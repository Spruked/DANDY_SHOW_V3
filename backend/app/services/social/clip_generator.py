import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

from .audiogram_generator import generate_audiogram


def _timed_lines(script_lines: List[Dict], total_duration_seconds: float) -> List[Dict]:
    weights = [max(1, len(line.get("text", "").split())) for line in script_lines]
    total_weight = max(1, sum(weights))
    current = 0.0
    timed: List[Dict] = []

    for line, weight in zip(script_lines, weights):
        duration = max(1.5, (weight / total_weight) * total_duration_seconds)
        start = round(current, 2)
        end = round(min(total_duration_seconds, current + duration), 2)
        timed.append(
            {
                "speaker": line.get("speaker", "speaker"),
                "text": line.get("text", ""),
                "start": start,
                "end": end,
            }
        )
        current = end
        if current >= total_duration_seconds:
            break

    return timed


def _score_text(text: str) -> float:
    lowered = text.lower()
    score = min(6.0, len(lowered.split()) * 0.18)
    if "?" in text:
        score += 3.0
    if "!" in text:
        score += 2.0
    if any(token in lowered for token in ("free", "now", "sponsor", "goat", "mint", "listen", "what if", "why")):
        score += 2.5
    return score


def _select_clip_windows(timed_lines: List[Dict], total_duration_seconds: float, clip_count: int = 3) -> List[Dict]:
    candidates = []
    for idx, line in enumerate(timed_lines):
        start = max(0.0, line["start"] - 1.2)
        end = min(total_duration_seconds, max(line["end"] + 2.8, start + 8.0))
        if total_duration_seconds - start < 3.0:
            continue
        if end - start < 3.0:
            continue
        candidates.append(
            {
                "index": idx,
                "hook_text": line["text"][:90],
                "start": round(start, 2),
                "end": round(end, 2),
                "score": _score_text(line["text"]),
            }
        )

    selected: List[Dict] = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        overlaps = False
        for existing in selected:
            if not (candidate["end"] <= existing["start"] or candidate["start"] >= existing["end"]):
                overlaps = True
                break
        if overlaps:
            continue
        selected.append(candidate)
        if len(selected) >= clip_count:
            break

    return sorted(selected, key=lambda item: item["start"])


def _extract_audio_clip(audio_path: Path, output_path: Path, start: float, end: float) -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return ""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(1.0, end - start)
    if duration < 1.0:
        return ""
    cmd = [
        ffmpeg_path,
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(audio_path),
        "-c:a",
        "mp3",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        if not output_path.exists() or output_path.stat().st_size < 2048:
            return ""
        return str(output_path)
    except subprocess.CalledProcessError:
        return ""


def _probe_clip_duration(audio_path: Path) -> float | None:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path or not audio_path.exists():
        return None

    cmd = [ffmpeg_path, "-i", str(audio_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = f"{result.stdout}\n{result.stderr}"
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        duration = round((hours * 3600) + (minutes * 60) + seconds, 2)
        return duration if duration > 0 else None
    except Exception:
        return None


def build_clip_exports(
    episode_id: str,
    title: str,
    sponsor_text: str,
    script_lines: List[Dict],
    audio_path: str | Path,
    total_duration_seconds: float,
    destination: Path,
    clip_count: int = 3,
) -> List[Dict]:
    audio_path = Path(audio_path)
    clips_root = destination / "clips"
    clips_root.mkdir(parents=True, exist_ok=True)

    timed = _timed_lines(script_lines, total_duration_seconds)
    windows = _select_clip_windows(timed, total_duration_seconds, clip_count=clip_count)
    exports: List[Dict] = []

    for idx, window in enumerate(windows, start=1):
        clip_name = f"clip_{idx:02d}"
        clip_audio = clips_root / f"{clip_name}.mp3"
        clip_video = clips_root / f"{clip_name}.mp4"
        clip_meta = clips_root / f"{clip_name}.json"

        audio_result = _extract_audio_clip(audio_path, clip_audio, window["start"], window["end"])
        if not audio_result:
            continue

        actual_clip_duration = _probe_clip_duration(clip_audio)

        actual_end = window["end"]
        if actual_clip_duration is not None and actual_clip_duration > 0:
            actual_end = round(window["start"] + actual_clip_duration, 2)

        local_captions = []
        for line in timed:
            if line["end"] < window["start"] or line["start"] > actual_end:
                continue
            local_captions.append(
                {
                    "speaker": line["speaker"],
                    "text": f"{str(line['speaker']).upper()}: {line['text'][:90]}",
                    "start": max(0.0, round(line["start"] - window["start"], 2)),
                    "end": max(0.5, round(min(line["end"], actual_end) - window["start"], 2)),
                }
            )

        video_result = generate_audiogram(
            audio_path=clip_audio,
            output_path=clip_video,
            title=title,
            sponsor_text=sponsor_text,
            hook_text=window["hook_text"],
            captions=local_captions,
        )

        payload = {
            "clip_id": clip_name,
            "start": window["start"],
            "end": actual_end,
            "score": window["score"],
            "hook_text": window["hook_text"],
            "audio": audio_result,
            "video": video_result,
            "captions_count": len(local_captions),
        }
        clip_meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        exports.append(payload)

    return exports
