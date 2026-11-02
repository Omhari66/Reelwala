"""Pydantic schemas and loader for video templates."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


class CanvasConfig(BaseModel):
    """Canvas dimensions and framerate."""

    width: int = 1080
    height: int = 1920
    fps: int = 30


class ShotLengthConfig(BaseModel):
    """Shot length constraints."""

    min: float = 1.0
    max: float = 2.0


class SegmentRole(BaseModel):
    """Segment role in template timeline."""

    role: str
    seconds: float
    pick: str
    cuts: str | None = None


class TextStyleConfig(BaseModel):
    """Style and positioning for a text element."""

    start: float | None = None
    end: float | None = None
    position: str = "lower_third"
    font_size: int = 72
    color: str = "#FFFFFF"
    stroke: str | None = "#000000"
    stroke_w: int | None = 5
    bg: str | None = None
    shape: str | None = None
    max_words: int | None = None
    per_line_s: float | None = None
    only_if_price: bool = False


class BrandConfig(BaseModel):
    """Brand accent bar and name display."""

    accent_bar: str = "bottom"
    bar_height: int = 14
    show_business_name: bool = True
    name_position: str = "bottom_left"
    name_font_size: int = 44


class TransitionConfig(BaseModel):
    """Transition style."""

    type: str = "hard_cut"
    optional_flash_frames: int | None = None


class MusicConfig(BaseModel):
    """Background music mixing configuration."""

    file: str = "auto"
    volume: float = 0.18
    duck_under_speech: bool = True
    fade_out_s: float = 0.5


class TemplateConfig(BaseModel):
    """Full template configuration schema."""

    name: Literal["offer", "new_dish", "behind_the_scenes"]
    description: str
    target_duration_s: float
    canvas: CanvasConfig = CanvasConfig()
    shot_length_s: ShotLengthConfig = ShotLengthConfig()
    segments_roles: list[SegmentRole] = []
    text: dict[str, Any] = {}
    brand: BrandConfig = BrandConfig()
    transitions: TransitionConfig = TransitionConfig()
    music: MusicConfig = MusicConfig()


def load_template(template_name: str, base_dir: Path | str | None = None) -> TemplateConfig:
    """Load and parse template YAML by name."""
    directory = Path(base_dir) if base_dir else TEMPLATES_DIR
    target_file = directory / f"{template_name}.yaml"
    if not target_file.is_file():
        raise FileNotFoundError(f"Template '{template_name}' not found at {target_file}")

    raw = yaml.safe_load(target_file.read_text(encoding="utf-8"))
    return TemplateConfig.model_validate(raw)
