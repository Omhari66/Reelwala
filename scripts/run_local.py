"""CLI tool to execute the Reelwala pipeline locally without WhatsApp."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.llm.client import FakeLLMClient, LLMClient  # noqa: E402
from app.llm.schemas import ClipAnalysis, Moment, Plan, PlanResult  # noqa: E402
from app.pipeline.analyse import analyse_clips_parallel  # noqa: E402
from app.pipeline.download import normalize_media_clip  # noqa: E402
from app.pipeline.plan import BusinessContext, plan_ad_campaign  # noqa: E402
from app.pipeline.quality import run_pipeline_with_quality_autofix  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_local")


def default_business() -> BusinessContext:
    """Default business profile for CLI testing."""
    return BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Campus Gate",
        brand_hex="#FF5722",
        menu_items=[
            {"name": "Steamed Veg Momo", "price_inr": 60},
            {"name": "Fried Chicken Momo", "price_inr": 90},
            {"name": "Special Momo Combo", "price_inr": 99},
        ],
    )


def load_business_profile(source: str | None) -> BusinessContext:
    """Load business profile from JSON file or JSON string."""
    if not source:
        return default_business()

    path = Path(source)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            logger.warning("Could not parse --business as JSON; using default profile.")
            return default_business()

    return BusinessContext.model_validate(data)


def create_fake_llm() -> LLMClient:
    """Create FakeLLMClient with dynamic canned responses for local pipeline."""
    def _canned_handler(prompt: str, schema: type) -> Any:
        if schema == ClipAnalysis:
            return ClipAnalysis(
                clip_id=1,
                moments=[
                    Moment(
                        t_start=0.0,
                        t_end=3.0,
                        appeal=8,
                        sharpness=8,
                        lighting=8,
                        has_food=True,
                        has_person=False,
                        tag="steam food close-up",
                    ),
                    Moment(
                        t_start=3.0,
                        t_end=5.0,
                        appeal=7,
                        sharpness=7,
                        lighting=7,
                        has_food=True,
                        has_person=True,
                        tag="owner smiling",
                    ),
                ],
                overall_note="appetising and well lit",
            )
        elif schema == Plan or schema == PlanResult:
            plan = Plan(
                template="offer",
                target_duration_s=15.0,
                segments=[
                    {"clip_id": 1, "start": 0.0, "end": 2.0},
                    {"clip_id": 2, "start": 0.0, "end": 2.0},
                    {"clip_id": 3, "start": 0.0, "end": 2.0},
                    {"clip_id": 1, "start": 2.0, "end": 4.0},
                    {"clip_id": 2, "start": 2.0, "end": 4.0},
                    {"clip_id": 3, "start": 2.0, "end": 4.0},
                    {"clip_id": 1, "start": 0.0, "end": 3.0},
                ],
                hook_text="₹99 Momo Combo Alert!",
                on_screen_lines=[
                    "Steamed Hot Veg Momos",
                    "Spicy Garlic Dip",
                    "Special College Combo",
                ],
                offer_text="₹99 Combo",
                price_inr=99,
                call_to_action="Aaj hi aao North Campus",
                caption="Special combo only ₹99! Freshly steamed hot momos at Tibetan Momo Corner. #momo",
                hashtags=["#momo", "#foodie", "#delhifood", "#combo", "#offer"],
                language="hinglish",
            )
            return PlanResult(root=plan) if schema == PlanResult else plan

        raise ValueError(f"Unknown schema in fake LLM: {schema}")

    return FakeLLMClient(canned_responses=_canned_handler)


def run_pipeline(
    clip_paths: list[str],
    message: str,
    business_source: str | None,
    out_dir: str,
    use_fake_llm: bool = True,
) -> dict[str, Any]:
    """Execute end-to-end local video generation pipeline."""
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    biz = load_business_profile(business_source)
    llm_client = create_fake_llm()

    print("==================================================")
    print("🎬 Reelwala Local Pipeline (CLI)")
    print(f"Business: {biz.name} ({biz.language})")
    print(f"Message : {message}")
    print(f"Clips   : {len(clip_paths)} clips provided")
    print("==================================================")

    # Step 1: Download & Normalize
    t0 = time.perf_counter()
    normalized_clips: dict[int, Path] = {}
    for idx, path_str in enumerate(clip_paths, start=1):
        norm = normalize_media_clip(path_str, target_dir)
        normalized_clips[idx] = norm
    t_down = time.perf_counter() - t0
    timings["download_s"] = round(t_down, 2)
    print(f"[1/5] Download & normalize : {t_down:.2f}s")

    # Step 2: Analyse (Local + Vision)
    t0 = time.perf_counter()
    clip_items = [(cid, path) for cid, path in normalized_clips.items()]
    clip_analyses = analyse_clips_parallel(clip_items, llm_client=llm_client)
    for c in clip_analyses:
        logger.info(f"Clip {c.clip_id}: {len(c.moments)} moments, note: '{c.overall_note}'")
    t_ana = time.perf_counter() - t0
    timings["analyse_s"] = round(t_ana, 2)
    print(f"[2/5] Analyse clips (LLM)   : {t_ana:.2f}s")

    # Step 3: Plan
    t0 = time.perf_counter()
    plan_res = plan_ad_campaign(
        business=biz,
        owner_message=message,
        clip_analyses=clip_analyses,
        llm_client=llm_client,
    )
    if not isinstance(plan_res, Plan):
        print(f"⚠️ Footage insufficient: {plan_res.tip}")
        return {"error": "insufficient_footage", "tip": plan_res.tip}

    t_plan = time.perf_counter() - t0
    timings["plan_s"] = round(t_plan, 2)
    print(f"[3/5] Creative ad planning : {t_plan:.2f}s (Template: {plan_res.template})")

    # Step 4 & 5: Render & Quality Auto-Fix
    t0 = time.perf_counter()
    out_video_path = target_dir / "preview.mp4"
    rendered_vid, quality_report = run_pipeline_with_quality_autofix(
        plan=plan_res,
        business=biz,
        clip_paths=normalized_clips,
        clip_analyses=clip_analyses,
        output_path=out_video_path,
        owner_message=message,
    )
    t_render = time.perf_counter() - t0
    timings["render_and_quality_s"] = round(t_render, 2)
    total_time = sum(timings.values())
    timings["total_duration_s"] = round(total_time, 2)

    print(f"[4/5] Render & Quality Gates: {t_render:.2f}s")
    print(f"[5/5] Pipeline finished in {total_time:.2f}s")

    # Write output artifacts
    (target_dir / "plan.json").write_text(plan_res.model_dump_json(indent=2), encoding="utf-8")
    (target_dir / "quality_report.json").write_text(quality_report.model_dump_json(indent=2), encoding="utf-8")

    # Cost logging (tokens, render seconds, estimated INR)
    # Gemini Flash pricing ~ $0.15 / 1M tokens * 85 INR/USD
    in_tokens = 1500
    out_tokens = 400
    token_cost_inr = round(((in_tokens + out_tokens) / 1_000_000) * 0.15 * 85.0, 4)
    # Compute cost ~ 2 vCPU seconds estimated at ~0.05 INR
    compute_cost_inr = round(t_render * 0.005, 4)
    total_inr = round(token_cost_inr + compute_cost_inr, 2)

    cost_data = {
        "step_timings_seconds": timings,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "render_seconds": round(t_render, 2),
        "est_token_cost_inr": token_cost_inr,
        "est_compute_cost_inr": compute_cost_inr,
        "est_total_cost_inr": max(total_inr, 0.05),
    }
    (target_dir / "cost.json").write_text(json.dumps(cost_data, indent=2), encoding="utf-8")

    print("\nQuality Gates Summary:")
    for g in quality_report.gates:
        status_sym = "[PASS]" if g.passed else "[FAIL]"
        print(f" {status_sym:7s} {g.name:20s}: {g.message}")

    print(f"\n==> Generated preview video: {rendered_vid.resolve()}")

    return {
        "preview_path": str(rendered_vid),
        "quality_report": quality_report.model_dump(),
        "timings": timings,
        "cost": cost_data,
    }


def main() -> None:
    """CLI parser and launcher."""
    parser = argparse.ArgumentParser(description="Run Reelwala pipeline locally.")
    parser.add_argument("--clips", nargs="+", required=True, help="List of video clip or image paths")
    parser.add_argument("--message", default="New momo combo Rs 99 for college students", help="Owner message")
    parser.add_argument("--business", default=None, help="Path to business JSON or inline JSON")
    parser.add_argument("--out-dir", default="out", help="Output directory")
    parser.add_argument("--fake-llm", action="store_true", default=True, help="Use fake LLM for offline local run")
    args = parser.parse_args()

    run_pipeline(
        clip_paths=args.clips,
        message=args.message,
        business_source=args.business,
        out_dir=args.out_dir,
        use_fake_llm=args.fake_llm,
    )


if __name__ == "__main__":
    main()
