"""
Slideshow + ad-card renderer.
Static frames produced with Pillow. MP4 assembly via ffmpeg subprocess.
Outputs go to social/renders/. FastAPI mounts that as /renders.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ...schemas.social_visual import Slide, AdCard
from ...core.paths import PROJECT_ROOT

TEMPLATES_DIR = PROJECT_ROOT / "social" / "templates"
RENDERS_DIR   = PROJECT_ROOT / "social" / "renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

ASPECT_SIZES = {
    "16:9": (1920, 1080),
    "1:1":  (1080, 1080),
    "9:16": (1080, 1920),
}


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        str(PROJECT_ROOT / "assets" / "fonts" / "Inter-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _resolve_image(filename: str) -> Path | None:
    if not filename:
        return None
    for base in [TEMPLATES_DIR, PROJECT_ROOT / "social" / "assets"]:
        p = base / filename
        if p.exists():
            return p
    return None


def _draw_slide(slide: Slide, size: tuple[int, int]) -> Image.Image:
    w, h = size
    bg = _resolve_image(slide.background)
    if bg:
        img = Image.open(bg).convert("RGB").resize(size)
    else:
        img = Image.new("RGB", size, (14, 17, 22))

    draw = ImageDraw.Draw(img)
    title_font = _load_font(slide.style.fontSize)
    sub_font   = _load_font(int(slide.style.fontSize * 0.55))
    body_font  = _load_font(int(slide.style.fontSize * 0.4))

    y = h // 3
    for text, font in [
        (slide.title,    title_font),
        (slide.subtitle, sub_font),
        (slide.body,     body_font),
    ]:
        if not text:
            continue
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        if slide.style.align == "center":
            x = (w - tw) // 2
        elif slide.style.align == "right":
            x = w - tw - 80
        else:
            x = 80
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0))
        draw.text((x, y),         text, font=font, fill=slide.style.color)
        y += (bbox[3] - bbox[1]) + 20

    for overlay in slide.overlays:
        ov_path = _resolve_image(overlay)
        if ov_path:
            ov = Image.open(ov_path).convert("RGBA")
            ov.thumbnail((w // 6, h // 6))
            img.paste(ov, (w - ov.width - 40, 40), ov)

    return img


def render_slideshow_job(
    episode_id: str,
    slideshow_path: Path,
    aspect: str = "16:9",
    fmt: str = "mp4",
) -> dict:
    size = ASPECT_SIZES[aspect]
    data = json.loads(slideshow_path.read_text())
    slides = [Slide(**s) for s in data["slides"]]

    job_id = uuid.uuid4().hex[:8]
    work = RENDERS_DIR / f"slideshow_{episode_id}_{job_id}"
    work.mkdir(parents=True, exist_ok=True)

    frames = []
    for i, slide in enumerate(slides):
        img = _draw_slide(slide, size)
        frame_path = work / f"frame_{i:04d}.png"
        img.save(frame_path)
        frames.append((frame_path, max(0.5, slide.end - slide.start)))

    if fmt == "png_sequence":
        zip_path = RENDERS_DIR / f"slideshow_{episode_id}_{job_id}.zip"
        shutil.make_archive(str(zip_path.with_suffix("")), "zip", work)
        return {"path": str(zip_path), "url": f"/renders/{zip_path.name}"}

    concat_file = work / "concat.txt"
    with concat_file.open("w") as f:
        for path, dur in frames:
            f.write(f"file '{path.resolve()}'\n")
            f.write(f"duration {dur:.3f}\n")
        if frames:
            f.write(f"file '{frames[-1][0].resolve()}'\n")

    mp4_path = RENDERS_DIR / f"slideshow_{episode_id}_{job_id}.mp4"
    audio_path = PROJECT_ROOT / "episodes" / episode_id / "audio.mp3"

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
    if audio_path.exists():
        cmd += ["-i", str(audio_path), "-map", "0:v", "-map", "1:a", "-shortest"]
    cmd += ["-vsync", "vfr", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", str(mp4_path)]
    subprocess.run(cmd, check=True)

    return {"path": str(mp4_path), "url": f"/renders/{mp4_path.name}"}


def render_adcard_job(card: AdCard, aspect: str = "1:1", fmt: str = "png") -> dict:
    size = ASPECT_SIZES[aspect]
    job_id = uuid.uuid4().hex[:8]

    bg = _resolve_image(card.background)
    img = Image.open(bg).convert("RGB").resize(size) if bg else Image.new("RGB", size, (14, 17, 22))

    draw = ImageDraw.Draw(img)
    w, h = size

    sponsor_font = _load_font(int(h * 0.07))
    cta_font     = _load_font(int(h * 0.04))
    code_font    = _load_font(int(h * 0.035))

    y = h // 2 - int(h * 0.1)
    for text, font, color in [
        (card.sponsor,                                        sponsor_font, (255, 255, 255)),
        (card.cta,                                            cta_font,     (220, 220, 220)),
        (f"Code: {card.offer_code}" if card.offer_code else "", code_font, (212, 182, 74)),
        (card.url,                                            code_font,    (180, 180, 180)),
    ]:
        if not text:
            continue
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
        draw.text((x, y),         text, font=font, fill=color)
        y += (bbox[3] - bbox[1]) + 20

    logo_path = _resolve_image(card.logo)
    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((w // 4, h // 4))
        img.paste(logo, ((w - logo.width) // 2, int(h * 0.12)), logo)

    if fmt == "png":
        out = RENDERS_DIR / f"adcard_{card.id}_{job_id}.png"
        img.save(out)
        return {"path": str(out), "url": f"/renders/{out.name}"}

    tmp = RENDERS_DIR / f"adcard_{card.id}_{job_id}_tmp.png"
    img.save(tmp)
    out = RENDERS_DIR / f"adcard_{card.id}_{job_id}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-t", "4", "-i", str(tmp),
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", str(out),
    ], check=True)
    tmp.unlink(missing_ok=True)
    return {"path": str(out), "url": f"/renders/{out.name}"}
