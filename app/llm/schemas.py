"""Authoritative Pydantic schemas for LLM inputs and outputs."""

from typing import Literal

from pydantic import BaseModel, Field, RootModel


class Moment(BaseModel):
    """A scored moment within a video clip."""

    t_start: float
    t_end: float
    appeal: int = Field(ge=1, le=10, description="1-10, how appetising/engaging")
    sharpness: int = Field(ge=1, le=10)
    lighting: int = Field(ge=1, le=10)
    has_food: bool
    has_person: bool
    tag: str


class ClipAnalysis(BaseModel):
    """Analysis result for a single video clip."""

    clip_id: int
    moments: list[Moment]
    overall_note: str


class Segment(BaseModel):
    """A cut segment selected from a source clip."""

    clip_id: int
    start: float
    end: float


class Plan(BaseModel):
    """Creative ad plan for video rendering."""

    template: Literal["offer", "new_dish", "behind_the_scenes"]
    target_duration_s: float
    segments: list[Segment]
    hook_text: str
    on_screen_lines: list[str]
    offer_text: str | None = None
    price_inr: int | None = None
    call_to_action: str
    caption: str
    hashtags: list[str]
    language: Literal["hinglish", "hindi", "english"]


class InsufficientFootage(BaseModel):
    """Returned when footage does not meet minimum quality threshold."""

    insufficient_footage: Literal[True] = True
    tip: str


PlanOutput = Plan | InsufficientFootage


class PlanResult(RootModel[PlanOutput]):
    """Wrapper schema for Plan | InsufficientFootage."""

    root: PlanOutput



class RevisionRequest(BaseModel):
    """Structured request extracted from owner revision message."""

    price_inr: int | None = None
    shorter: bool = False
    longer: bool = False
    regenerate_hook: bool = False
    text_change: str | None = None
    approve: bool = False
    cancel: bool = False
    unclear: bool = False


class MenuItem(BaseModel):
    """Single menu item with optional price in INR."""

    name: str
    price_inr: int | None = None


class MenuExtraction(BaseModel):
    """Extraction output from menu photo or text."""

    items: list[MenuItem]
    uncertain: list[str]
