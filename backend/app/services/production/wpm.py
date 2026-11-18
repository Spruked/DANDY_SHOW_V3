"""Rendered delivery measurements, excluding inter-turn silence."""
from __future__ import annotations

import re
from typing import Iterable


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def spoken_wpm(words: int, audio_seconds: float) -> float:
    if words <= 0 or audio_seconds <= 0:
        raise ValueError("words and audio_seconds must be positive")
    return words / (audio_seconds / 60.0)


def measure_turn(text: str, audio_seconds: float) -> dict:
    words = word_count(text)
    return {"words": words, "audio_seconds": round(float(audio_seconds), 3), "spoken_wpm": round(spoken_wpm(words, audio_seconds), 1)}


def measure_turns(turns: Iterable[dict]) -> dict:
    total_words = 0
    total_seconds = 0.0
    for turn in turns:
        total_words += word_count(str(turn.get("text", "")))
        total_seconds += float(turn.get("audio_seconds", 0) or 0)
    return {"words": total_words, "audio_seconds": round(total_seconds, 3), "spoken_wpm": round(spoken_wpm(total_words, total_seconds), 1) if total_words and total_seconds else None}


def measure_audio_file(text: str, audio_path: str, silence_dbfs: float = -42.0, min_silence_ms: int = 80) -> dict:
    """Measure a rendered turn while excluding leading/trailing/internal silence."""
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    audio = AudioSegment.from_file(audio_path)
    spans = detect_nonsilent(audio, min_silence_len=min_silence_ms, silence_thresh=silence_dbfs)
    spoken_ms = sum(end - start for start, end in spans)
    return measure_turn(text, spoken_ms / 1000.0)
