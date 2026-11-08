from typing import Dict


from ...core.settings import load_project_config, load_voices_config, load_qwen_tts_config


def get_tts_runtime() -> Dict[str, str]:
    config = load_project_config()
    voices = load_voices_config()
    preferred = config.get("tts", {}).get("preferred_device", "cpu")
    try:
        import torch
        device = preferred if preferred == "cuda" and torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "external_service"
    required = load_qwen_tts_config().get("production", {}).get("required_engine")
    return {
        "primary_engine": required or config.get("tts", {}).get("primary_engine", "kokoro"),
        "fallback_engine": "disabled" if required else config.get("tts", {}).get("fallback_engine", "edge"),
        "device": device,
        "voices_defined": str(len(voices)),
    }

