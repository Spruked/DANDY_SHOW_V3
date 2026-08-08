import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from pydub import AudioSegment

from .audiogram_generator import generate_audiogram
from .captions_generator import build_caption_cues, build_hook_text
from .clip_generator import build_clip_exports
from .post_copy_generator import build_post_copy
from .thumbnail_generator import generate_thumbnail


def _probe_audio_duration(audio_path: str | Path, script_lines: List[Dict]) -> float:
    audio_path = Path(audio_path)
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            candidate = Path(ffmpeg_path).with_name("ffprobe.exe")
            if candidate.exists():
                ffprobe_path = str(candidate)

    if ffprobe_path:
        cmd = [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            duration = float(result.stdout.strip())
            if duration > 0:
                return duration
        except Exception:
            pass

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        cmd = [ffmpeg_path, "-i", str(audio_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            output = f"{result.stdout}\n{result.stderr}"
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                duration = round((hours * 3600) + (minutes * 60) + seconds, 2)
                if duration > 0:
                    return duration
        except Exception:
            pass

    try:
        segment = AudioSegment.from_file(audio_path)
        duration = round(len(segment) / 1000.0, 2)
        if duration > 0:
            return duration
    except Exception:
        pass

    word_count = sum(len(line.get("text", "").split()) for line in script_lines)
    return max(4.0, min(90.0, word_count * 0.38))


def export_social_package(
    episode_id: str,
    title: str,
    topic: str,
    script_text: str,
    script_lines: List[Dict],
    audio_path: str | Path,
    destination: Path,
    sponsor_text: str = "",
    media_cues: List[Dict] | None = None,
) -> Dict:
    destination.mkdir(parents=True, exist_ok=True)
    audio_duration = max(1.0, _probe_audio_duration(audio_path, script_lines))
    hook_text = build_hook_text(title=title, topic=topic, script_lines=script_lines)
    captions = build_caption_cues(script_lines=script_lines, total_duration_seconds=audio_duration)
    image_cues = _build_image_cues(
        media_cues=media_cues or [],
        script_lines=script_lines,
        total_duration_seconds=audio_duration,
    )
    clip_exports = build_clip_exports(
        episode_id=episode_id,
        title=title,
        sponsor_text=sponsor_text,
        script_lines=script_lines,
        audio_path=audio_path,
        total_duration_seconds=audio_duration,
        destination=destination,
        clip_count=3,
    )

    thumbnail_path = generate_thumbnail(
        episode_id=episode_id,
        title=title,
        subtitle=topic,
        sponsor_text=sponsor_text,
        output_dir=destination,
    )
    audiogram_path = generate_audiogram(
        audio_path=audio_path,
        output_path=destination / "audiogram.mp4",
        title=title,
        sponsor_text=sponsor_text,
        hook_text=hook_text,
        captions=captions,
        image_cues=image_cues,
    )
    post_copy = build_post_copy(
        episode_id=episode_id,
        title=title,
        topic=topic,
        script_text=script_text,
    )

    payload = {
        "episode_id": episode_id,
        "status": "exported",
        "audio": str(audio_path),
        "thumbnail": thumbnail_path,
        "video": audiogram_path,
        "hook_text": hook_text,
        "captions_count": len(captions),
        "image_cues_count": len(image_cues),
        "clips": clip_exports,
        "clips_count": len(clip_exports),
        "script_preview": script_text[:200],
        "copy": post_copy,
    }
    (destination / "social_export.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _build_image_cues(media_cues: List[Dict], script_lines: List[Dict], total_duration_seconds: float) -> List[Dict]:
    if not media_cues:
        return []

    line_weights = [max(1, len(line.get("text", "").split())) for line in script_lines] or [1]
    total_weight = max(1, sum(line_weights))
    line_timings: Dict[int, Dict[str, float]] = {}
    current = 0.0
    for idx, weight in enumerate(line_weights, start=1):
        duration = max(1.5, (weight / total_weight) * total_duration_seconds)
        start = round(current, 2)
        end = round(min(total_duration_seconds, current + duration), 2)
        line_timings[idx] = {"start": start, "end": end}
        current = end

    image_cues: List[Dict] = []
    for cue in media_cues:
        asset = cue.get("asset") or {}
        if asset.get("asset_type") != "image":
            continue
        stored_path = asset.get("stored_path")
        if not stored_path:
            continue

        line_number = cue.get("line_number")
        line_timing = line_timings.get(int(line_number)) if line_number else None
        start_seconds = cue.get("start_seconds")
        end_seconds = cue.get("end_seconds")

        start = float(start_seconds) if start_seconds is not None else (line_timing or {}).get("start", 0.0)
        end = float(end_seconds) if end_seconds is not None else (line_timing or {}).get("end", min(total_duration_seconds, start + 4.0))
        if end <= start:
            end = min(total_duration_seconds, start + 3.0)

        image_cues.append(
            {
                "asset_id": cue.get("asset_id"),
                "path": stored_path,
                "start": round(max(0.0, start), 2),
                "end": round(min(total_duration_seconds, end), 2),
                "display_label": cue.get("display_label", ""),
            }
        )

    return image_cues
