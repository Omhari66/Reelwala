"""Pipeline step: Parse owner feedback into RevisionRequest and apply minimal re-runs."""

import logging
from pathlib import Path

from app.llm.client import LLMClient
from app.llm.schemas import ClipAnalysis, Plan, RevisionRequest, Segment
from app.pipeline.plan import BusinessContext, extract_price_from_text

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "revise_v1.md"
MAX_REVISIONS = 3

APPROVE_KEYWORDS = {"ok", "okay", "yes", "haan", "ha", "approve", "done", "theek hai", "👍", "post kar dunga"}
CANCEL_KEYWORDS = {"cancel", "band karo", "rehne do", "stop"}
SHORTER_KEYWORDS = {"chhota karo", "shorter", "thoda chota", "chota karo", "kam karo"}
LONGER_KEYWORDS = {"lamba karo", "longer", "bada karo"}
HOOK_KEYWORDS = {"naya hook", "hook change", "different start", "hook badlo", "different hook"}


def parse_revision_request(
    owner_message: str,
    current_plan: Plan,
    business: BusinessContext,
    llm_client: LLMClient,
) -> RevisionRequest:
    """Parse owner's message into structured RevisionRequest using heuristics and LLM."""
    cleaned = owner_message.strip().lower()

    # Fast-path deterministic detection for global and common commands
    if cleaned in APPROVE_KEYWORDS:
        return RevisionRequest(approve=True)
    if cleaned in CANCEL_KEYWORDS:
        return RevisionRequest(cancel=True)

    # Use LLM with prompt
    prompt_base = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.is_file() else ""
    context = (
        f"{prompt_base}\n\n"
        f"Current Plan Summary:\n"
        f"- Hook: {current_plan.hook_text}\n"
        f"- Price: ₹{current_plan.price_inr}\n"
        f"- Target Duration: {current_plan.target_duration_s}s\n"
        f"- Menu items: {[m.get('name') for m in business.menu_items]}\n\n"
        f"Owner Message: \"{owner_message}\""
    )

    try:
        req = llm_client.generate_json(prompt=context, schema=RevisionRequest)
    except Exception as e:
        logger.warning(f"Revision LLM failed: {e}. Using deterministic parser.")
        # Fallback deterministic parsing
        price = extract_price_from_text(owner_message)
        shorter = any(w in cleaned for w in SHORTER_KEYWORDS)
        longer = any(w in cleaned for w in LONGER_KEYWORDS)
        hook = any(w in cleaned for w in HOOK_KEYWORDS)

        if not any([price, shorter, longer, hook]):
            return RevisionRequest(unclear=True)

        return RevisionRequest(
            price_inr=price,
            shorter=shorter,
            longer=longer,
            regenerate_hook=hook,
        )

    # Price verification by code (never trust LLM blindly)
    code_price = extract_price_from_text(owner_message)
    if code_price is not None:
        req.price_inr = code_price

    return req


def apply_revision(
    current_plan: Plan,
    revision: RevisionRequest,
    revision_count: int,
    business: BusinessContext,
    clip_analyses: list[ClipAnalysis],
) -> tuple[Plan, str]:
    """Apply minimal re-run to Plan per ARCHITECTURE section 5.6 and enforce max 3 revisions."""
    if revision_count >= MAX_REVISIONS and not (revision.approve or revision.cancel):
        raise ValueError("Maximum revision limit reached (max 3 revisions allowed).")

    if revision.approve:
        return current_plan, "approved"
    if revision.cancel:
        return current_plan, "cancelled"
    if revision.unclear:
        return current_plan, "unclear"

    plan = current_plan.model_copy(deep=True)

    # 1. Price change
    if revision.price_inr is not None:
        old_price = plan.price_inr
        new_price = revision.price_inr
        plan.price_inr = new_price
        plan.offer_text = f"₹{new_price}"

        if old_price:
            plan.hook_text = plan.hook_text.replace(f"₹{old_price}", f"₹{new_price}").replace(str(old_price), str(new_price))
            plan.caption = plan.caption.replace(f"₹{old_price}", f"₹{new_price}").replace(str(old_price), str(new_price))
            plan.on_screen_lines = [
                line.replace(f"₹{old_price}", f"₹{new_price}").replace(str(old_price), str(new_price))
                for line in plan.on_screen_lines
            ]
        else:
            plan.hook_text = f"Sirf ₹{new_price} mein! {plan.hook_text}"[:40]
            plan.caption = f"Sirf ₹{new_price}! {plan.caption}"[:300]
            plan.on_screen_lines.insert(0, f"Sirf ₹{new_price}")

    # 2. Text change
    if revision.text_change:
        plan.on_screen_lines.append(revision.text_change)
        if len(plan.on_screen_lines) > 4:
            plan.on_screen_lines = plan.on_screen_lines[-4:]

    # 3. Shorter: reduce target duration by ~25% (bounded between 10s and 20s)
    if revision.shorter:
        new_dur = max(10.0, round(plan.target_duration_s * 0.75, 1))
        scale = new_dur / plan.target_duration_s
        new_segments: list[Segment] = []
        for s in plan.segments:
            seg_len = max(1.0, round((s.end - s.start) * scale, 2))
            new_segments.append(
                Segment(
                    clip_id=s.clip_id,
                    start=s.start,
                    end=round(s.start + seg_len, 2),
                )
            )
        plan.target_duration_s = new_dur
        plan.segments = new_segments

    # 4. Longer: increase target duration by ~25% (bounded <= 20s)
    if revision.longer:
        new_dur = min(20.0, round(plan.target_duration_s * 1.25, 1))
        scale = new_dur / plan.target_duration_s
        new_segments = []
        for s in plan.segments:
            seg_len = round((s.end - s.start) * scale, 2)
            new_segments.append(
                Segment(
                    clip_id=s.clip_id,
                    start=s.start,
                    end=round(s.start + seg_len, 2),
                )
            )
        plan.target_duration_s = new_dur
        plan.segments = new_segments

    # 5. Regenerate Hook
    if revision.regenerate_hook:
        hooks = [
            f"Kya aapne ye try kiya? {business.name}",
            f"Craving alert! {business.name} special",
            "Is steam ko dekho!",
            "Aaj kya khane ka man hai?",
        ]
        # Pick alternative hook not identical to current
        alt_hook = next((h for h in hooks if h != plan.hook_text), hooks[0])
        plan.hook_text = alt_hook

    return plan, "revised"
