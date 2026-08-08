from typing import Dict

import torch

from ...core.settings import load_project_config, load_voices_config


def get_tts_runtime() -> Dict[str, str]:
    config = load_project_config()
    voices = load_voices_config()
    preferred = config.get("tts", {}).get("preferred_device", "cpu")
    device = preferred if preferred == "cuda" and torch.cuda.is_available() else "cpu"
    return {
        "primary_engine": config.get("tts", {}).get("primary_engine", "kokoro"),
        "fallback_engine": config.get("tts", {}).get("fallback_engine", "edge"),
        "device": device,
        "voices_defined": str(len(voices)),
    }

