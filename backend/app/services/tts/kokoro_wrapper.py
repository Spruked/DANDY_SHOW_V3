from typing import Dict

import torch

from ...core.settings import load_project_config, load_voices_config


def get_tts_runtime() -> Dict[str, str]:
    config = load_project_config()
    voices = load_voices_config()
    selected = config.get("tts", {}).get("primary_engine", "kokoro")
    return {
        "primary_engine": selected,
        "fallback_engine": "none",
        "device": "unverified",
        "runtime": "wsl_kokoro" if selected == "kokoro" else "qwen_bridge",
        "backend_device": "cuda" if torch.cuda.is_available() else "cpu",
        "voices_defined": str(len(voices)),
    }
