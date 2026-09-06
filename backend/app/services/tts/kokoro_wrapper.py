from typing import Dict

from ...core.settings import load_project_config, load_voices_config


def get_tts_runtime() -> Dict[str, str]:
    config = load_project_config()
    voices = load_voices_config()
    selected = config.get("tts", {}).get("primary_engine", "kokoro")
    return {
        "primary_engine": selected,
        "fallback_engine": "none",
        "device": "unverified",
        "runtime": "wsl_kokoro" if selected == "kokoro" else ("qwen_bridge" if selected == "qwen" else "voice_forge_xtts"),
        "backend_device": "managed_by_selected_engine",
        "voices_defined": str(len(voices)),
    }
