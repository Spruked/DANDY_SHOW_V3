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
_LAST_CALL_DIAGNOSTIC = {}
_DIALOGUE_GRAMMAR_BODY = r'''exchange ::= "PHIL [" emotion "]: " line "\nJIM [" emotion "]: " line "\n"
emotion ::= "curious" | "warm" | "thoughtful" | "skeptical" | "dry" | "amused" | "concerned"
line ::= [^\r\n]{7,599} [.!?]'''


def _dialogue_grammar(exchanges: int) -> str:
    # Match the largest stage request (expansion/deepening request six turns).
    # A lower cap silently truncates otherwise valid model output.
    count = max(1, min(int(exchanges or 1), 8))
    return "root ::= " + " ".join(["exchange"] * count) + "\n" + _DIALOGUE_GRAMMAR_BODY




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
        "goal": "Open the Phil and Jim Dandy Show, introduce the hosts and topic, explain the supplied topic in plain language without inventing facts, then let Jim ask the central practical question.",
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
        "goal": "Close this episode: summarize the discussion, separate known facts from unanswered questions, give a practical takeaway, thank the listener, and sign off the Phil and Jim Dandy Show. Introduce no new topic or example.",
        "n": 3,
    },
}

# Matches: PHIL [excited]: text, JIM [dry]: text, or PHIL: text.
_LINE_RE = re.compile(r"^(PHIL|JIM)(?:\s*(?:\[([^\]]{2,20})\]|([A-Za-z_ -]{2,20})))?:\s*(.{8,})$", re.IGNORECASE)
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


def _call_llamacpp(prompt: str, n_exchanges: int | None = None) -> Optional[str]:
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
        "temperature": 0.6,
        "top_p": 0.9,
        "max_tokens": 1800,
    }
    if n_exchanges is not None:
        # Validate complete batches after decoding. A hard character grammar
        # forced the model to pad/truncate natural sentences (Inde/indle).
        payload["max_tokens"] = max(1800, min(6000, n_exchanges * 450))
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "dandy_dialogue", "strict": True, "schema": {
                "type": "object", "properties": {"lines": {
                    "type": "array", "minItems": n_exchanges * 2, "maxItems": n_exchanges * 2,
                    "items": {"type": "object", "properties": {
                        "speaker": {"type": "string", "enum": ["Phil", "Jim"]},
                        "emotion": {"type": "string"}, "text": {"type": "string"}},
                        "required": ["speaker", "emotion", "text"], "additionalProperties": False}}},
                "required": ["lines"], "additionalProperties": False}}}
        payload["messages"][0]["content"] = "Write complete Phil and Jim Dandy dialogue. Return only the requested JSON object, with exactly " + str(n_exchanges * 2) + " lines. Alternate Phil then Jim. Never include speaker labels inside text. The supplied brief is authoritative. This is a factual explanatory discussion, not a product design brainstorm. Do not propose product mechanisms or technologies not supplied. Introduce the named topic in the opening, and only thank listeners in the closing."

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


def _parse_response(text: str, generated_by: str) -> List[Dict]:
    lines = []
    try:
        parsed = json.loads(text)
        raw_lines = parsed.get("lines", []) if isinstance(parsed, dict) else []
    except (ValueError, TypeError):
        raw_lines = []
        for raw in (text or "").strip().splitlines():
            match = _LINE_RE.match(raw.strip())
            if match:
                raw_lines.append({"speaker": match.group(1), "emotion": match.group(2) or match.group(3) or "thoughtful", "text": match.group(4)})
    for raw in raw_lines:
        if not isinstance(raw, dict):
            continue
        speaker = _SPEAKER_MAP.get(str(raw.get("speaker", "")).lower())
        if not speaker:
            continue
        dialogue = str(raw.get("text", "")).strip().strip('"')
        lines.append({"speaker": speaker, "text": dialogue,
            "emotional_state": {"primary": str(raw.get("emotion") or "thoughtful").lower().strip()},
            "pause_after": _PAUSE_MAP.get(speaker, 0.45), "timestamp": datetime.now().isoformat(),
            "generated_by": generated_by or "llm_writer"})
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
    production_brief: str = "",
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
        f"\nPrimary source — use specific details from this:\n{primary_source_summary[:4000]}"
        if primary_source_summary
        else ""
    )

    persona_block = (
        f"\nPERSONA / SKG RULEBOOK:\n{persona_brief[:1800]}\n"
        if persona_brief
        else ""
    )
    topic_scope = ("For this episode POPS means Proof of Presence: evidence of someone being present at a place and time. No implementation is specified. Presence is not merely a timestamp and does not itself prove attention, engagement or intent. Discuss criteria and unanswered questions. Use one explicitly hypothetical ordinary attendance-list example, not electronic tracking, new devices or a technical product design."
                   if "proof of presence" in topic.lower() else "Do not extend a supplied term beyond its stated meaning.")
    nonce = generation_nonce or f"fresh-{datetime.now().isoformat()}-{uuid4().hex[:8]}"

    return f"""Write a complete part of a Phil and Jim Dandy Show episode.
Phil is curious, warm and energetic. Jim is practical, skeptical and dryly funny.

TOPIC: {topic}
KEY POINTS:
{kp_block}
SOURCE MATERIAL:
{source_block or '(No implementation source supplied. Do not invent product capabilities.)'}
SCOPE: {topic_scope}

CURRENT STAGE: {stage}
STAGE GOAL (required): {stage_info['goal']}
EDITORIAL ASSIGNMENT (required):
{production_brief[:6000]}
PERSONA CONSTRAINTS:
{persona_brief[:800]}

PREVIOUS DIALOGUE (continue, do not repeat it):
{chr(10).join(history_lines[-8:]) or '(Start the show.)'}

Return only a JSON object with a "lines" array of exactly {n_exchanges * 2} objects.
Each object has "speaker", "emotion", and "text". Alternate Phil then Jim.
Write original dialogue in every text value; there are no example lines to copy.
Write natural complete sentences, normally 15–55 words per turn, ending with punctuation.
Use no speaker labels inside text. Do not repeat a sentence or add filler.
Give at most one clearly labeled simple hypothetical example across the episode.
Do not invent mechanisms, hardware, adoption, guarantees or partnerships.
If a capability is not specified, discuss it as an unanswered question.
{("The FIRST Phil line welcomes listeners to the Phil and Jim Dandy Show and introduces the topic. The next exchanges explain the term and frame the discussion. Do not sign off." if stage == "opening" else "Summarize the known points and open questions, thank listeners and say goodbye. No new examples." if stage == "closing" else "Advance the current assignment without a greeting or sign-off. This episode has more sections after this one.")}
Request: {nonce}
"""



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
        production_brief=production_brief,
    )
    for attempt in range(2):
        raw, backend = _call_bridge(prompt, n_exchanges=n)
        if not raw:
            continue
        parsed = _parse_response(raw, backend)
        issues = response_issues(parsed, n)
        combined = " ".join(line.get("text", "") for line in parsed).lower()
        if stage == "opening" and not all(word in combined for word in ("phil", "jim", "dandy", "show")):
            issues.append("Opening must introduce the Phil and Jim Dandy Show and its topic")
        if stage == "opening" and "proof of presence" in topic.lower() and "proof of presence" not in combined:
            issues.append("Opening must explicitly explain the named topic POPS: Proof of Presence")
        supplied = " ".join([topic, " ".join(key_points), primary_source_summary, production_brief]).lower()
        if "proof of presence" in topic.lower():
            if re.search(r"(?:not just|it's about|it is about|all about).{0,90}(?:being engaged|engagement|paying attention)", combined) or "physically present and engaged" in combined:
                issues.append("Presence must not be redefined as attention or engagement; the supplied topic concerns evidence of place and time")
            if re.search(r"pops (?:involves|uses|relies on|requires) (?:multiple|several|biometric|technical)", combined):
                issues.append("No POPS implementation layers are supplied; describe those details as unknown rather than established")
            for mechanism in ("blockchain", "biometric", "facial recognition", "gps", "smart bracelet", "wearable", "qr code"):
                if mechanism in combined and mechanism not in supplied:
                    issues.append(f"Unsupported implementation detail: {mechanism}; stay with the supplied concept and ordinary attendance-list example")

        if stage == "closing" and not re.search(r"\b(thanks|thank you|thank.*listening|until next|next time|goodbye|take care|see you)\b", combined):
            issues.append("Closing must thank the listeners and sign off")
        if not issues:
            _LAST_CALL_DIAGNOSTIC.update(status="success", error=None)
            for line in parsed:
                line["generation_stage"] = stage
            return parsed
        _LAST_CALL_DIAGNOSTIC.update(status="rejected", error="; ".join(issues))
        logger.warning("Rejected %s batch: %s", stage, issues)
        prompt += "\nCORRECTION REQUIRED: " + "; ".join(issues) + ". Rewrite the complete requested batch with natural complete sentences and alternating PHIL/JIM lines."
    return []


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


def response_issues(lines: List[Dict], exchanges: int) -> List[str]:
    issues = []
    if len(lines) != exchanges * 2:
        issues.append(f"Expected {exchanges * 2} dialogue lines, received {len(lines)}")
    for index, line in enumerate(lines):
        expected = "phil" if index % 2 == 0 else "jim"
        if str(line.get("speaker", "")).lower() != expected:
            issues.append(f"Line {index + 1} must be {expected.upper()}")
        issue = dialogue_issue(line.get("text", ""))
        if issue:
            issues.append(f"Line {index + 1}: {issue}")
    return issues


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
        issue = dialogue_issue(new.get("text", ""))
        if issue:
            raise ValueError(f"Writer returned invalid dialogue: {issue}")
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


def last_call_diagnostic():
    return dict(_LAST_CALL_DIAGNOSTIC)
