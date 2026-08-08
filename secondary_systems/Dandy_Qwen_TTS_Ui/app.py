from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import gradio as gr
from gradio_client import Client


APP_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = APP_ROOT / "generated_audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_OPTIONS = {
    "Auto-detect live backend": "auto",
    "CustomVoice - built-in voices (8031)": "http://127.0.0.1:8031",
    "VoiceClone/Base - clone UI (8032)": "http://127.0.0.1:8032",
    "VoiceDesign - design UI (8033)": "http://127.0.0.1:8033",
}

BACKEND_ORDER = [
    url.strip().rstrip("/")
    for url in os.getenv(
        "DANDY_QWEN_BACKENDS",
        "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033",
    ).split(",")
    if url.strip()
]

for option_url in (
    "http://127.0.0.1:8031",
    "http://127.0.0.1:8032",
    "http://127.0.0.1:8033",
):
    if option_url not in BACKEND_ORDER:
        BACKEND_ORDER.append(option_url)

LANGUAGES = [
    "English",
    "Auto",
    "German",
    "Italian",
    "Portuguese",
    "Spanish",
    "Japanese",
    "Korean",
    "French",
    "Russian",
]

SPEAKERS = [
    "Ryan",
    "Aiden",
    "Uncle Fu",
    "Eric",
    "Dylan",
    "Vivian",
    "Serena",
    "Ono Anna",
    "Sohee",
]

VOICE_PRESETS = {
    "Phil candidate - Ryan": {
        "speaker": "Ryan",
        "instruction": "Warm American male voice, dry wit, relaxed podcast pacing, natural pauses, confident but not announcer-like.",
    },
    "Phil candidate - Aiden": {
        "speaker": "Aiden",
        "instruction": "Clear American male voice, thoughtful and friendly, conversational timing, light humor, steady midrange.",
    },
    "Jim candidate - Ryan": {
        "speaker": "Ryan",
        "instruction": "Dynamic American male voice, faster comedic timing, skeptical but warm, responsive conversational cadence.",
    },
    "Jim candidate - Eric": {
        "speaker": "Eric",
        "instruction": "Lively male voice, slightly raspy brightness, quick reactions, playful brotherly cadence.",
    },
    "Announcer candidate": {
        "speaker": "Ryan",
        "instruction": "Classic radio announcer delivery, clean articulation, upbeat but controlled, brief dramatic emphasis.",
    },
}


def _client(backend_url: str) -> Client:
    return Client(str(backend_url).strip().rstrip("/"))


def _normalize_url(backend_url: str) -> str:
    return str(backend_url or "").strip().rstrip("/")


def _backend_alive(backend_url: str) -> bool:
    backend_url = _normalize_url(backend_url)
    if not backend_url:
        return False
    try:
        with urlopen(backend_url, timeout=1.5) as response:
            return response.status < 500
    except (OSError, URLError, ValueError):
        return False


def _detect_backend() -> str:
    env_backend = _normalize_url(os.getenv("DANDY_QWEN_GRADIO_URL", ""))
    if env_backend and _backend_alive(env_backend):
        return env_backend

    for backend_url in BACKEND_ORDER:
        if _backend_alive(backend_url):
            return backend_url

    return env_backend or BACKEND_ORDER[0]


def _backend_kind(backend_url: str) -> str:
    backend_url = _normalize_url(backend_url)
    if backend_url.endswith(":8031"):
        return "custom"
    if backend_url.endswith(":8032"):
        return "clone"
    if backend_url.endswith(":8033"):
        return "design"
    return "unknown"


DEFAULT_BACKEND = _detect_backend()


def _copy_generated_audio(source: str, speaker: str) -> str:
    src = Path(source)
    if not src.exists():
        raise FileNotFoundError(f"Generated audio path does not exist: {src}")

    safe_speaker = "".join(ch.lower() if ch.isalnum() else "_" for ch in speaker).strip("_") or "voice"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = OUTPUT_DIR / f"{stamp}_{safe_speaker}{src.suffix or '.wav'}"
    shutil.copyfile(src, target)
    return str(target)


def _extract_audio_path(result: Any) -> str:
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
    else:
        first = result

    if isinstance(first, dict):
        path = first.get("path") or first.get("name")
    else:
        path = str(first) if first else ""

    if not path:
        raise RuntimeError(f"No audio path returned from Qwen backend: {result!r}")
    return path


def backend_status(backend_url: str) -> str:
    backend_url = _normalize_url(backend_url)
    if not _backend_alive(backend_url):
        live_backend = _detect_backend()
        if live_backend != backend_url and _backend_alive(live_backend):
            return f"No listener at {backend_url}. Live Qwen backend detected at {live_backend}."
        return f"No listener at {backend_url}."

    kind = _backend_kind(backend_url)
    if kind == "custom":
        return f"Connected to CustomVoice at {backend_url}. Wrapper Generate is available."
    if kind == "clone":
        return f"Connected to VoiceClone/Base at {backend_url}. Use the direct clone UI there."
    if kind == "design":
        return f"Connected to VoiceDesign at {backend_url}. Use the direct design UI there."
    return f"Connected to Qwen backend at {backend_url}."


def select_backend(mode: str):
    target = BACKEND_OPTIONS.get(mode, "auto")
    backend_url = _detect_backend() if target == "auto" else target
    return backend_url, backend_status(backend_url)


def apply_preset(preset: str):
    data = VOICE_PRESETS.get(preset) or {}
    return data.get("speaker", "Ryan"), data.get("instruction", "")


def synthesize(
    text: str,
    language: str,
    speaker: str,
    instruction: str,
    backend_url: str,
):
    text = (text or "").strip()
    if not text:
        return None, "", "Text is required."

    backend_url = _normalize_url(backend_url or _detect_backend())
    kind = _backend_kind(backend_url)

    if not _backend_alive(backend_url):
        live_backend = _detect_backend()
        if live_backend != backend_url and _backend_alive(live_backend):
            return None, "", f"No listener at {backend_url}. Live Qwen backend detected at {live_backend}."
        return None, "", f"No listener at {backend_url}."

    if kind == "clone":
        return None, "", f"VoiceClone/Base is live at {backend_url}. Use that direct UI for cloning and cloned-voice generation."

    if kind == "design":
        return None, "", f"VoiceDesign is live at {backend_url}. Use that direct UI for voice design generation."

    try:
        client = _client(backend_url)
        result = client.predict(
            text=text,
            lang_disp=language or "English",
            spk_disp=speaker or "Ryan",
            instruct=(instruction or "").strip(),
            api_name="/run_instruct",
        )
        generated_path = _extract_audio_path(result)
        saved_path = _copy_generated_audio(generated_path, speaker or "voice")
        status = {
            "backend": backend_url,
            "speaker": speaker,
            "language": language,
            "saved_audio": saved_path,
            "raw_backend_result": result,
        }
        return saved_path, saved_path, json.dumps(status, indent=2)
    except Exception as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


CSS = """
.gradio-container { max-width: none !important; }
#status_box textarea { font-family: Consolas, monospace; font-size: 12px; }
"""


with gr.Blocks(title="Dandy Qwen TTS", css=CSS) as demo:
    gr.Markdown("# Dandy Qwen TTS")

    with gr.Row():
        backend_mode = gr.Dropdown(
            label="Backend mode",
            choices=list(BACKEND_OPTIONS.keys()),
            value="Auto-detect live backend",
            scale=2,
        )
        backend = gr.Textbox(label="Qwen backend", value=DEFAULT_BACKEND, scale=3)
        check = gr.Button("Check", scale=1)

    status = gr.Textbox(label="Backend status", lines=2, elem_id="status_box")

    with gr.Row():
        with gr.Column(scale=2):
            text = gr.Textbox(
                label="Text",
                lines=8,
                value="Welcome back to the Phil and Jim Dandy Show. Today we are testing the new Qwen voices.",
            )
            preset = gr.Dropdown(
                label="Voice preset",
                choices=list(VOICE_PRESETS.keys()),
                value="Phil candidate - Ryan",
            )
            with gr.Row():
                language = gr.Dropdown(label="Language", choices=LANGUAGES, value="English")
                speaker = gr.Dropdown(label="Speaker", choices=SPEAKERS, value="Ryan")
            instruction = gr.Textbox(
                label="Instruction",
                lines=3,
                value=VOICE_PRESETS["Phil candidate - Ryan"]["instruction"],
            )
            generate = gr.Button("Generate", variant="primary")

        with gr.Column(scale=2):
            audio = gr.Audio(label="Generated audio", type="filepath", autoplay=True)
            saved_path = gr.Textbox(label="Saved file")
            detail = gr.Textbox(label="Result detail", lines=10, elem_id="status_box")

    backend_mode.change(select_backend, inputs=[backend_mode], outputs=[backend, status])
    check.click(backend_status, inputs=[backend], outputs=[status])
    preset.change(apply_preset, inputs=[preset], outputs=[speaker, instruction])
    generate.click(
        synthesize,
        inputs=[text, language, speaker, instruction, backend],
        outputs=[audio, saved_path, detail],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(
        server_name=os.getenv("DANDY_QWEN_UI_HOST", "127.0.0.1"),
        server_port=int(os.getenv("DANDY_QWEN_UI_PORT", "7861")),
        share=False,
        pwa=True,
    )
