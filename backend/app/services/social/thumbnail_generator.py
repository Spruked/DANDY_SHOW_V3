import json
import logging
from pathlib import Path
from typing import Dict, Optional

from PIL import Image, ImageDraw, ImageFont

from ...core.paths import PROJECT_ROOT


logger = logging.getLogger(__name__)

DEFAULTS = {
    "width": 1280,
    "height": 720,
    "background_color": "#08111f",
    "text_color": "#d8a340",
    "subtitle_color": "#f7f3ea",
    "sponsor_color": "#ff6b4a",
    "font_path": None,
    "logo_path": None,
    "background_image_path": None,
    "font_size_title": 72,
    "font_size_subtitle": 40,
    "font_size_sponsor": 34,
    "safe_zone_x": 56,
    "safe_zone_top": 72,
    "safe_zone_bottom": 140,
    "title_max_chars": 80,
    "subtitle_max_chars": 100,
    "sponsor_max_chars": 90,
    "output_format": "jpg",
    "quality": 92,
}


def _load_config() -> Dict:
    config_path = PROJECT_ROOT / "config" / "social_presets.json"
    if not config_path.exists():
        return DEFAULTS.copy()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    thumbnail = payload.get("thumbnail", {})
    merged = DEFAULTS.copy()
    merged.update(thumbnail)
    return merged


def _load_font(font_path: Optional[str], size: int):
    try:
        if font_path:
            return ImageFont.truetype(font_path, size)
        for candidate in ("arialbd.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        raise OSError("No default truetype font found")
    except OSError:
        logger.warning("Falling back to default font for thumbnail rendering")
        return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return (8, 17, 31)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _build_fallback_background(width: int, height: int, base_hex: str, accent_hex: str) -> Image.Image:
    base = _hex_to_rgb(base_hex)
    accent = _hex_to_rgb(accent_hex)
    image = Image.new("RGB", (width, height), color=base)
    pixels = image.load()

    for y in range(height):
        blend = y / max(1, height - 1)
        row = tuple(int(base[i] * (1 - blend) + accent[i] * blend * 0.25) for i in range(3))
        for x in range(width):
            diag = x / max(1, width - 1)
            pixels[x, y] = tuple(min(255, int(row[i] + accent[i] * diag * 0.08)) for i in range(3))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, width, 16), fill=accent + (210,))
    draw.rounded_rectangle((36, height - 220, width - 36, height - 42), radius=28, fill=(0, 0, 0, 110))
    draw.ellipse((width - 280, -120, width + 120, 220), fill=accent + (55,))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _draw_text_with_shadow(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font, fill, shadow_fill):
    x, y = position
    draw.text((x + 3, y + 3), text, fill=shadow_fill, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _resolve_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def generate_thumbnail(
    episode_id: str,
    title: str,
    subtitle: str = "",
    sponsor_text: str = "",
    background_image_path: str | None = None,
    output_dir: str | Path | None = None,
) -> str:
    config = _load_config()
    output_root = Path(output_dir) if output_dir else (PROJECT_ROOT / "social" / "generated" / episode_id)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"thumbnail.{config['output_format']}"

    try:
        resolved_bg = _resolve_path(background_image_path) or _resolve_path(config.get("background_image_path"))
        if resolved_bg and resolved_bg.exists():
            image = Image.open(resolved_bg).convert("RGB")
            image = image.resize((config["width"], config["height"]), Image.LANCZOS)
        else:
            image = _build_fallback_background(
                config["width"],
                config["height"],
                config["background_color"],
                config["text_color"],
            )

        draw = ImageDraw.Draw(image)
        title_font = _load_font(config.get("font_path"), config["font_size_title"])
        subtitle_font = _load_font(config.get("font_path"), config["font_size_subtitle"])
        sponsor_font = _load_font(config.get("font_path"), config["font_size_sponsor"])

        left = config["safe_zone_x"]
        right = config["width"] - config["safe_zone_x"]
        safe_title = title[: config["title_max_chars"]]
        title_box = draw.textbbox((0, 0), safe_title, font=title_font)
        title_width = title_box[2] - title_box[0]
        title_x = max(left, min((config["width"] - title_width) // 2, right - title_width))
        _draw_text_with_shadow(
            draw,
            (title_x, config["safe_zone_top"]),
            safe_title,
            title_font,
            config["text_color"],
            "#02050a",
        )

        if subtitle:
            safe_subtitle = subtitle[: config["subtitle_max_chars"]]
            sub_box = draw.textbbox((0, 0), safe_subtitle, font=subtitle_font)
            sub_width = sub_box[2] - sub_box[0]
            sub_x = max(left, min((config["width"] - sub_width) // 2, right - sub_width))
            _draw_text_with_shadow(
                draw,
                (sub_x, config["safe_zone_top"] + 132),
                safe_subtitle,
                subtitle_font,
                config["subtitle_color"],
                "#02050a",
            )

        if sponsor_text:
            safe_sponsor = sponsor_text[: config["sponsor_max_chars"]]
            sponsor_box = draw.textbbox((0, 0), safe_sponsor, font=sponsor_font)
            sponsor_width = sponsor_box[2] - sponsor_box[0]
            sponsor_pad_x = 22
            sponsor_pad_y = 12
            sponsor_x = max(left, min((config["width"] - sponsor_width) // 2, right - sponsor_width))
            sponsor_y = config["height"] - config["safe_zone_bottom"]
            draw.rounded_rectangle(
                (
                    sponsor_x - sponsor_pad_x,
                    sponsor_y - sponsor_pad_y,
                    sponsor_x + sponsor_width + sponsor_pad_x,
                    sponsor_y + (sponsor_box[3] - sponsor_box[1]) + sponsor_pad_y,
                ),
                radius=18,
                fill=(8, 8, 8, 180),
            )
            _draw_text_with_shadow(
                draw,
                (sponsor_x, sponsor_y),
                safe_sponsor,
                sponsor_font,
                config["sponsor_color"],
                "#000000",
            )

        resolved_logo = _resolve_path(config.get("logo_path"))
        if resolved_logo and resolved_logo.exists():
            logo = Image.open(resolved_logo).convert("RGBA")
            target_width = min(180, logo.width)
            scale = target_width / max(1, logo.width)
            logo = logo.resize((int(logo.width * scale), int(logo.height * scale)), Image.LANCZOS)
            image.paste(logo, (config["width"] - logo.width - 44, 40), logo)

        image.save(
            output_path,
            format="JPEG" if config["output_format"].lower() == "jpg" else "PNG",
            quality=config["quality"],
        )
        return str(output_path)
    except Exception as exc:
        logger.exception("Thumbnail generation failed for %s: %s", episode_id, exc)
        return ""
