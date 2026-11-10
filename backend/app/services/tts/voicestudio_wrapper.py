"""Voice Studio (OmniVoice) OpenAI-compatible local TTS adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from pydub import AudioSegment


def synthesize(base_url: str, voice: str, text: str, output_path: Path,
               instructions: str | None = None, speed: float | None = None) -> Path:
    payload = {
        "model": "omnivoice",
        "voice": voice,
        "input": text,
        "response_format": "wav",
    }
    if instructions:
        payload["instructions"] = instructions
    if speed is not None:
        payload["speed"] = speed
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            audio_bytes = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Voice Studio request failed: {exc}") from exc
    if not audio_bytes:
        raise RuntimeError("Voice Studio returned empty audio")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_wav = output_path.with_suffix(".voicestudio.wav")
    temp_wav.write_bytes(audio_bytes)
    try:
        AudioSegment.from_file(str(temp_wav), format="wav").export(
            str(output_path), format=output_path.suffix.lstrip(".") or "mp3"
        )
    finally:
        temp_wav.unlink(missing_ok=True)
    if not output_path.is_file() or not output_path.stat().st_size:
        raise RuntimeError("Voice Studio did not produce audio")
    return output_path
