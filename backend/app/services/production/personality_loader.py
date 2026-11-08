import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict


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


def load_personality(personality: str) -> Any:
    import torch
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

    module = _load_module_from_path(f"merged_{personality_key}_skg", file_path)
    klass = getattr(module, class_name)

    try:
        return klass(PROJECT_ROOT, enable_gpu=torch.cuda.is_available())
    except TypeError:
        return klass(PROJECT_ROOT)
