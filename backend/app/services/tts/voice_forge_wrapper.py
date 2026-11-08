"""Local Voice Forge 2.0 adapter for Dandy production."""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, Dict

from ...core.paths import PROJECT_ROOT

VOICE_FORGE_ROOT = PROJECT_ROOT / "voice_forge_2.0"
_MIN_EMBEDDING_BYTES = 1024
_synthesizer: Any | None = None
_lock = threading.Lock()


def voice_forge_status() -> Dict[str, Any]:
    embeddings = VOICE_FORGE_ROOT / "embeddings"
    valid_embeddings = sorted(
        path.stem.removesuffix("_voice")
        for path in embeddings.glob("*_voice.pt")
        if path.stat().st_size >= _MIN_EMBEDDING_BYTES
    ) if embeddings.is_dir() else []
    issues = []
    if not VOICE_FORGE_ROOT.is_dir():
        issues.append("voice_forge_2.0 directory is missing")
    if importlib.util.find_spec("TTS") is None:
        issues.append("Coqui TTS is not installed in the Dandy Python environment")
    if not valid_embeddings:
        issues.append("no valid minted Voice Forge embeddings are available")
    return {"engine": "voice_forge", "root": str(VOICE_FORGE_ROOT), "ready": not issues,
            "valid_embeddings": valid_embeddings, "issues": issues}


def synthesize(character: str, text: str, output_path: Path) -> Path:
    status = voice_forge_status()
    if not status["ready"]:
        raise RuntimeError("Voice Forge is not ready: " + "; ".join(status["issues"]))
    global _synthesizer
    with _lock:
        if _synthesizer is None:
            sys.path.insert(0, str(VOICE_FORGE_ROOT))
            try:
                from synthesize import VoiceSynthesizer
                _synthesizer = VoiceSynthesizer()
            finally:
                if sys.path and sys.path[0] == str(VOICE_FORGE_ROOT):
                    sys.path.pop(0)
        produced = _synthesizer.synthesize(character, text, output_path=output_path)
    if not produced or not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Voice Forge did not produce audio")
    return output_path
