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
import os
import math
import tempfile
import time
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ...schemas.social_visual import Slide, AdCard
from ...core.paths import PROJECT_ROOT

TEMPLATES_DIR = PROJECT_ROOT / "social" / "templates"
RENDERS_DIR   = PROJECT_ROOT / "social" / "renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

ASPECT_SIZES = {
    "16:9": (1920, 1080),
    "1:1":  (1080, 1080),
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
}


def _layer_motion(image, layer, t, canvas_size):
    """Render the saved entrance/exit motion. Coordinates are normalized centers."""
    w, h = canvas_size
    if not layer.start <= t < layer.end:
        return None
    duration = min(layer.animation_duration, (layer.end - layer.start) / 2)
    entrance = min(1.0, max(0.0, (t - layer.start) / duration))
    exit_progress = min(1.0, max(0.0, (layer.end - t) / duration))
    if layer.easing == "ease_in_out":
        entrance = entrance * entrance * (3 - 2 * entrance)
        exit_progress = exit_progress * exit_progress * (3 - 2 * exit_progress)
    alpha, scale, dx, reveal = float(getattr(layer, "opacity", 1)), 1.0, 0.0, 1.0
    pulse_applied = False
    for motion, progress, exiting in ((layer.animation_in, entrance, False), (layer.animation_out, exit_progress, True)):
        if motion == "fade":
            alpha *= progress
        elif motion == "slide":
            dx += (1 - progress) * w * (.35 if exiting else -.35)
        elif motion == "zoom":
            scale *= .6 + .4 * progress
            alpha *= progress
        elif motion == "reveal":
            reveal *= progress
        elif motion == "pulse" and not pulse_applied:
            scale *= 1 + .045 * math.sin((t - layer.start) * math.tau * 1.5)
            pulse_applied = True
    frame = image.copy().convert("RGBA")
    if scale != 1:
        frame = frame.resize((max(1, round(frame.width * scale)), max(1, round(frame.height * scale))), Image.Resampling.LANCZOS)
    if reveal < 1:
        mask = Image.new("L", frame.size, 0)
        ImageDraw.Draw(mask).rectangle((0, 0, int(frame.width * reveal), frame.height), fill=255)
        from PIL import ImageChops
        frame.putalpha(ImageChops.multiply(frame.getchannel("A"), mask))
    if alpha < 1:
        frame.putalpha(frame.getchannel("A").point(lambda value: round(value * alpha)))
    x = round(layer.x * w - frame.width / 2 + dx)
    y = round(layer.y * h - frame.height / 2)
    return frame, x, y


def _text_layer_image(layer, size):
    font_files = {"Arial": "arial.ttf", "Arial Bold": "arialbd.ttf", "Georgia": "georgia.ttf", "Consolas": "consola.ttf"}
    font_path = Path("C:/Windows/Fonts") / font_files[layer.font]
    font = ImageFont.truetype(str(font_path), layer.size) if font_path.is_file() else _load_font(layer.size)
    maximum_width = int(size[0] * .88)
    measurement = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = []
    for paragraph in layer.content.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            proposed = f"{current} {word}".strip()
            if current and measurement.textlength(proposed, font=font) > maximum_width:
                lines.append(current); current = word
            else:
                current = proposed
        lines.append(current)
    text = "\n".join(lines)
    box = measurement.multiline_textbbox((0, 0), text, font=font, spacing=8, align=layer.align)
    if box[2] - box[0] > maximum_width or box[3] - box[1] > size[1] * .9:
        raise ValueError(f"Text layer {layer.id} does not fit; reduce font size or shorten its text")
    image = Image.new("RGBA", (max(1, box[2] - box[0] + 16), max(1, box[3] - box[1] + 16)))
    ImageDraw.Draw(image).multiline_text((8 - box[0], 8 - box[1]), text, font=font, fill=layer.color, spacing=8, align=layer.align,
                                        stroke_width=1, stroke_fill="#000000")
    return image


def render_composed_ad(ad, composition, assets):
    """Local, saved-state renderer: visual/text motion + voice + timed SFX."""
    from pydub import AudioSegment
    ffmpeg = os.getenv("DANDY_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is unavailable")
    duration = float(ad["duration_seconds"])
    from ..production.ads import mix_ad_tracks
    mixed = mix_ad_tracks(ad, [track.model_dump() for track in composition.sfx_tracks], assets)
    asset_map = {asset["asset_id"]: asset for asset in assets}
    def asset_path(asset_id):
        record = asset_map.get(asset_id)
        if not record:
            raise ValueError(f"Asset {asset_id} is not attached to this ad")
        path = Path(record["stored_path"])
        if not path.is_file():
            raise ValueError(f"Asset file is missing: {asset_id}")
        return path
    size = ASPECT_SIZES[composition.aspect]
    fps = 24
    layers = [(layer, _text_layer_image(layer, size)) for layer in composition.text_layers]
    visual_sources = []
    video_commands = []
    readers = []
    output = RENDERS_DIR / f"advisual_{ad['ad_id']}_{uuid.uuid4().hex[:8]}.mp4"
    with tempfile.TemporaryDirectory(dir=str(RENDERS_DIR), prefix="ad_render_") as scratch:
        scratch = Path(scratch)
        audio = scratch / "mixed.wav"
        mixed.export(audio, format="wav").close()
        for layer in composition.visuals:
            path = asset_path(layer.asset_id)
            if path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
                video_commands.append((layer, [ffmpeg, "-v", "error", "-stream_loop", "-1", "-i", str(path), "-vf", f"scale={size[0]}:{size[1]}",
                                               "-r", str(fps), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]))
            else:
                with Image.open(path) as original:
                    image = original.convert("RGBA")
                if layer.role == "background":
                    image = ImageOps.fit(image, size)
                else:
                    image.thumbnail((round(size[0] * layer.width), size[1]))
                visual_sources.append((layer, image))
        error_log = scratch / "ffmpeg_errors.txt"
        with error_log.open("wb") as errors:
            encoder = subprocess.Popen([ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
                                        "-r", str(fps), "-i", "pipe:0", "-i", str(audio), "-map", "0:v", "-map", "1:a",
                                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                                        "-t", str(duration), "-movflags", "+faststart", str(output)], stdin=subprocess.PIPE, stderr=errors)
            started = time.monotonic()
            timed_out = threading.Event()
            processes = [encoder]
            def abort_render():
                timed_out.set()
                for process in processes:
                    if process.poll() is None:
                        try:
                            process.kill()
                        except OSError:
                            pass
            # A loop-clock check alone cannot interrupt a blocked pipe read/write.
            watchdog = threading.Timer(600, abort_render)
            watchdog.daemon = True
            watchdog.start()
            try:
                for layer, command in video_commands:
                    reader = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    readers.append((layer, reader))
                    processes.append(reader)
                    visual_sources.append((layer, reader))
                order = {layer.id: index for index, layer in enumerate(composition.visuals)}
                visual_sources.sort(key=lambda item: order[item[0].id])
                for frame_index in range(math.ceil(duration * fps)):
                    if time.monotonic() - started > 600:
                        raise TimeoutError("Visual render exceeded 10 minutes")
                    t = frame_index / fps
                    canvas = Image.new("RGBA", size, composition.background_color)
                    for layer, source in visual_sources:
                        if layer.start <= t < layer.end:
                            if isinstance(source, subprocess.Popen):
                                raw = source.stdout.read(size[0] * size[1] * 3)
                                if len(raw) != size[0] * size[1] * 3:
                                    raise RuntimeError(f"Video decode failed for {layer.asset_id}")
                                frame = Image.frombytes("RGB", size, raw).convert("RGBA")
                                if layer.role != "background":
                                    frame.thumbnail((round(size[0] * layer.width), size[1]))
                            else:
                                frame = source
                            placed = _layer_motion(frame, layer, t, size)
                            if placed:
                                canvas.alpha_composite(placed[0], (placed[1], placed[2]))
                    for layer, image in layers:
                        placed = _layer_motion(image, layer, t, size)
                        if placed:
                            canvas.alpha_composite(placed[0], (placed[1], placed[2]))
                    encoder.stdin.write(canvas.convert("RGB").tobytes())
                encoder.stdin.close()
                if encoder.wait(timeout=30):
                    raise RuntimeError(error_log.read_text(encoding="utf-8", errors="replace")[-1200:])
            except Exception as exc:
                if encoder.poll() is None:
                    encoder.kill()
                encoder.wait(timeout=5)
                output.unlink(missing_ok=True)
                if timed_out.is_set():
                    raise TimeoutError("Visual render exceeded 10 minutes") from exc
                raise
            finally:
                watchdog.cancel()
                watchdog.join(timeout=5)
                if encoder.stdin and not encoder.stdin.closed:
                    encoder.stdin.close()
                for _, reader in readers:
                    if reader.poll() is None:
                        reader.kill()
                    reader.wait(timeout=5)
                    reader.stdout.close()
    if not output.is_file() or not output.stat().st_size:
        raise RuntimeError("Encoder did not produce a non-empty video")
    return {"path": str(output), "download_url": f"/renders/{output.name}", "duration_seconds": duration,
            "aspect": composition.aspect, "width": size[0], "height": size[1], "composition_version": composition.version}


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
