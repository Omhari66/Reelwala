"""Generate Advanced SubStation Alpha (ASS) subtitles for burned-in video captions."""

from pathlib import Path
from typing import Any


def hex_to_ass_bgr(hex_str: str, alpha: int = 0) -> str:
    """Convert hex color (#RRGGBB) to ASS color format &HAABBGGRR."""
    cleaned = hex_str.lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(c * 2 for c in cleaned)
    if len(cleaned) != 6:
        cleaned = "FFFFFF"
    r = cleaned[0:2]
    g = cleaned[2:4]
    b = cleaned[4:6]
    return f"&H{alpha:02X}{b}{g}{r}"


def format_ass_time(seconds: float) -> str:
    """Format float seconds to ASS timestamp H:MM:SS.cs."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        secs += 1
        cs = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def generate_ass_subtitles(
    hook_text: str,
    on_screen_lines: list[str],
    offer_text: str | None,
    cta_text: str,
    business_name: str,
    brand_hex: str,
    target_duration_s: float,
    output_path: Path | str,
    template_text_config: dict[str, Any] | None = None,
    price_inr: int | None = None,
) -> Path:
    """Write an ASS subtitle file driven by template configuration."""
    out_file = Path(output_path)
    brand_ass = hex_to_ass_bgr(brand_hex)
    cfg = template_text_config or {}

    content = f"""[Script Info]
Title: Reelwala Video Overlay
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Arial,92,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,8,90,90,300,1
Style: DishName,Arial,86,&H00FFFFFF,&H000000FF,{brand_ass},{brand_ass},-1,0,0,0,100,100,0,0,1,5,0,2,90,90,450,1
Style: Badge,Arial,80,&H00000000,&H000000FF,{brand_ass},{brand_ass},-1,0,0,0,100,100,0,0,1,4,0,9,90,90,260,1
Style: Lines,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,90,90,320,1
Style: CTA,Arial,78,&H00000000,&H000000FF,{brand_ass},{brand_ass},-1,0,0,0,100,100,0,0,1,5,0,2,90,90,320,1
Style: BrandName,Arial,44,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,1,90,90,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []

    # 1. Hook Text
    hook_cfg = cfg.get("hook", {})
    h_start = hook_cfg.get("start", 0.2)
    h_end = min(hook_cfg.get("end", 2.2), target_duration_s)
    events.append(f"Dialogue: 0,{format_ass_time(h_start)},{format_ass_time(h_end)},Hook,,0,0,0,,{hook_text}")

    # 2. Dish Name (used in new_dish template)
    dish_cfg = cfg.get("dish_name")
    if dish_cfg:
        d_start = dish_cfg.get("start", 2.2)
        d_end = min(dish_cfg.get("end", 6.0), target_duration_s)
        dish_display = on_screen_lines[0] if on_screen_lines else "Special New Dish"
        events.append(f"Dialogue: 0,{format_ass_time(d_start)},{format_ass_time(d_end)},DishName,,0,0,0,,{dish_display}")

    # 3. Badge / Price Tag
    price_tag_cfg = cfg.get("price_tag")
    offer_badge_cfg = cfg.get("offer_badge")
    if price_tag_cfg and price_inr:
        p_start = price_tag_cfg.get("start", 6.0)
        p_end = min(price_tag_cfg.get("end", target_duration_s - 1.0), target_duration_s)
        events.append(f"Dialogue: 0,{format_ass_time(p_start)},{format_ass_time(p_end)},Badge,,0,0,0,,₹{price_inr}")
    elif (offer_badge_cfg or not cfg) and offer_text:
        o_start = offer_badge_cfg.get("start", 2.0) if offer_badge_cfg else 2.0
        o_end = min(offer_badge_cfg.get("end", target_duration_s - 3.0), target_duration_s) if offer_badge_cfg else max(2.5, target_duration_s - 3.0)
        events.append(f"Dialogue: 0,{format_ass_time(o_start)},{format_ass_time(o_end)},Badge,,0,0,0,,{offer_text}")

    # 4. On-screen lines
    lines_list = on_screen_lines[1:] if dish_cfg and len(on_screen_lines) > 1 else on_screen_lines
    lines_cfg = cfg.get("lines", {})
    l_start = 2.2 if not dish_cfg else 6.0
    cta_cfg = cfg.get("cta", {})
    l_end = cta_cfg.get("start", max(l_start + 1.0, target_duration_s - 3.0))
    if lines_list and l_end > l_start:
        nominal_dur = (l_end - l_start) / len(lines_list)
        per_line_limit = lines_cfg.get("per_line_s", nominal_dur)
        dur_per_line = min(nominal_dur, per_line_limit)
        for i, line in enumerate(lines_list):
            s_t = l_start + (i * dur_per_line)
            e_t = s_t + dur_per_line
            events.append(f"Dialogue: 0,{format_ass_time(s_t)},{format_ass_time(e_t)},Lines,,0,0,0,,{line}")


    # 5. CTA Text
    c_start = cta_cfg.get("start", max(0.0, target_duration_s - 3.0))
    c_end = min(cta_cfg.get("end", target_duration_s), target_duration_s)
    events.append(f"Dialogue: 0,{format_ass_time(c_start)},{format_ass_time(c_end)},CTA,,0,0,0,,{cta_text}")

    # 6. Brand Name
    events.append(f"Dialogue: 0,{format_ass_time(1.0)},{format_ass_time(target_duration_s)},BrandName,,0,0,0,,{business_name}")

    out_file.write_text(content + "\n".join(events) + "\n", encoding="utf-8")
    return out_file
