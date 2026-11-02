"""Cost logging and computation for token and compute usage."""

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import CostLog

logger = logging.getLogger(__name__)

# Base Gemini pricing (per million tokens)
INPUT_TOKEN_PRICE_USD_PER_M = 0.075
OUTPUT_TOKEN_PRICE_USD_PER_M = 0.30

# Estimated 2-vCPU server compute cost in INR per render second (~₹0.002 / sec)
RENDER_INR_PER_SECOND = 0.002


def compute_cost_inr(
    input_tokens: int = 0,
    output_tokens: int = 0,
    render_seconds: float = 0.0,
    usd_inr: float | None = None,
) -> float:
    """Calculate estimated cost in INR for LLM tokens and render compute."""
    rate = usd_inr or settings.USD_INR
    token_cost_usd = (
        (input_tokens / 1_000_000) * INPUT_TOKEN_PRICE_USD_PER_M
        + (output_tokens / 1_000_000) * OUTPUT_TOKEN_PRICE_USD_PER_M
    )
    token_cost_inr = token_cost_usd * rate
    render_cost_inr = render_seconds * RENDER_INR_PER_SECOND
    return round(token_cost_inr + render_cost_inr, 4)


def record_step_cost(
    db: Session,
    campaign_id: int,
    step: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    render_seconds: float = 0.0,
) -> CostLog:
    """Persist a CostLog record for a campaign step."""
    cost_inr = compute_cost_inr(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        render_seconds=render_seconds,
    )
    log_entry = CostLog(
        campaign_id=campaign_id,
        step=step,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        render_seconds=round(render_seconds, 2),
        est_cost_inr=cost_inr,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry

