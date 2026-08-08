import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from .paths import CONFIG_ROOT


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_project_config() -> Dict[str, Any]:
    return _load_json(CONFIG_ROOT / "config.json")


@lru_cache(maxsize=1)
def load_voices_config() -> Dict[str, Any]:
    return _load_json(CONFIG_ROOT / "voices.json")


@lru_cache(maxsize=1)
def load_qwen_tts_config() -> Dict[str, Any]:
    return _load_json(CONFIG_ROOT / "qwen_tts.json")


def clear_settings_cache() -> None:
    load_project_config.cache_clear()
    load_voices_config.cache_clear()
    load_qwen_tts_config.cache_clear()
