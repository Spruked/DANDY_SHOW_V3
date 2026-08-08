import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

import torch

from ...core.paths import PROJECT_ROOT


logger = logging.getLogger(__name__)

DEFAULTS = {
    "width": 1280,
    "height": 720,
    "wave_color": "#d8a340",
    "wave_mode": "cline",
    "wave_scale": "cbrt",
    "background_color": "#08111f",
    "title_color": "white",
    "sponsor_color": "white",
    "logo_path": None,
    "background_image_path": None,
    "font_path": None,
    "title_font_size": 46,
    "sponsor_font_size": 34,
    "hook_font_size": 58,
    "caption_font_size": 34,
    "caption_color": "white",
    "hook_color": "#f7f3ea",
    "hook_box_color": "black@0.55",
    "caption_box_color": "black@0.5",
    "fps": 30,
    "codec_cuda": "h264_nvenc",
    "codec_cpu": "libx264",
    "audio_codec": "aac",
    "pixel_format": "yuv420p",
}


def _load_config() -> Dict:
    config_path = PROJECT_ROOT / "config" / "social_presets.json"
    if not config_path.exists():
        return DEFAULTS.copy()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    audiogram = payload.get("audiogram", {})
    merged = DEFAULTS.copy()
    merged.update(audiogram)
    return merged


def _resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _escape_ffmpeg_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "")
        .replace('"', "")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def generate_audiogram(
    audio_path: str | Path,
    output_path: str | Path,
    title: str = "",
    sponsor_text: str = "",
    hook_text: str = "",
    captions: List[Dict] | None = None,
    image_cues: List[Dict] | None = None,
    background_image_path: str | None = None,
) -> str:
    config = _load_config()
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        logger.error("Audiogram source audio does not exist: %s", audio_path)
        return ""

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.error("ffmpeg is not available in PATH")
        return ""

    vcodec = config["codec_cuda"] if torch.cuda.is_available() else config["codec_cpu"]
    filter_parts = [
        f"[0:a]showwaves=s={config['width']}x{config['height']}:mode={config['wave_mode']}:colors={config['wave_color']}:scale={config['wave_scale']},format=rgba,colorkey=0x000000:0.12:0.08[wave]"
    ]

    inputs = [
        ffmpeg_path,
        "-y",
        "-i",
        str(audio_path),
    ]

    resolved_bg = _resolve_path(background_image_path) or _resolve_path(config.get("background_image_path"))
    if resolved_bg and resolved_bg.exists():
        inputs.extend(["-loop", "1", "-i", str(resolved_bg)])
        filter_parts.append(
            f"[1:v]scale={config['width']}:{config['height']}:force_original_aspect_ratio=increase,crop={config['width']}:{config['height']}[bg]"
        )
        bg_label = "[bg]"
        next_input_index = 2
    else:
        inputs.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"color=c={config['background_color']}:s={config['width']}x{config['height']}:r={config['fps']}",
            ]
        )
        filter_parts.append("[1:v]format=rgba[bg]")
        bg_label = "[bg]"
        next_input_index = 2

    filter_parts.append(f"{bg_label}[wave]overlay=0:0[base]")
    current = "[base]"

    resolved_logo = _resolve_path(config.get("logo_path"))
    if resolved_logo and resolved_logo.exists():
        inputs.extend(["-i", str(resolved_logo)])
        filter_parts.append(f"[{next_input_index}:v]scale=150:-1[logo]")
        filter_parts.append(f"{current}[logo]overlay=W-w-40:40[with_logo]")
        current = "[with_logo]"
        next_input_index += 1

    image_cues = image_cues or []
    for idx, cue in enumerate(image_cues[:4]):
        cue_path = _resolve_path(cue.get("path"))
        if not cue_path or not cue_path.exists():
            continue
        start = max(0.0, float(cue.get("start", 0.0)))
        end = max(start + 0.5, float(cue.get("end", start + 3.0)))
        inputs.extend(["-loop", "1", "-i", str(cue_path)])
        cue_label = f"[cueimg{idx}]"
        next_label = f"[with_cue_{idx}]"
        filter_parts.append(f"[{next_input_index}:v]scale=320:-1,format=rgba{cue_label}")
        filter_parts.append(
            f"{current}{cue_label}overlay=W-w-50:210:enable='between(t,{start},{end})'{next_label}"
        )
        current = next_label
        next_input_index += 1

    title_text = _escape_ffmpeg_text(title[:80]) if title else ""
    sponsor_line = _escape_ffmpeg_text(sponsor_text[:90]) if sponsor_text else ""
    hook_line = _escape_ffmpeg_text(hook_text[:90]) if hook_text else ""
    font_path = _resolve_path(config.get("font_path"))
    font_arg = ""
    if font_path and font_path.exists():
        normalized_font_path = str(font_path).replace("\\", "/")
        font_arg = f":fontfile='{normalized_font_path}'"

    if title_text:
        filter_parts.append(
            f"{current}drawtext=text='{title_text}'{font_arg}:fontsize={config['title_font_size']}:fontcolor={config['title_color']}:box=1:boxcolor=black@0.35:boxborderw=18:x=(w-text_w)/2:y=64[with_title]"
        )
        current = "[with_title]"

    if hook_line:
        filter_parts.append(
            f"{current}drawtext=text='{hook_line}'{font_arg}:fontsize={config['hook_font_size']}:fontcolor={config['hook_color']}:box=1:boxcolor={config['hook_box_color']}:boxborderw=20:x=(w-text_w)/2:y=150:enable='between(t,0,3.2)'[with_hook]"
        )
        current = "[with_hook]"

    if sponsor_line:
        filter_parts.append(
            f"{current}drawtext=text='{sponsor_line}'{font_arg}:fontsize={config['sponsor_font_size']}:fontcolor={config['sponsor_color']}:box=1:boxcolor=black@0.45:boxborderw=16:x=(w-text_w)/2:y=h-110[with_sponsor]"
        )
        current = "[with_sponsor]"
    else:
        filter_parts.append(f"{current}format=rgba[with_sponsor]")
        current = "[with_sponsor]"

    captions = captions or []
    for idx, cue in enumerate(captions[:8]):
        caption_text = _escape_ffmpeg_text(cue.get("text", "")[:100])
        if not caption_text:
            continue
        start = max(0, float(cue.get("start", 0.0)))
        end = max(start + 0.2, float(cue.get("end", start + 2.0)))
        next_label = f"[cap{idx}]"
        filter_parts.append(
            f"{current}drawtext=text='{caption_text}'{font_arg}:fontsize={config['caption_font_size']}:fontcolor={config['caption_color']}:box=1:boxcolor={config['caption_box_color']}:boxborderw=14:x=(w-text_w)/2:y=h-190:enable='between(t,{start},{end})'{next_label}"
        )
        current = next_label

    if current != "[final]":
        filter_parts.append(f"{current}format=rgba[final]")

    cmd = inputs + [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[final]",
        "-map",
        "0:a",
        "-c:v",
        vcodec,
        "-pix_fmt",
        config["pixel_format"],
        "-c:a",
        config["audio_codec"],
        "-r",
        str(config["fps"]),
        "-shortest",
        str(output_path),
    ]

    if vcodec == config["codec_cuda"]:
        cmd[1:1] = ["-hwaccel", "cuda"]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return str(output_path)
    except subprocess.CalledProcessError as exc:
        logger.error("Audiogram generation failed: %s", exc.stderr or exc)
        return ""
