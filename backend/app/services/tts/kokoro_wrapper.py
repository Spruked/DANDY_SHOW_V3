from typing import Dict

import torch

from ...core.settings import load_project_config, load_voices_config


def get_tts_runtime() -> Dict[str, str]:
    config = load_project_config()
    voices = load_voices_config()
    preferred = config.get("tts", {}).get("preferred_device", "cpu")
    # Windows controller torch is not the Kokoro WSL or Qwen service runtime.
    device = "unverified"
    return {
        "primary_engine": config.get("tts", {}).get("primary_engine", "kokoro"),
        "fallback_engine": config.get("tts", {}).get("fallback_engine", "edge"),
        "device": device,
        "configured_device": preferred,
        "runtime_route": "wsl" if config.get("tts", {}).get("primary_engine", "kokoro") == "kokoro" else "qwen_bridge",
        "controller_cuda_available": torch.cuda.is_available(),
        "voices_defined": str(len(voices)),
    }

