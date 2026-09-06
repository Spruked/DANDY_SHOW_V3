"""
llm_writer.py — direct local LLM script writer for Phil & Jim Dandy Show.

Dandy script generation goes straight to the local llama.cpp OpenAI-compatible
endpoint. The former substrate governance hop was intentionally removed from
the hot path because Dandy is a single-operator creative studio and the extra
network probe added latency without adding useful authority.

The LLM writes dialogue within a brief supplied by the system (topic, key
points, stage, primary source). Bryan is the final decision maker on what
ships. ScriptQualityGuard and the short-segment acceptance filters remain the
deterministic quality controls.
"""

import json
import logging
import os
import re
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)

_LLAMACPP_BASE_URL = os.getenv("DANDY_LLAMACPP_BASE_URL", "http://127.0.0.1:8009/v1")
_LLAMACPP_MODEL = os.getenv("DANDY_LLAMACPP_MODEL", "local")
_TIMEOUT = 120

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
    payload = {
        "model": _LLAMACPP_MODEL,
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
    """Compatibility name retained for callers; there is no governance hop."""
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
                "generated_by": generated_by or "llamacpp",
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
        "\n".join(history_lines[-24:])
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
- Generation ID: {nonce}
- Continue FORWARD from the conversation so far. Never restart the discussion.
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
- Do NOT repeat any phrase, sentence, claim, example, question, or idea already in the conversation above
- Do NOT summarize earlier turns unless the stage is closing
- Do NOT restart with the basic definition after it has already been established
- Do NOT reuse canned fallback, seed, expander, or SKG template language
- Each line must advance with a new angle, specific example, consequence, distinction, or honest challenge
- Finish every sentence and thought; never end on a dangling fragment
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
    """Generate one forward-only conversation stage directly through llama.cpp."""
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


def writer_status() -> Dict[str, object]:
    llamacpp_ok = False
    model_name = None
    model_meta: Dict[str, object] = {}
    try:
        req = urllib.request.Request(f"{_LLAMACPP_BASE_URL}/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            llamacpp_ok = resp.status < 500
            body = json.loads(resp.read().decode("utf-8"))
            entries = body.get("data") or body.get("models") or []
            if entries:
                first = entries[0]
                if isinstance(first, dict):
                    model_name = first.get("id") or first.get("name") or first.get("model")
                    model_meta = first.get("meta") or first.get("details") or {}
    except Exception:
        llamacpp_ok = False

    return {
        "bridge_reachable": llamacpp_ok,
        "active_writer": "llamacpp" if llamacpp_ok else "offline",
        "writer_backend": "llamacpp" if llamacpp_ok else "offline",
        "llamacpp_url": _LLAMACPP_BASE_URL,
        "model": model_name,
        "model_meta": model_meta,
        "governance_bridge": "removed_from_dandy_hot_path",
        "warning": None if llamacpp_ok else "Local llama.cpp writer is offline; script generation will fail closed.",
    }


def check_bridge() -> bool:
    """Compatibility helper: True only when the direct llama.cpp writer is reachable."""
    return bool(writer_status()["bridge_reachable"])
