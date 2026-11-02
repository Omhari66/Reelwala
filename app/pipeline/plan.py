"""Pipeline step: Creative ad planning with structured LLM output and fallback."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient
from app.llm.schemas import (
    ClipAnalysis,
    InsufficientFootage,
    Moment,
    Plan,
    PlanResult,
    Segment,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "plan_v1.md"


class BusinessContext(BaseModel):
    """Business profile context passed to ad planner."""

    name: str
    category: str = "Food stall"
    language: str = "hinglish"
    landmark: str | None = None
    brand_hex: str = "#FF5722"
    menu_items: list[dict[str, Any]] = []


class PlanOrInsufficient(BaseModel):
    """Container schema for LLM structured output."""

    plan: Plan | None = None
    insufficient_footage: bool = False
    tip: str | None = None


def calculate_usable_footage(clip_analyses: list[ClipAnalysis]) -> float:
    """Calculate total duration of usable moments (appeal >= 5 and sharpness >= 4)."""
    usable_seconds = 0.0
    for clip in clip_analyses:
        for m in clip.moments:
            if m.appeal >= 5 and m.sharpness >= 4:
                usable_seconds += max(0.0, m.t_end - m.t_start)
    return round(usable_seconds, 2)


def extract_price_from_text(text: str | None) -> int | None:
    """Extract price in INR using strict regex (never trust LLM for measurement)."""
    if not text:
        return None
    match = re.search(r"(?:₹|rs\.?|inr)\s?(\d+)|(\d+)\s?(?:rs|inr|/-)", text, re.IGNORECASE)
    if match:
        val = match.group(1) or match.group(2)
        return int(val)
    return None


def build_deterministic_fallback_plan(
    business: BusinessContext,
    owner_message: str | None,
    clip_analyses: list[ClipAnalysis],
) -> Plan | InsufficientFootage:
    """Build a deterministic rule-based plan from highest-appeal moments."""
    usable_seconds = calculate_usable_footage(clip_analyses)
    tip_lang = business.language.lower()
    if usable_seconds < 6.0:
        tip = (
            "Phone ko steady rakh kar roshni mein 3 naye clips film karein."
            if tip_lang != "english"
            else "Please film 3 steady, well-lit clips with your phone held vertically."
        )
        return InsufficientFootage(tip=tip)

    msg_lower = (owner_message or "").lower()
    price = extract_price_from_text(owner_message)

    # 1. Select template
    if price or any(w in msg_lower for w in ["combo", "offer", "discount", "deal", "special"]):
        template = "offer"
        target_duration = 15.0
    elif any(w in msg_lower for w in ["new", "naya", "launch", "dish"]):
        template = "new_dish"
        target_duration = 14.0
    else:
        template = "behind_the_scenes"
        target_duration = 16.0

    # 2. Collect and rank moments
    scored_moments: list[tuple[int, Moment]] = []
    for clip in clip_analyses:
        for m in clip.moments:
            scored_moments.append((clip.clip_id, m))

    scored_moments.sort(key=lambda item: (item[1].appeal, item[1].sharpness, item[1].lighting), reverse=True)

    # Hook moment: highest appeal with food
    food_moments = [item for item in scored_moments if item[1].has_food]
    hook_item = food_moments[0] if food_moments else scored_moments[0]

    segments: list[Segment] = []
    current_time = 0.0

    # First segment: Hook shot (2.0s)
    hook_clip_id, hook_moment = hook_item
    hook_duration = min(2.0, max(1.0, hook_moment.t_end - hook_moment.t_start))
    segments.append(
        Segment(
            clip_id=hook_clip_id,
            start=hook_moment.t_start,
            end=round(hook_moment.t_start + hook_duration, 2),
        )
    )
    current_time += hook_duration

    # Intermediate segments
    for cid, m in scored_moments:
        if current_time >= target_duration - 2.5:
            break
        if cid == hook_clip_id and m.t_start == hook_moment.t_start:
            continue
        seg_dur = min(2.0, max(1.2, m.t_end - m.t_start))
        segments.append(
            Segment(
                clip_id=cid,
                start=m.t_start,
                end=round(m.t_start + seg_dur, 2),
            )
        )
        current_time += seg_dur

    # Closing segment: loop back to hook moment
    remaining = max(1.5, target_duration - current_time)
    segments.append(
        Segment(
            clip_id=hook_clip_id,
            start=hook_moment.t_start,
            end=round(hook_moment.t_start + min(remaining, hook_moment.t_end - hook_moment.t_start), 2),
        )
    )

    # 3. Text generation (strict adherence to business profile facts)
    hook_text = f"₹{price} mein special combo!" if price else f"Swad jo yaad rahe - {business.name}"
    if len(hook_text.split()) > 6:
        hook_text = f"{business.name} special"

    on_screen_lines = [
        "Taste jo dil jeet le",
        "Ek baar zaroor try karein",
    ]
    if price:
        on_screen_lines.insert(0, f"Sirf ₹{price} mein")

    landmark_part = f"{business.landmark} ke paas" if business.landmark else "Aaj hi aao"
    cta = f"Aaj hi aao, {landmark_part}"[:50]
    if len(cta.split()) > 8:
        cta = "Aaj hi visit karein"

    caption = f"{hook_text}! {cta}. Fresh & tasty food at {business.name}."
    hashtags = ["#foodie", "#streetfood", "#delhifood", "#taste", "#reelsindia"]

    lang = business.language.lower()
    if lang not in ("hinglish", "hindi", "english"):
        lang = "hinglish"

    return Plan(
        template=template,
        target_duration_s=target_duration,
        segments=segments,
        hook_text=hook_text,
        on_screen_lines=on_screen_lines,
        offer_text=f"₹{price}" if price else None,
        price_inr=price,
        call_to_action=cta,
        caption=caption[:300],
        hashtags=hashtags,
        language=lang,  # type: ignore[arg-type]
    )


def plan_ad_campaign(
    business: BusinessContext,
    owner_message: str | None,
    clip_analyses: list[ClipAnalysis],
    llm_client: LLMClient,
) -> Plan | InsufficientFootage:
    """Generate ad plan using LLM with one retry and deterministic fallback."""
    # Pre-check footage sufficiency
    usable = calculate_usable_footage(clip_analyses)
    if usable < 6.0:
        tip = "Clips thode dark/hilte hue hain. Phone steady rakh kar roshni mein 3 naye clips film karein."
        return InsufficientFootage(tip=tip)

    prompt_base = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.is_file() else ""
    context_data = {
        "business": business.model_dump(),
        "owner_message": owner_message or "",
        "clips": [c.model_dump() for c in clip_analyses],
    }
    prompt = f"{prompt_base}\n\n## Inputs\n{json.dumps(context_data, indent=2)}"

    def _call(p: str) -> Plan | InsufficientFootage:
        res = llm_client.generate_json(prompt=p, schema=PlanResult)
        return res.root


    # Attempt 1
    try:
        return _call(prompt)
    except (ValidationError, Exception) as e1:
        logger.warning(f"Plan generation attempt 1 failed: {e1}. Retrying once...")
        retry_prompt = f"{prompt}\n\nPrevious attempt failed with error: {e1}. Please return valid Plan or InsufficientFootage JSON."
        try:
            return _call(retry_prompt)
        except (ValidationError, Exception) as e2:
            logger.error(f"Plan generation attempt 2 failed: {e2}. Falling back to deterministic plan.")
            return build_deterministic_fallback_plan(business, owner_message, clip_analyses)
