import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch

from ...core.paths import PROJECT_ROOT
from ...core.settings import load_voices_config


DEFAULT_CLASS_NAMES = {
    "phil": "PhilDandySKG",
    "jim": "JimDandySKG",
}


def _load_module_from_path(module_name: str, file_path: Path):
    module_parent = str(file_path.resolve().parent)
    project_root = str(PROJECT_ROOT.resolve())
    for candidate in (module_parent, project_root):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ensure_sentence_transformers_stub() -> None:
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        return
    except Exception:
        pass

    stub_module = types.ModuleType("sentence_transformers")

    class SentenceTransformer:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def encode(self, value, *args, **kwargs):
            if isinstance(value, list):
                return [self.encode(item, *args, **kwargs) for item in value]
            text = str(value)
            vector = np.zeros(16, dtype=float)
            if not text:
                return vector
            for idx, char in enumerate(text.encode("utf-8")[:16]):
                vector[idx] = (char % 31) / 31.0
            return vector

    stub_module.SentenceTransformer = SentenceTransformer
    sys.modules["sentence_transformers"] = stub_module


def load_personality(personality: str) -> Any:
    voices = load_voices_config()
    personality_key = personality.lower()
    voice_payload: Dict[str, Any] = voices.get(personality_key, {})
    relative_path = voice_payload.get("character_file")
    if not relative_path:
        raise FileNotFoundError(f"No character_file configured for {personality_key}")

    file_path = (PROJECT_ROOT / relative_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Character file not found: {file_path}")

    class_name = DEFAULT_CLASS_NAMES.get(personality_key)
    if not class_name:
        raise ValueError(f"Unsupported personality: {personality_key}")

    _ensure_sentence_transformers_stub()
    module = _load_module_from_path(f"merged_{personality_key}_skg", file_path)
    klass = getattr(module, class_name)

    try:
        return klass(PROJECT_ROOT, enable_gpu=torch.cuda.is_available())
    except TypeError:
        return klass(PROJECT_ROOT)
