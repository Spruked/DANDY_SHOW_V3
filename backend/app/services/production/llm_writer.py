"""NVIDIA authoring transport with local evidence and strict dialogue validation."""
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from uuid import uuid4
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
logger = logging.getLogger(__name__)
_CONFIG = json.loads((Path(__file__).resolve().parents[4] / "config" / "writer.json").read_text(encoding="utf-8"))
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_LLAMACPP_BASE_URL = (os.getenv("DANDY_LLAMACPP_BASE_URL") or _CONFIG["base_url"]).rstrip("/")
_REQUIRED_MODEL_FILE = _CONFIG["required_model_file"]
_TIMEOUT = 120
_LAST_CALL_DIAGNOSTIC = {}
_USAGE = {"request_count": 0, "success_count": 0, "error_count": 0,
          "throttled_count": 0, "input_tokens": 0, "output_tokens": 0,
          "last_latency_ms": None, "last_model": None, "last_error": None}


def episode_request_settings():
    """Effective settings are visible in diagnostics and durable across launches."""
    return {
        "timeout_seconds": int(os.getenv("DANDY_NVIDIA_TIMEOUT_SECONDS", _CONFIG.get("nvidia_timeout_seconds", 600))),
        "max_retries": int(os.getenv("DANDY_NVIDIA_MAX_RETRIES", _CONFIG.get("nvidia_max_retries", 0))),
        "max_tokens": int(os.getenv("DANDY_NVIDIA_MAX_TOKENS", _CONFIG.get("nvidia_episode_max_tokens", 48000))),
        "reasoning_budget": int(_CONFIG.get("nvidia_episode_reasoning_budget", 2000)),
        "temperature": float(_CONFIG.get("nvidia_episode_temperature", 0.7)),
    }


def _save_episode_response(body: Dict, prompt: str, model: str, response_headers=None,
                           request_payload=None, endpoint=None, elapsed_seconds=None) -> None:
    """Save provider evidence before episode response validation rejects it."""
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    visible = message.get("content") or ""
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "request_id": (response_headers or {}).get("x-request-id") or body.get("id"),
        "finish_reason": choice.get("finish_reason"),
        "usage": body.get("usage") or {},
        "visible_response_characters": len(visible),
        "response": body,
        "prompt": prompt,
        "request_payload": request_payload,
        "endpoint": endpoint,
        "elapsed_seconds": elapsed_seconds,
    }
    debug_dir = _PROJECT_ROOT / "data" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    from ...core.safety import atomic_json
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    atomic_json(debug_dir / f"nemotron_episode_{stamp}_{uuid4().hex[:8]}.json", payload)
    atomic_json(debug_dir / "nemotron_last_episode_response.json", payload)


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


def _call_nvidia(prompt: str, kind: str = "short-copy", *, cancel_event=None, max_tokens_override=None) -> Optional[str]:
    """Explicit Nemotron authoring adapter; credentials remain process-local."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is required for the nvidia writer provider")
    endpoint = os.getenv("DANDY_NVIDIA_API_URL", _CONFIG.get("nvidia_base_url", "https://integrate.api.nvidia.com/v1")).rstrip("/")
    model = os.getenv("DANDY_NVIDIA_MODEL", _CONFIG.get("nvidia_model", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"))
    settings = episode_request_settings()
    timeout, retries = settings['timeout_seconds'], settings['max_retries']
    max_tokens = settings['max_tokens'] if kind == 'episode' else int(os.getenv('DANDY_NVIDIA_MAX_TOKENS', '12000'))
    if max_tokens_override is not None:
        max_tokens = min(max_tokens, max_tokens_override)
    payload = {"model": model, "temperature": 0.4 if kind != "episode" else settings['temperature'],
               "max_tokens": max_tokens,
               "messages": [{"role": "system", "content":
                   ("Write the complete episode at the requested length. Use supplied facts only. "
                    "Return only the JSON array requested." if kind == "episode" else
                    f"Write only a short {kind}. Use supplied facts only. Return plain copy.")},
                  {"role": "user", "content": prompt}], "stream": False}
    if kind == "episode":
        # Match the successful transition probe: positive budget alone keeps
        # provider reasoning separate from final dialogue (variant D).
        payload["reasoning_budget"] = settings['reasoning_budget']
        if max_tokens_override == 6000:
            payload['messages'][0]['content'] = (
                'Write only the requested eight-turn diagnostic dialogue sample, about 200 spoken words. '
                'Use the complete saved context for facts and canon. Full-episode duration instructions '
                'do not apply to this sample. Return only a complete JSON array with speaker, text, emotion, '
                'and numeric pause_after in seconds. No planning in dialogue.'
            )
    import time
    from urllib.error import HTTPError, URLError
    started = time.monotonic()
    _USAGE.update({"request_count": _USAGE["request_count"] + 1, "last_model": model, "last_error": None})
    for attempt in range(retries + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError('Generation cancelled; no script was activated')
        request = urllib.request.Request(endpoint + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode())
                if kind == "episode":
                    _save_episode_response(body, prompt, model, getattr(response, 'headers', None),
                                           payload, endpoint + '/chat/completions', time.monotonic() - started)
            usage = body.get("usage") or {}
            _USAGE.update({"input_tokens": _USAGE["input_tokens"] + int(usage.get("prompt_tokens", 0) or 0),
                           "output_tokens": _USAGE["output_tokens"] + int(usage.get("completion_tokens", 0) or 0),
                           "last_latency_ms": round((time.monotonic() - started) * 1000)})
            choice = (body.get("choices") or [{}])[0]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("Nemotron response was truncated")
            text = choice.get("message", {}).get("content", "").strip()
            if not text:
                raise RuntimeError("Nemotron response was empty")
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError('Generation cancelled; provider response captured without activating a script')
            _USAGE['success_count'] += 1
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
            _USAGE['last_latency_ms'] = round((time.monotonic() - started) * 1000)
            if attempt >= retries:
                raise RuntimeError(f"Nemotron request failed: {type(exc).__name__}") from exc
        except RuntimeError as exc:
            _USAGE['error_count'] += 1
            _USAGE['last_error'] = str(exc)
            raise
    raise RuntimeError("Nemotron request failed after bounded retries")


def generate_episode_script(context: str, *, target_words: int = 5000,
                            sample: bool = False, cancel_event=None) -> List[Dict]:
    """Generate a structured Phil/Jim episode from the saved context package."""
    prompt = f"""Write the complete Dandy Show episode from the source-grounded context below.
Return ONLY a complete JSON array. Each item must have exactly: speaker (phil or jim),
text (spoken dialogue string), emotion (string), pause_after (number of seconds from 0 to 3, e.g. 0.4).
Alternate speakers, use complete spoken sentences, and never include markdown, stage directions, citations,
or an analysis/thinking section in text. Do not invent facts beyond the supplied context. Target about
{int(target_words)} spoken words. Make the conversation feel natural, progressive, witty, and distinct.
Phil addresses Jim; Jim addresses Phil. Neither addresses himself by name. The brothers' biographies
do not establish product features. iOS/Android parity does not mean mobile/desktop parity.

CONTEXT PACKAGE:
{context}
"""
    if sample:
        prompt = ("DIAGNOSTIC SAMPLE: write exactly eight alternating turns, starting with phil, about 200 spoken words. "
                  "Full-episode duration and word-count instructions in the saved context do not apply to this sample. "
                  "Return only a complete JSON array with speaker, text, emotion, numeric pause_after.\n\n"
                  "CONTEXT PACKAGE:\n" + context)
    raw = _call_nvidia(prompt, kind="episode", cancel_event=cancel_event,
                       max_tokens_override=6000 if sample else None) or ""
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Nemotron returned non-JSON dialogue; raw evidence was retained") from exc
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("Nemotron returned an empty episode script")
    script = []
    expected = "phil"
    for index, item in enumerate(parsed, 1):
        if not isinstance(item, dict):
            raise RuntimeError(f'Dialogue turn {index} must be an object')
        if set(item) != {'speaker', 'text', 'emotion', 'pause_after'}:
            raise RuntimeError(f'Dialogue turn {index} has missing or unexpected fields')
        if not isinstance(item['text'], str) or not isinstance(item['emotion'], str):
            raise RuntimeError(f'Dialogue turn {index} requires text and emotion strings')
        speaker = str(item.get("speaker", "")).strip().lower()
        text = str(item.get("text", "")).strip()
        if speaker not in {"phil", "jim"} or not text:
            raise RuntimeError(f'Dialogue turn {index} has an invalid speaker or empty text')
        if speaker != expected:
            raise RuntimeError(f'Dialogue turn {index} must be {expected}; no turns were discarded')
        pause = item['pause_after']
        if isinstance(pause, bool) or not isinstance(pause, (int, float)) or not math.isfinite(pause) or not 0 <= pause <= 3:
            raise RuntimeError(f'Dialogue turn {index} requires a numeric pause from 0 to 3 seconds')
        if dialogue_issue(text):
            raise RuntimeError(f'Dialogue turn {index}: {dialogue_issue(text)}')
        script.append({"speaker": speaker, "text": text, "emotion": str(item.get("emotion", "neutral")),
                       "pause_after": float(pause),
                       "generated_by": "nemotron"})
        expected = "jim" if expected == "phil" else "phil"
    if len(script) < 4:
        raise RuntimeError("Nemotron returned too few valid alternating dialogue turns")
    if sample and len(script) != 8:
        raise RuntimeError('Diagnostic sample must contain exactly eight dialogue turns')
    words = sum(len(line['text'].split()) for line in script)
    if not sample and not target_words * 0.65 <= words <= target_words * 1.35:
        raise RuntimeError(f'Dialogue contains {words} words; expected approximately {target_words}. Raw evidence retained')
    from ..storage.episode_store import calculate_repetition_report
    if not calculate_repetition_report(script)['repetition_guard_passed']:
        raise RuntimeError('Repeated dialogue detected; raw evidence retained')
    for number, line in enumerate(script, 1):
        line["line_number"] = number
    return script


def nvidia_status() -> Dict[str, object]:
    return {"provider": "nvidia", "configured": bool(os.getenv("NVIDIA_API_KEY")),
            "model": os.getenv("DANDY_NVIDIA_MODEL", _CONFIG.get("nvidia_model")),
            "base_url": os.getenv("DANDY_NVIDIA_API_URL", _CONFIG.get("nvidia_base_url")),
            "episode_settings": episode_request_settings(), "usage": dict(_USAGE)}


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
    provider = os.getenv('DANDY_WRITER_PROVIDER', _CONFIG.get('provider', 'llamacpp'))
    if provider == 'nvidia':
        status = nvidia_status()
        return {'selected_provider': 'nvidia', 'writer_backend': 'nvidia',
                'active_writer': 'llm_bridge' if status['configured'] else 'offline',
                'bridge_reachable': status['configured'], 'availability_scope': 'credentials configured; provider inference is unverified',
                'bridge_url': status['base_url'], 'model': status['model'], 'nvidia': status,
                'allow_model_fallback': False,
                'warning': None if status['configured'] else 'NVIDIA_API_KEY is not configured'}
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
    """Return configured NVIDIA availability or verified local-model reachability."""
    return bool(writer_status()["bridge_reachable"])


def last_call_diagnostic():
    return dict(_LAST_CALL_DIAGNOSTIC)
