"""
llm_writer.py — LLM script writer for Phil & Jim Dandy Show.

All generated dialogue and rewrites use the required local Qwen2.5-7B-Instruct
Q4_K_M model through llama.cpp. No alternate model provider is used.
SKG supplies persona guidance; it does not replace model-generated dialogue.
"""

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

_CONFIG = json.loads((Path(__file__).resolve().parents[4] / "config" / "writer.json").read_text(encoding="utf-8"))
_LLAMACPP_BASE_URL = os.getenv("DANDY_LLAMACPP_BASE_URL") or _CONFIG["base_url"]
_LLAMACPP_BASE_URL = _LLAMACPP_BASE_URL.rstrip("/")
_REQUIRED_MODEL_FILE = _CONFIG["required_model_file"]
_TIMEOUT = 120


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


_STAGES: Dict[str, Dict] = {
    "opening": {
        "goal": "Phil opens with genuine curiosity about the topic. Jim grounds it with a practical question.",
        "n": 4,
    },
    "expansion": {
        "goal": "Phil finds new connections and specific examples. Jim challenges with 'show me' skepticism. Ideas advance — nothing repeated.",
        "n": 6,
    },
    "deepening": {
        "goal": "Go underneath the surface. Phil finds the unexpected angle. Jim challenges the core assumption underneath.",
        "n": 6,
    },
    "reflection": {
        "goal": "Phil reflects on what this means for real people. Jim brings something concrete and honest.",
        "n": 4,
    },
    "closing": {
        "goal": "Phil synthesizes the thread. Jim gives his final, honest, grounded take.",
        "n": 3,
    },
}

# Matches: PHIL [excited]: text, JIM [dry]: text, or PHIL: text.
_LINE_RE = re.compile(r"^(PHIL|JIM)(?:\s*\[([^\]]{2,20})\])?:\s*(.{8,})$", re.IGNORECASE)
_SPEAKER_MAP = {"phil": "Phil", "jim": "Jim"}
_PAUSE_MAP = {"Phil": 0.35, "Jim": 0.55}


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


def _call_llamacpp(prompt: str) -> Optional[str]:
    model_id = _verified_model()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write only Phil and Jim Dandy dialogue in the exact "
                    "line format requested. No headers, no commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1800,
    }
    try:
        body = _post_json(f"{_LLAMACPP_BASE_URL}/chat/completions", payload)
        return (
            (body.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception as exc:
        logger.warning("llama.cpp writer call failed: %s", exc)
        return None


def _call_bridge(prompt: str) -> Tuple[Optional[str], str]:
    llamacpp = _call_llamacpp(prompt)
    if llamacpp:
        return llamacpp, "llamacpp"
    return None, ""


def _parse_response(text: str, generated_by: str) -> List[Dict]:
    lines = []
    for raw in (text or "").strip().splitlines():
        m = _LINE_RE.match(raw.strip())
        if not m:
            continue
        speaker_raw = m.group(1)
        emotion = (m.group(2) or "thoughtful").lower().strip()
        dialogue = m.group(3).strip().strip('"')
        speaker = _SPEAKER_MAP.get(speaker_raw.lower(), speaker_raw.capitalize())
        lines.append(
            {
                "speaker": speaker,
                "text": dialogue,
                "emotional_state": {"primary": emotion},
                "pause_after": _PAUSE_MAP.get(speaker, 0.45),
                "timestamp": datetime.now().isoformat(),
                "generated_by": generated_by or "llm_writer",
            }
        )
    return lines


_CHARACTERS = """\
CHARACTERS:
Phil Dandridge — younger brother, the idea engine. Thinks out loud, builds \
connections mid-sentence, tangential, enthusiastic. Uses "wait—", "okay but—", \
"here's the thing". 20-50 words per turn.
Jim Dandridge — older brother, the grounding force. Pragmatic, dry wit, short \
punchy skepticism. Uses "yeah but", "hold on", "show me". 10-25 words per turn."""


def _build_prompt(
    topic: str,
    key_points: List[str],
    stage: str,
    stage_info: Dict,
    history_lines: List[str],
    primary_source_summary: str,
    n_exchanges: int,
    persona_brief: str = "",
    generation_nonce: str = "",
) -> str:
    kp_block = (
        "\n".join(f"- {kp}" for kp in key_points[:8])
        if key_points
        else f"- {topic}"
    )
    history_block = (
        "\n".join(history_lines[-20:])
        if history_lines
        else "(none yet — this is the opening)"
    )
    source_block = (
        f"\nPrimary source — use specific details from this:\n{primary_source_summary[:800]}"
        if primary_source_summary
        else ""
    )

    persona_block = (
        f"\nPERSONA / SKG RULEBOOK:\n{persona_brief[:1800]}\n"
        if persona_brief
        else ""
    )
    nonce = generation_nonce or f"fresh-{datetime.now().isoformat()}-{uuid4().hex[:8]}"

    return f"""{_CHARACTERS}{persona_block}

PRODUCTION BRIEF:
- Topic and key points below are the source of truth — stay within them
- Stage goal: {stage_info["goal"]}
- Do not invent facts outside the source material
- Do not repeat any line already in the conversation
- Generation ID: {nonce}
- This is a fresh script pass. Write new dialogue for this request.
- Use the persona/SKG rulebook as constraints only; do not quote or copy template lines from it.

TOPIC: {topic}

KEY POINTS (stay within these):
{kp_block}
{source_block}

CONVERSATION SO FAR:
{history_block}

STAGE: {stage}

Write exactly {n_exchanges} back-and-forth exchanges ({n_exchanges * 2} lines total).
Phil speaks first in each exchange.

RULES:
- Do NOT repeat any phrase, sentence, or idea already in the conversation above
- Do NOT reuse canned fallback, seed, expander, or SKG template language
- Each line must advance with a new angle, specific example, or honest challenge
- No explanations, no headers, no stage labels — just the dialogue lines

OUTPUT FORMAT:
PHIL [emotion]: dialogue text
JIM [emotion]: dialogue text

Valid emotions: excited, curious, warm, skeptical, dry, amused, concerned, thoughtful"""


def generate_segment(
    topic: str,
    key_points: List[str],
    stage: str,
    history_lines: List[str],
    primary_source_summary: str = "",
    n_exchanges: Optional[int] = None,
    persona_brief: str = "",
    generation_nonce: Optional[str] = None,
) -> List[Dict]:
    """
    Generate one conversation segment using the required Qwen model.

    Returns a list of line dicts (speaker, text, emotional_state, pause_after, timestamp).
    Returns [] if the bridge is unreachable or the response is unparseable.
    """
    stage_info = _STAGES.get(stage, _STAGES["expansion"])
    n = n_exchanges or stage_info["n"]
    prompt = _build_prompt(
        topic,
        key_points,
        stage,
        stage_info,
        history_lines,
        primary_source_summary,
        n,
        persona_brief=persona_brief,
        generation_nonce=generation_nonce or f"{stage}-{uuid4().hex}",
    )
    raw, backend = _call_bridge(prompt)
    if raw is None:
        return []
    parsed = _parse_response(raw, backend)
    if not parsed:
        logger.warning(
            "LLM returned no parseable lines for stage=%s topic=%r; raw preview: %r",
            stage,
            topic,
            raw[:200],
        )
    return parsed


def regenerate_section(script: List[Dict], start: int, end: int, topic: str,
                       instructions: str = "", source_context: str = "") -> List[Dict]:
    """Rewrite an exclusive slice through the existing writer, with no template fallback."""
    selected = script[start:end]
    prompt = f"""{_CHARACTERS}
Rewrite only the selected dialogue, preserving its factual meaning and speaker order.
Return exactly {len(selected)} lines in PHIL [emotion]: dialogue / JIM [emotion]: dialogue format.
Keep approximately the original word count. No headings, placeholders, or copied context lines.
Topic: {topic}
Source material: {source_context[:4000]}
Previous context (do not rewrite): {json.dumps(script[max(0, start-3):start])}
Selected lines to rewrite: {json.dumps(selected)}
Following context (do not rewrite): {json.dumps(script[end:end+3])}
Editorial instructions: {instructions}
Request: {uuid4().hex}
"""
    raw, backend = _call_bridge(prompt)
    if not raw:
        raise RuntimeError("LLM writer unavailable or returned no dialogue")
    replacement = _parse_response(raw, backend)
    if len(replacement) != len(selected):
        raise ValueError("Writer must return exactly the selected number of lines")
    for offset, (old, new) in enumerate(zip(selected, replacement)):
        if old.get("speaker", "").lower() != new["speaker"].lower():
            raise ValueError("Writer changed the selected speaker order")
        new["speaker"] = old["speaker"]
        new["emotion"] = new["emotional_state"]["primary"]
        new["pause_after"] = old.get("pause_after", new["pause_after"])
        new["line_number"] = old.get("line_number", start + offset + 1)
    return replacement


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
