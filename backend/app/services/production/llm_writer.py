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
_USAGE = {"request_count": 0, "success_count": 0, "error_count": 0,
          "throttled_count": 0, "input_tokens": 0, "output_tokens": 0,
          "last_latency_ms": None, "last_model": None, "last_error": None}


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


def _call_nvidia(prompt: str, kind: str = "short-copy") -> Optional[str]:
    """Explicit Nemotron authoring adapter; credentials remain process-local."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is required for the nvidia writer provider")
    endpoint = os.getenv("DANDY_NVIDIA_API_URL", _CONFIG.get("nvidia_base_url", "https://integrate.api.nvidia.com/v1")).rstrip("/")
    model = os.getenv("DANDY_NVIDIA_MODEL", _CONFIG.get("nvidia_model", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"))
    timeout = int(os.getenv("DANDY_NVIDIA_TIMEOUT_SECONDS", _CONFIG.get("nvidia_timeout_seconds", 60)))
    retries = int(os.getenv("DANDY_NVIDIA_MAX_RETRIES", _CONFIG.get("nvidia_max_retries", 1)))
    max_tokens = int(os.getenv("DANDY_NVIDIA_MAX_TOKENS", "12000"))
    payload = {"model": model, "temperature": 0.4 if kind != "episode" else 0.7,
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content":
                   f"Write only a short {kind}. Use supplied facts only. Return plain copy."},
                  {"role": "user", "content": prompt}], "stream": False}
    import time
    from urllib.error import HTTPError, URLError
    started = time.monotonic()
    _USAGE.update({"request_count": _USAGE["request_count"] + 1, "last_model": model, "last_error": None})
    for attempt in range(retries + 1):
        request = urllib.request.Request(endpoint + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode())
            usage = body.get("usage") or {}
            _USAGE.update({"success_count": _USAGE["success_count"] + 1,
                           "input_tokens": _USAGE["input_tokens"] + int(usage.get("prompt_tokens", 0) or 0),
                           "output_tokens": _USAGE["output_tokens"] + int(usage.get("completion_tokens", 0) or 0),
                           "last_latency_ms": round((time.monotonic() - started) * 1000)})
            choice = (body.get("choices") or [{}])[0]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("Nemotron response was truncated")
            text = choice.get("message", {}).get("content", "").strip()
            if not text:
                raise RuntimeError("Nemotron response was empty")
            return text
        except HTTPError as exc:
            if exc.code == 429:
                _USAGE["throttled_count"] += 1
            _USAGE["error_count"] += 1
            _USAGE["last_error"] = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise RuntimeError(f"Nemotron request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            _USAGE["error_count"] += 1
            _USAGE["last_error"] = type(exc).__name__
            if attempt >= retries:
                raise RuntimeError(f"Nemotron request failed: {type(exc).__name__}") from exc
    raise RuntimeError("Nemotron request failed after bounded retries")


def generate_episode_script(context: str, *, target_words: int = 5000) -> List[Dict]:
    """Generate a structured Phil/Jim episode from the saved context package."""
    prompt = f"""Write the complete Dandy Show episode from the source-grounded context below.
Return ONLY a JSON array. Each item must have exactly: speaker (phil or jim), text, emotion, pause_after.
Alternate speakers, use complete spoken sentences, and never include markdown, stage directions, citations,
or an analysis/thinking section in text. Do not invent facts beyond the supplied context. Target about
{max(600, int(target_words))} spoken words. Make the conversation feel natural, progressive, witty, and distinct.

CONTEXT PACKAGE:
{context}
"""
    raw = _call_nvidia(prompt, kind="episode") or ""
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        match = re.search(r"\[.*\]", candidate, flags=re.S)
        if not match:
            raise RuntimeError("Nemotron returned non-JSON episode script") from exc
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("Nemotron returned an empty episode script")
    script = []
    expected = "phil"
    for item in parsed:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker", "")).strip().lower()
        text = str(item.get("text", "")).strip()
        if speaker not in {"phil", "jim"} or not text:
            continue
        if speaker != expected:
            continue
        script.append({"speaker": speaker, "text": text, "emotion": str(item.get("emotion", "neutral")),
                       "pause_after": float(item.get("pause_after", 0.4) or 0.4),
                       "generated_by": "nemotron"})
        expected = "jim" if expected == "phil" else "phil"
    if len(script) < 4:
        raise RuntimeError("Nemotron returned too few valid alternating dialogue turns")
    for number, line in enumerate(script, 1):
        line["line_number"] = number
    return script


def nvidia_status() -> Dict[str, object]:
    return {"provider": "nvidia", "configured": bool(os.getenv("NVIDIA_API_KEY")),
            "model": os.getenv("DANDY_NVIDIA_MODEL", _CONFIG.get("nvidia_model")),
            "base_url": os.getenv("DANDY_NVIDIA_API_URL", _CONFIG.get("nvidia_base_url")),
            "usage": dict(_USAGE)}


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
    provider = os.getenv("DANDY_WRITER_PROVIDER", _CONFIG.get("provider", "llamacpp"))
    result = {
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
    if provider == "nvidia":
        result.update({"selected_provider": "nvidia", "nvidia": nvidia_status(),
                       "bridge_reachable": bool(os.getenv("NVIDIA_API_KEY")),
                       "writer_backend": "nvidia", "warning": None if os.getenv("NVIDIA_API_KEY") else "NVIDIA_API_KEY is not configured"})
    else:
        result["selected_provider"] = "llamacpp"
    return result


def check_bridge() -> bool:
    """Return True only when the required Qwen model is served."""
    return bool(writer_status()["bridge_reachable"])


def last_call_diagnostic():
    return dict(_LAST_CALL_DIAGNOSTIC)
