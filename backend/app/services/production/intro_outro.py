"""intro_outro.py — Intro and outro music + announcer synthesis for Dandy Show episodes.

Flow
----
Intro:
  1. Clip music from music_file at intro.clip_start_ms for intro.clip_duration_ms
  2. Fade the clip in (intro.music_fade_in_ms)
  3. At intro.duck_start_ms, duck the music by intro.duck_db decibels
  4. Synthesize announcer TTS (supports [pause] markers → AudioSegment.silent)
  5. Overlay announcer on ducked music starting at duck_start_ms
  6. Fade music out at the end; append intro.silence_after_ms of silence

Outro:
  1. Synthesize announcer TTS (topic injected into {topic} placeholder)
  2. Clip music at outro.clip_start_ms for outro.clip_duration_ms
  3. Fade music in (outro.music_fade_in_ms) and out (outro.music_fade_out_ms)
  4. Prepend outro.silence_before_ms of silence + announcer
  5. Start music fade-in so it overlaps the last outro.music_fade_in_ms of the announcer
  6. Concatenate silence+announcer+music
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from pydub import AudioSegment
import pydub.utils as _pydub_utils

logger = logging.getLogger(__name__)


def _configure_pydub() -> None:
    """Point pydub at the bundled ffmpeg/ffprobe in staging if not already in PATH."""
    import shutil
    _HERE = Path(__file__).resolve()
    # Walk up to project root (backend/app/services/production → project root)
    project_root = _HERE.parents[4]
    bundled_bin = project_root / "staging" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
    if bundled_bin.exists():
        ffmpeg_bin = str(bundled_bin / "ffmpeg.exe")
        ffprobe_bin = str(bundled_bin / "ffprobe.exe")
        if Path(ffmpeg_bin).exists():
            _pydub_utils.get_encoder_name = lambda: ffmpeg_bin  # type: ignore
            AudioSegment.converter = ffmpeg_bin
            AudioSegment.ffmpeg = ffmpeg_bin
            AudioSegment.ffprobe = ffprobe_bin
            # Also add to PATH so subprocess calls work
            os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")
            logger.debug("pydub configured with bundled ffmpeg: %s", bundled_bin)
            return
    logger.debug("Using system ffmpeg (bundled not found at %s)", bundled_bin)


_configure_pydub()

# ---------------------------------------------------------------------------
# Default config — overridden by config.json intro_outro section
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "music_file": "./audio/jingles/intro_outro.mp3",
    "intro": {
        "clip_start_ms": 0,
        "clip_duration_ms": 14000,
        "music_fade_in_ms": 1200,
        "music_fade_out_ms": 2000,
        "duck_start_ms": 4000,
        "duck_db": -18,
        "announcer_text": "And now... the Phil and Jiiiiiimmmmm Dandyyyy Shooowwwww!",
        "announcer_voice": "en-US-GuyNeural",
        "silence_after_ms": 800,
    },
    "outro": {
        "clip_start_ms": 0,
        "clip_duration_ms": 12000,
        "music_fade_in_ms": 2000,
        "music_fade_out_ms": 3000,
        "announcer_text": "Be sure and tune in next time when Phil[pause] and Jim talk about {topic}.",
        "announcer_voice": "en-US-GuyNeural",
        "silence_before_ms": 600,
        "pause_duration_ms": 700,
    },
}

PAUSE_MARKER = "[pause]"


def _load_music(music_file: str, base_path: Path) -> AudioSegment:
    p = Path(music_file)
    if not p.is_absolute():
        p = (base_path / music_file).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Intro/outro music file not found: {p}")
    return AudioSegment.from_file(str(p))


def _clip(music: AudioSegment, start_ms: int, duration_ms: int) -> AudioSegment:
    end_ms = start_ms + duration_ms
    clipped = music[start_ms:end_ms]
    if len(clipped) < duration_ms:
        # Loop if shorter than requested
        loops = (duration_ms // len(clipped)) + 2
        clipped = (clipped * loops)[:duration_ms]
    return clipped


_WSL_PYTHON = "/home/bryan/.venvs/gpu/bin/python"
_WSL_WORKER = "/home/bryan/wsl_tts_worker.py"
_WSL_TIMEOUT = 90  # seconds


def _win_to_wsl(path: Path) -> str:
    """Convert a Windows absolute path to a WSL /mnt/... path."""
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":\\").lower()
    rest = resolved.as_posix()
    rest = rest[len(drive) + 1:].lstrip("/")
    return f"/mnt/{drive}/{rest}"


def _synthesize_tts_wsl(part: str, voice: str, out_path: Path, speed: float = 1.0) -> None:
    """Synthesize a single text segment via WSL Kokoro GPU sidecar → WAV → MP3."""
    wav_path = out_path.with_suffix(".wav")
    wsl_out = _win_to_wsl(wav_path)

    result = subprocess.run(
        ["wsl", "--", _WSL_PYTHON, _WSL_WORKER,
         "--text", part, "--voice", voice, "--speed", str(speed), "--output", wsl_out],
        capture_output=True, text=True, timeout=_WSL_TIMEOUT,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown").strip()
        raise RuntimeError(f"WSL TTS failed: {err}")
    if not wav_path.exists():
        raise RuntimeError("WSL TTS produced no output file")

    ffmpeg_bin = getattr(AudioSegment, "ffmpeg", "ffmpeg") or "ffmpeg"
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", str(wav_path),
         "-codec:a", "libmp3lame", "-q:a", "2", str(out_path)],
        check=True, capture_output=True,
    )
    wav_path.unlink(missing_ok=True)


def _synthesize_tts_edge_sync(text: str, voice: str, output_path: Path, pause_ms: int = 700) -> None:
    """Synthesize `text` to `output_path` using WSL Kokoro (GPU).
    Falls back to Edge TTS on Windows if WSL call fails.
    Splits on [pause] markers, inserting silence between segments.
    """
    # Map Edge TTS voice names → Kokoro voice names for the announcer
    _edge_to_kokoro = {
        "en-US-GuyNeural": "am_eric",
        "en-US-ChristopherNeural": "am_eric",
        "en-US-BrianNeural": "am_eric",
    }
    kokoro_voice = _edge_to_kokoro.get(voice, voice)

    parts = [p.strip() for p in text.split(PAUSE_MARKER) if p.strip()]

    try:
        if len(parts) == 1:
            _synthesize_tts_wsl(parts[0], kokoro_voice, output_path)
            return

        # Multiple parts — synthesize each, concatenate with silence
        combined = AudioSegment.empty()
        for i, part in enumerate(parts):
            part_path = output_path.with_name(f"{output_path.stem}_part{i}.mp3")
            _synthesize_tts_wsl(part, kokoro_voice, part_path)
            combined += AudioSegment.from_file(str(part_path))
            part_path.unlink(missing_ok=True)
            if i < len(parts) - 1:
                combined += AudioSegment.silent(duration=pause_ms)
        combined.export(str(output_path), format="mp3")

    except Exception as wsl_exc:
        logger.warning("WSL TTS failed (%s), falling back to Edge TTS", wsl_exc)
        # Edge TTS fallback — use a fresh event loop per thread to avoid asyncio conflicts
        import edge_tts

        combined = AudioSegment.empty()
        for i, part in enumerate(parts):
            part_path = output_path.with_name(f"{output_path.stem}_edge{i}.mp3")
            errors: list = []

            def _run(p=part, pp=part_path):
                loop = asyncio.new_event_loop()
                try:
                    async def _inner():
                        c = edge_tts.Communicate(p, voice)
                        await c.save(str(pp))
                    loop.run_until_complete(_inner())
                except Exception as exc:
                    errors.append(exc)
                finally:
                    loop.close()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=60)
            if errors:
                raise errors[0]

            combined += AudioSegment.from_file(str(part_path))
            part_path.unlink(missing_ok=True)
            if i < len(parts) - 1:
                combined += AudioSegment.silent(duration=pause_ms)

        combined.export(str(output_path), format="mp3")


def build_intro(
    cfg: Dict[str, Any],
    base_path: Path,
    output_path: Path,
) -> Path:
    """Build the intro clip: music + announcer overlay with ducking."""
    intro_cfg = cfg.get("intro", DEFAULT_CONFIG["intro"])
    music_file = cfg.get("music_file", DEFAULT_CONFIG["music_file"])

    music_full = _load_music(music_file, base_path)

    clip_start = int(intro_cfg.get("clip_start_ms", 0))
    clip_dur = int(intro_cfg.get("clip_duration_ms", 14000))
    fade_in = int(intro_cfg.get("music_fade_in_ms", 1200))
    fade_out = int(intro_cfg.get("music_fade_out_ms", 2000))
    duck_start = int(intro_cfg.get("duck_start_ms", 4000))
    duck_db = float(intro_cfg.get("duck_db", -18))
    announcer_text = str(intro_cfg.get("announcer_text", DEFAULT_CONFIG["intro"]["announcer_text"]))
    announcer_voice = str(intro_cfg.get("announcer_voice", "en-US-GuyNeural"))
    silence_after = int(intro_cfg.get("silence_after_ms", 800))
    pause_ms = int(intro_cfg.get("pause_duration_ms", 700))

    # Clip music
    music = _clip(music_full, clip_start, clip_dur)
    music = music.fade_in(fade_in)

    # Duck music from duck_start onward
    pre_duck = music[:duck_start]
    post_duck = music[duck_start:].apply_gain(duck_db).fade_out(fade_out)
    music_ducked = pre_duck + post_duck

    # Synthesize announcer
    with tempfile.TemporaryDirectory() as td:
        ann_path = Path(td) / "intro_announcer.mp3"
        _synthesize_tts_edge_sync(announcer_text, announcer_voice, ann_path, pause_ms)
        announcer = AudioSegment.from_file(str(ann_path))

    # Extend music if announcer + duck_start exceeds music length
    needed = duck_start + len(announcer) + silence_after
    if needed > len(music_ducked):
        extra = AudioSegment.silent(needed - len(music_ducked))
        music_ducked = music_ducked + extra

    # Overlay announcer on ducked music
    intro = music_ducked.overlay(announcer, position=duck_start)

    # Trim to needed length and add trailing silence
    intro = intro[:needed]
    intro = intro + AudioSegment.silent(silence_after)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    intro.export(str(output_path), format="mp3")
    logger.info("Intro built: %s (%.1fs)", output_path, len(intro) / 1000)
    return output_path


def build_outro(
    cfg: Dict[str, Any],
    base_path: Path,
    output_path: Path,
    topic: str = "",
) -> Path:
    """Build the outro clip: announcer + music fade-in/out."""
    outro_cfg = cfg.get("outro", DEFAULT_CONFIG["outro"])
    music_file = cfg.get("music_file", DEFAULT_CONFIG["music_file"])

    music_full = _load_music(music_file, base_path)

    clip_start = int(outro_cfg.get("clip_start_ms", 0))
    clip_dur = int(outro_cfg.get("clip_duration_ms", 12000))
    fade_in = int(outro_cfg.get("music_fade_in_ms", 2000))
    fade_out = int(outro_cfg.get("music_fade_out_ms", 3000))
    announcer_text = str(outro_cfg.get("announcer_text", DEFAULT_CONFIG["outro"]["announcer_text"]))
    announcer_text = announcer_text.replace("{topic}", topic or "their next topic")
    announcer_voice = str(outro_cfg.get("announcer_voice", "en-US-GuyNeural"))
    silence_before = int(outro_cfg.get("silence_before_ms", 600))
    pause_ms = int(outro_cfg.get("pause_duration_ms", 700))

    # Clip music with fades
    music = _clip(music_full, clip_start, clip_dur)
    music = music.fade_in(fade_in).fade_out(fade_out)

    # Synthesize announcer
    with tempfile.TemporaryDirectory() as td:
        ann_path = Path(td) / "outro_announcer.mp3"
        _synthesize_tts_edge_sync(announcer_text, announcer_voice, ann_path, pause_ms)
        announcer = AudioSegment.from_file(str(ann_path))

    # Build: [silence] + [announcer] then music overlapping by fade_in at end of announcer
    pre_silence = AudioSegment.silent(silence_before)
    music_start_offset = silence_before + max(0, len(announcer) - fade_in)
    total_duration = music_start_offset + len(music)

    outro = AudioSegment.silent(total_duration)
    outro = outro.overlay(pre_silence + announcer, position=0)
    outro = outro.overlay(music, position=music_start_offset)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    outro.export(str(output_path), format="mp3")
    logger.info("Outro built: %s (%.1fs)", output_path, len(outro) / 1000)
    return output_path


def wrap_episode_audio(
    episode_audio_path: Path,
    output_path: Path,
    cfg: Dict[str, Any],
    base_path: Path,
    topic: str = "",
) -> Path:
    """Concatenate intro + episode audio + outro into a single MP3."""
    with tempfile.TemporaryDirectory() as td:
        intro_path = Path(td) / "intro.mp3"
        outro_path = Path(td) / "outro.mp3"

        build_intro(cfg, base_path, intro_path)
        build_outro(cfg, base_path, outro_path, topic=topic)

        intro_seg = AudioSegment.from_file(str(intro_path))
        episode_seg = AudioSegment.from_file(str(episode_audio_path))
        outro_seg = AudioSegment.from_file(str(outro_path))

        full = intro_seg + episode_seg + outro_seg
        output_path.parent.mkdir(parents=True, exist_ok=True)
        full.export(str(output_path), format="mp3", bitrate="192k")
        logger.info(
            "Wrapped episode: intro=%.1fs ep=%.1fs outro=%.1fs total=%.1fs",
            len(intro_seg) / 1000,
            len(episode_seg) / 1000,
            len(outro_seg) / 1000,
            len(full) / 1000,
        )

    return output_path
