"""Pinned local model transport. Episode-writing implementation is archived.

The supported writing interface is authoring.short_copy: ads and short posts.
Legacy episode entry points raise an explicit migration error.
"""
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
logger = logging.getLogger(__name__)
_CONFIG = json.loads((Path(__file__).resolve().parents[4] / "config" / "writer.json").read_text(encoding="utf-8"))
_LLAMACPP_BASE_URL = (os.getenv("DANDY_LLAMACPP_BASE_URL") or _CONFIG["base_url"]).rstrip("/")
_REQUIRED_MODEL_FILE = _CONFIG["required_model_file"]
_TIMEOUT = 120
_LAST_CALL_DIAGNOSTIC = {}


def _verified_model() -> str:
    """Resolve the pinned GGUF from the live server; reject other models."""
    with urllib.request.urlopen(f"{_LLAMACPP_BASE_URL}/models", timeout=3) as response:
        models = json.loads(response.read().decode()).get("data", [])
    for model in models:
        model_id = str(model.get("id", ""))
        filename = model_id.replace("\\", "/").rsplit("/", 1)[-1]
        if filename.lower() == _REQUIRED_MODEL_FILE.lower():
            return model_id
    raise RuntimeError(f"Required Qwen2.5-7B-Instruct Q4_K_M model is not loaded: {_REQUIRED_MODEL_FILE}")


def _post_json(url: str, payload: Dict, timeout: int = _TIMEOUT) -> Dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _call_llamacpp(prompt: str, n_exchanges: int | None = None) -> Optional[str]:
    model_id = _verified_model()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write short advertising or social copy only. Use supplied facts. "
                    "Do not write full episodes. No commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.6,
        "top_p": 0.9,
        "max_tokens": 1800,
    }
    try:
        body = _post_json(f"{_LLAMACPP_BASE_URL}/chat/completions", payload)
        choice = (body.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            _LAST_CALL_DIAGNOSTIC.update(status="truncated", error="Writer hit its token limit")
            return None
        return (
            (body.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception as exc:
        logger.warning("llama.cpp writer call failed: %s", exc)
        return None


def _call_bridge(prompt: str, n_exchanges: int | None = None) -> Tuple[Optional[str], str]:
    llamacpp = _call_llamacpp(prompt, n_exchanges=n_exchanges)
    _LAST_CALL_DIAGNOSTIC.update({"backend": "llamacpp", "empty": not bool(llamacpp), "raw_characters": len(llamacpp or "")})
    if llamacpp:
        return llamacpp, "llamacpp"
    return None, ""


def generate_segment(
    topic: str,
    key_points: List[str],
    stage: str,
    history_lines: List[str],
    primary_source_summary: str = "",
    n_exchanges: Optional[int] = None,
    persona_brief: str = "",
    generation_nonce: Optional[str] = None,
    production_brief: str = "",
) -> List[Dict]:
    raise RuntimeError("The local writer is reserved for ads and short posts. Episode dialogue must be imported.")


def dialogue_issue(text: str) -> str | None:
    text = str(text or "").strip()
    if text.lower() in {"complete dialogue.", "your original dialogue."}:
        return "placeholder dialogue"
    if re.search(r"(?i)(?:\b|(?<=[.!?]))(?:inde|indle)\b", text):
        return "stray Inde/indle decoding fragment"
    if not re.search(r"[.!?][\"')]*$", text):
        return "unfinished sentence"
    if re.search(r"(?i)\b(?:and|or|but|because|with|into|the|a|an|to)\s*[.!?]$", text):
        return "unfinished trailing phrase"
    return None


def regenerate_section(script: List[Dict], start: int, end: int, topic: str,
                       instructions: str = "", source_context: str = "") -> List[Dict]:
    raise RuntimeError("The local writer is reserved for ads and short posts. Episode dialogue must be imported.")


def writer_status() -> Dict[str, object]:
    model_id = None
    warning = None
    try:
        model_id = _verified_model()
    except Exception as exc:
        warning = f"Required Qwen writer unavailable; generation is blocked: {exc}"
    return {
        "bridge_reachable": model_id is not None,
        "active_writer": "llm_bridge" if model_id else "offline",
        "writer_backend": "llamacpp" if model_id else "offline",
        "bridge_url": _LLAMACPP_BASE_URL,
        "llamacpp_url": _LLAMACPP_BASE_URL,
        "model": model_id,
        "required_model": "Qwen2.5-7B-Instruct Q4_K_M",
        "allow_model_fallback": False,
        "warning": warning,
    }


def check_bridge() -> bool:
    """Return True only when the required Qwen model is served."""
    return bool(writer_status()["bridge_reachable"])


def last_call_diagnostic():
    return dict(_LAST_CALL_DIAGNOSTIC)
