"""
sfx.py — Sound Effects injection for Phil & Jim Dandy Show
===========================================================
Loads SFX from audio/sfx/ by filename convention and overlays or
inserts them at configured positions in the episode audio.

Supported trigger modes:
  - "overlay":  mix SFX into the episode at a given offset (music bed style)
  - "insert":   splice SFX in as a gap between segments (hard cut)

SFX file naming convention in audio/sfx/:
  papers_rustling.mp3    — paper/desk ambient noise
  phone_ring_distant.mp3 — distant phone ring
  (any .mp3 or .wav file can be referenced by slug in config)

Config section in config.json (all optional):
  "sfx": {
    "enabled": true,
    "gain_db": -12,
    "events": [
      {
        "slug": "papers_rustling",
        "mode": "overlay",
        "position": "after_intro",
        "offset_ms": 500,
        "gain_db": -14,
        "fade_in_ms": 300,
        "fade_out_ms": 800
      },
      {
        "slug": "phone_ring_distant",
        "mode": "insert",
        "position": "before_ad_2",
        "gain_db": -10
      }
    ]
  }

Positions understood:
  "after_intro"       — immediately after the intro music ends
  "before_outro"      — just before the outro music starts
  "before_ad_1/2/3"  — before that ad break
  "after_ad_1/2/3"   — after that ad break
  "start"             — absolute start (offset_ms from 0)
  "end"               — absolute end (offset_ms from end)
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydub import AudioSegment
import pydub.utils as _pydub_utils

logger = logging.getLogger(__name__)


def _configure_pydub() -> None:
    """Point pydub at the bundled ffmpeg/ffprobe in staging if not already in PATH."""
    _HERE = Path(__file__).resolve()
    project_root = _HERE.parents[4]
    bundled_bin = project_root / "staging" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
    if bundled_bin.exists():
        ffmpeg_bin = str(bundled_bin / "ffmpeg.exe")
        ffprobe_bin = str(bundled_bin / "ffprobe.exe")
        if Path(ffmpeg_bin).exists():
            AudioSegment.converter = ffmpeg_bin
            AudioSegment.ffmpeg = ffmpeg_bin
            AudioSegment.ffprobe = ffprobe_bin
            os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")


_configure_pydub()

_SUPPORTED_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}


def _load_sfx(slug: str, sfx_dir: Path, gain_db: float = 0.0,
               fade_in_ms: int = 0, fade_out_ms: int = 0) -> Optional[AudioSegment]:
    """Load an SFX file by slug, applying gain and fades."""
    for ext in _SUPPORTED_EXTS:
        candidate = sfx_dir / f"{slug}{ext}"
        if candidate.exists():
            try:
                sfx = AudioSegment.from_file(str(candidate))
                if gain_db != 0:
                    sfx = sfx.apply_gain(gain_db)
                if fade_in_ms > 0:
                    sfx = sfx.fade_in(fade_in_ms)
                if fade_out_ms > 0:
                    sfx = sfx.fade_out(fade_out_ms)
                logger.info("SFX loaded: %s (%.1fs)", candidate.name, len(sfx) / 1000)
                return sfx
            except Exception as exc:
                logger.warning("SFX load failed for %s: %s", candidate, exc)
                return None

    logger.warning("SFX not found for slug '%s' in %s", slug, sfx_dir)
    return None


def apply_sfx_events(
    episode_audio: AudioSegment,
    sfx_cfg: Dict[str, Any],
    sfx_dir: Path,
    segment_offsets: Optional[List[int]] = None,
) -> AudioSegment:
    """
    Apply all configured SFX events to the episode audio.

    Args:
        episode_audio:   The full assembled episode (post-mix, pre-intro/outro).
        sfx_cfg:         The "sfx" block from config.json.
        sfx_dir:         Path to audio/sfx/ directory.
        segment_offsets: Optional list of millisecond offsets for each segment
                         (used for position lookups like "before_ad_2").

    Returns:
        Modified AudioSegment with SFX applied.
    """
    if not sfx_cfg.get("enabled", False):
        return episode_audio

    events = sfx_cfg.get("events", [])
    if not events:
        return episode_audio

    global_gain = float(sfx_cfg.get("gain_db", -12))
    result = episode_audio
    total_ms = len(result)

    for event in events:
        slug = event.get("slug", "").strip()
        if not slug:
            continue

        gain_db = float(event.get("gain_db", global_gain))
        fade_in = int(event.get("fade_in_ms", 0))
        fade_out = int(event.get("fade_out_ms", 0))
        mode = event.get("mode", "overlay")
        position = event.get("position", "after_intro")
        offset_ms = int(event.get("offset_ms", 0))

        sfx = _load_sfx(slug, sfx_dir, gain_db, fade_in, fade_out)
        if sfx is None:
            continue

        # Resolve position to absolute millisecond offset
        abs_offset = _resolve_position(position, offset_ms, total_ms, segment_offsets)

        if mode == "overlay":
            result = _overlay_sfx(result, sfx, abs_offset)
            logger.info("SFX overlay '%s' at %dms", slug, abs_offset)
        elif mode == "insert":
            result = _insert_sfx(result, sfx, abs_offset)
            total_ms = len(result)  # recalculate after insertion
            logger.info("SFX insert '%s' at %dms", slug, abs_offset)
        else:
            logger.warning("Unknown SFX mode '%s' for slug '%s'", mode, slug)

    return result


def _resolve_position(position: str, offset_ms: int, total_ms: int,
                       segment_offsets: Optional[List[int]]) -> int:
    """Resolve a named position to an absolute millisecond offset."""
    p = position.lower().strip()

    if p == "start":
        return max(0, offset_ms)

    if p == "end":
        return max(0, total_ms - offset_ms)

    if p == "after_intro":
        # Treat as a fixed offset from the start (caller can tune offset_ms)
        return max(0, offset_ms)

    if p == "before_outro":
        return max(0, total_ms - offset_ms)

    # Segment-based: "before_ad_2", "after_ad_1", etc.
    if segment_offsets and (p.startswith("before_ad_") or p.startswith("after_ad_")):
        try:
            parts = p.split("_")
            idx = int(parts[-1]) - 1  # convert 1-based to 0-based
            if p.startswith("before"):
                base = segment_offsets[idx] if idx < len(segment_offsets) else total_ms // 2
            else:
                base = segment_offsets[idx] + offset_ms if idx < len(segment_offsets) else total_ms // 2
            return max(0, base + offset_ms)
        except (ValueError, IndexError):
            pass

    # Fallback: treat as fraction of total if it looks like a float string
    try:
        frac = float(p)
        return int(total_ms * max(0.0, min(1.0, frac)))
    except ValueError:
        pass

    logger.warning("Unrecognised SFX position '%s', defaulting to start", position)
    return offset_ms


def _overlay_sfx(base: AudioSegment, sfx: AudioSegment, position_ms: int) -> AudioSegment:
    """Overlay SFX on top of base audio at position_ms (mix, not insert)."""
    position_ms = max(0, min(position_ms, len(base)))
    return base.overlay(sfx, position=position_ms)


def _insert_sfx(base: AudioSegment, sfx: AudioSegment, position_ms: int) -> AudioSegment:
    """Splice SFX into base audio at position_ms (splits the audio, inserts, rejoins)."""
    position_ms = max(0, min(position_ms, len(base)))
    before = base[:position_ms]
    after = base[position_ms:]
    return before + sfx + after
