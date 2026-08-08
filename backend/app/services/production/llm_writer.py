"""
llm_writer.py — LLM script writer for Phil & Jim Dandy Show.

Routes script generation through the substrate governance bridge
(http://127.0.0.1:5199/query) with role "dandy_scriptwriter".

The LLM writes dialogue within a brief supplied by the system (topic, key
points, stage, primary source). Bryan is the final decision maker on what
ships. The validator (ScriptQualityGuard) is the quality gate, not the LLM.

Falls back to the SKG path if the bridge is unavailable.
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

_BRIDGE_URL = os.getenv("DANDY_LLM_BRIDGE_URL", "http://127.0.0.1:5199/query")
_LLAMACPP_BASE_URL = os.getenv("DANDY_LLAMACPP_BASE_URL", "http://127.0.0.1:40343/v1")
_LLAMACPP_MODEL = os.getenv("DANDY_LLAMACPP_MODEL", "local")
_ROLE = "dandy_scriptwriter"
_TIMEOUT = 120  # matches governance config timeout_seconds

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


def _call_governance_bridge(prompt: str) -> Optional[str]:
    payload = json.dumps({"role": _ROLE, "prompt": prompt}).encode()
    req = urllib.request.Request(
        _BRIDGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return body.get("text", "")
    except Exception as exc:
        logger.warning("LLM governance bridge call failed: %s", exc)
        return None


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
    governance = _call_governance_bridge(prompt)
    if governance:
        return governance, "governance_bridge"
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
    Generate one conversation segment via the governed LLM bridge.

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


def writer_status() -> Dict[str, object]:
    governance_ok = False
    llamacpp_ok = False
    try:
        bridge_root = _BRIDGE_URL.rsplit("/", 1)[0] + "/"
        req = urllib.request.Request(bridge_root, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            governance_ok = resp.status < 500
    except Exception:
        governance_ok = False

    try:
        req = urllib.request.Request(f"{_LLAMACPP_BASE_URL}/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            llamacpp_ok = resp.status < 500
    except Exception:
        llamacpp_ok = False

    active = "governance_bridge" if governance_ok else "llamacpp" if llamacpp_ok else "offline"
    return {
        "bridge_reachable": bool(governance_ok or llamacpp_ok),
        "active_writer": "llm_bridge" if governance_ok or llamacpp_ok else "offline",
        "writer_backend": active,
        "bridge_url": _BRIDGE_URL,
        "llamacpp_url": _LLAMACPP_BASE_URL,
        "warning": None
        if governance_ok or llamacpp_ok
        else "LLM writer offline - generation will fail closed; SKG is persona guidance only.",
    }


def check_bridge() -> bool:
    """Return True if any configured LLM writer backend is reachable."""
    return bool(writer_status()["bridge_reachable"])
