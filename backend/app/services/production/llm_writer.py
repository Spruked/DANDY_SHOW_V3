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


def _call_nvidia(prompt: str, kind: str = "short-copy", *, cancel_event=None, max_tokens_override=None,
                 sample: bool = False) -> Optional[str]:
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
                   ("Write the requested Dandy Show dialogue at the requested length. Use supplied facts only. "
                    "Return only the dialogue in the format requested." if kind == "episode" else
                    "Propose the requested episode segment plan. Return only the JSON object requested."
                    if kind == "segment-plan" else
                    f"Write only a short {kind}. Use supplied facts only. Return plain copy.")},
                  {"role": "user", "content": prompt}], "stream": False}
    if kind == "episode":
        # Match the successful transition probe: positive budget alone keeps
        # provider reasoning separate from final dialogue (variant D).
        payload["reasoning_budget"] = settings['reasoning_budget']
        if sample:
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


SECTION_WORDS = 550          # one request reliably yields ~800 words; stay well inside that
MAX_SECTION_WORDS = 900
_TURN_FIELDS = {'speaker', 'text', 'emotion', 'pause_after'}
_OUTPUT_CONTRACT = """OUTPUT FORMAT (this overrides the PHIL:/JIM: transcript format described in the context package,
which is only for manual imports):
Return ONLY a JSON array, nothing before or after it. Each item has exactly these keys:
speaker ("phil" or "jim"), text (spoken dialogue), emotion (one word), pause_after (number of seconds, 0 to 3).
Example: [{"speaker": "phil", "text": "Spoken sentence.", "emotion": "warm", "pause_after": 0.5},
{"speaker": "jim", "text": "Spoken reply.", "emotion": "curious", "pause_after": 0.4}]"""
_RULES = """Alternate speakers on every turn. Use complete spoken sentences. No markdown, stage directions,
citations or planning notes inside text. Do not invent facts beyond the context package.
Phil addresses Jim; Jim addresses Phil. Neither addresses himself by name. The brothers' biographies
do not establish product features. iOS/Android parity does not mean mobile/desktop parity."""
_BLOCK_SPEAKER = re.compile(r'^(PHIL|JIM)\s*:\s*(.+)$', re.I)
_BLOCK_EMOTION = re.compile(r'^emotion\s*:\s*(.+)$', re.I)
_BLOCK_PAUSE = re.compile(r'^pause[_ ]after\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|seconds)?$', re.I)


def _parse_turn_blocks(text: str) -> Optional[List[Dict]]:
    """Strict reader for the SPEAKER:/Emotion:/pause_after: layout the model sometimes emits.

    Every non-blank line must belong to a complete three-line turn; anything
    else returns None so the caller rejects the response rather than drop lines.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) % 3:
        return None
    turns = []
    for i in range(0, len(lines), 3):
        speaker = _BLOCK_SPEAKER.match(lines[i])
        emotion = _BLOCK_EMOTION.match(lines[i + 1])
        pause = _BLOCK_PAUSE.match(lines[i + 2])
        if not (speaker and emotion and pause):
            return None
        turns.append({'speaker': speaker.group(1).lower(), 'text': speaker.group(2).strip(),
                      'emotion': emotion.group(1).strip(), 'pause_after': float(pause.group(1))})
    return turns


DEFAULT_TRANSCRIPT_PAUSE = 0.4


def _parse_transcript_lines(text: str) -> Optional[List[Dict]]:
    """Plain PHIL:/JIM: lines, one turn per line. Any other line rejects the response."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    turns = []
    for line in lines:
        match = _BLOCK_SPEAKER.match(line)
        if not match:
            return None
        turns.append({'speaker': match.group(1).lower(), 'text': match.group(2).strip(),
                      'emotion': 'neutral', 'pause_after': DEFAULT_TRANSCRIPT_PAUSE})
    return turns or None


_LEADING_LABEL = re.compile(r'^(phil|jim)\s*:\s*', re.I)


def parse_dialogue(raw: str, first_speaker: str = 'phil') -> List[Dict]:
    """Validate one model response; reject it whole instead of discarding turns.

    Accepts PHIL:/JIM: transcript lines, SPEAKER/Emotion/pause_after blocks or a JSON array.
    A repeated own-speaker label inside the text ("PHIL: Phil: ...") is removed; the
    other speaker's label inside the text rejects the response.
    """
    candidate = (raw or '').strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json|text)?\s*|\s*```$", "", candidate, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = _parse_turn_blocks(candidate) or _parse_transcript_lines(candidate)
        if parsed is None:
            raise RuntimeError("Nemotron returned dialogue that is neither PHIL:/JIM: transcript lines, "
                               "SPEAKER/Emotion/pause_after turns nor a JSON array; raw evidence was retained") from None
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("Nemotron returned an empty episode script")
    script = []
    expected = first_speaker
    for index, item in enumerate(parsed, 1):
        if not isinstance(item, dict):
            raise RuntimeError(f'Dialogue turn {index} must be an object')
        if set(item) != _TURN_FIELDS:
            raise RuntimeError(f'Dialogue turn {index} has missing or unexpected fields')
        if not isinstance(item['text'], str) or not isinstance(item['emotion'], str):
            raise RuntimeError(f'Dialogue turn {index} requires text and emotion strings')
        speaker = str(item.get("speaker", "")).strip().lower()
        text = item["text"].strip()
        if speaker not in {"phil", "jim"} or not text:
            raise RuntimeError(f'Dialogue turn {index} has an invalid speaker or empty text')
        if speaker != expected:
            raise RuntimeError(f'Dialogue turn {index} must be {expected}; no turns were discarded')
        label = _LEADING_LABEL.match(text)
        if label:
            if label.group(1).lower() != speaker:
                raise RuntimeError(f"Dialogue turn {index} is {speaker} but its text carries the "
                                   f"{label.group(1).upper()}: label")
            text = text[label.end():].strip()
            if not text:
                raise RuntimeError(f'Dialogue turn {index} has empty text')
        pause = item['pause_after']
        if isinstance(pause, bool) or not isinstance(pause, (int, float)) or not math.isfinite(pause) or not 0 <= pause <= 3:
            raise RuntimeError(f'Dialogue turn {index} requires a numeric pause from 0 to 3 seconds')
        issue = dialogue_issue(text)
        if issue:
            raise RuntimeError(f'Dialogue turn {index}: {issue}')
        script.append({"speaker": speaker, "text": text, "emotion": item["emotion"].strip() or "neutral",
                       "pause_after": float(pause), "generated_by": "nemotron"})
        expected = "jim" if expected == "phil" else "phil"
    return script


def _words(lines: List[Dict]) -> int:
    return sum(len(line['text'].split()) for line in lines)


def _section_prompt(context: str, written: List[Dict], number: int, total: int,
                    words: int, first_speaker: str, target_words: int) -> str:
    if number == 1:
        position = "This is the OPENING section: open the episode and start the first topic in the segment notes."
    elif number == total:
        position = ("This is the FINAL section: finish the remaining segment-note topics, then bring the "
                    "conversation to a natural close. The last turn ends the episode.")
    else:
        position = ("This is a MIDDLE section: continue directly from the last line. Do not re-open the show, "
                    "greet listeners, or wrap up.")
    so_far = "\n".join(f"{line['speaker'].upper()}: {line['text']}" for line in written) or "(nothing yet)"
    return f"""CONTEXT PACKAGE:
{context}

EPISODE SO FAR ({_words(written)} of about {target_words} words). Do not repeat points already made:
{so_far}

YOUR TASK: write section {number} of {total} of this Dandy Show episode.
{position}
Work through the owner's segment notes in order; this section covers roughly part {number} of {total} of them.
Write about {words} spoken words, roughly {max(4, round(words / 16))} turns. The first turn is {first_speaker}.
{_RULES}

{_OUTPUT_CONTRACT}
"""


def _request_dialogue(prompt: str, first_speaker: str, *, cancel_event, sample: bool) -> List[Dict]:
    """One provider call plus one bounded retry when the response cannot be parsed."""
    last_error = None
    for _attempt in range(2):
        raw = _call_nvidia(prompt, kind="episode", cancel_event=cancel_event,
                           max_tokens_override=6000 if sample else None, sample=sample) or ""
        try:
            return parse_dialogue(raw, first_speaker)
        except RuntimeError as exc:
            last_error = exc
            logger.warning("[Nemotron] unusable dialogue response, retrying once: %s", exc)
    raise last_error


def generate_episode_script(context: str, *, target_words: int = 5000, sample: bool = False,
                            cancel_event=None, progress=None) -> List[Dict]:
    """Generate a structured Phil/Jim episode from the saved context package.

    Full episodes are written in sections because a single request yields far
    fewer words than a 25-minute script needs. Every section sees the whole
    saved context and the dialogue written so far.
    """
    if sample:
        prompt = (f"CONTEXT PACKAGE:\n{context}\n\nDIAGNOSTIC SAMPLE: write exactly eight alternating turns, "
                  "starting with phil, about 200 spoken words. Full-episode duration and word-count instructions "
                  f"in the context package do not apply to this sample.\n{_RULES}\n\n{_OUTPUT_CONTRACT}\n")
        script = _request_dialogue(prompt, 'phil', cancel_event=cancel_event, sample=True)
        if len(script) != 8:
            raise RuntimeError('Diagnostic sample must contain exactly eight dialogue turns')
    else:
        total = max(1, math.ceil(target_words / SECTION_WORDS))
        script: List[Dict] = []
        for number in range(1, total + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError('Generation cancelled; no script was activated')
            remaining = max(0, target_words - _words(script))
            words = min(MAX_SECTION_WORDS, max(150, round(remaining / (total - number + 1))))
            first = 'phil' if not script or script[-1]['speaker'] == 'jim' else 'jim'
            if progress:
                progress({'section': number, 'sections': total, 'words_so_far': _words(script),
                          'target_words': target_words})
            prompt = _section_prompt(context, script, number, total, words, first, target_words)
            section = _request_dialogue(prompt, first, cancel_event=cancel_event, sample=False)
            for line in section:
                line['section'] = number
            script.extend(section)
        if len(script) < 4:
            raise RuntimeError("Nemotron returned too few valid alternating dialogue turns")
        words = _words(script)
        if not target_words * 0.65 <= words <= target_words * 1.35:
            raise RuntimeError(f'Dialogue contains {words} words; expected approximately {target_words}. Raw evidence retained')
    # Repetition is reported as a review warning on the saved draft, not rejected here.
    for number, line in enumerate(script, 1):
        line["line_number"] = number
    return script


# ── Three-segment writing ───────────────────────────────────────────────────
TRANSCRIPT_CONTRACT = """OUTPUT FORMAT: return ONLY dialogue lines, one turn per line, each starting with PHIL: or JIM:
(the same transcript format as the context package). Alternate speakers. No headings, notes, numbering,
blank commentary or anything else before, between or after the lines."""


def split_beats(beats: List[str], passes: int) -> List[List[str]]:
    """Contiguous, non-overlapping share of the segment's beats for each pass."""
    passes = max(1, min(passes, len(beats))) if beats else max(1, passes)
    size, extra = divmod(len(beats), passes)
    result, start = [], 0
    for index in range(passes):
        end = start + size + (1 if index < extra else 0)
        result.append(beats[start:end])
        start = end
    return result


def _position_rules(segment_index: int, segment_count: int, pass_number: int, pass_count: int) -> str:
    opening = segment_index == 1 and pass_number == 1
    closing = segment_index == segment_count and pass_number == pass_count
    rules = []
    if opening:
        rules.append("This pass OPENS THE SHOW: welcome listeners, introduce Phil and Jim, and introduce the topic.")
    else:
        rules.append("Continue directly from the last lines shown. No greetings, welcomes, show openings or "
                     "re-introductions of Phil, Jim or the show. Move the conversation forward; do not replay "
                     "earlier exchanges.")
    if closing:
        rules.append("This pass CLOSES THE SHOW: finish the last beats, then wrap up, thank listeners and sign off. "
                     "The final turn ends the episode.")
    elif pass_number == pass_count:
        rules.append("End this segment at a natural transition. An advertising break follows. Do not summarize "
                     "the episode, thank listeners or sign off.")
    else:
        rules.append("Do not wrap up, summarize the episode, thank listeners or sign off.")
    return "\n".join(f"- {rule}" for rule in rules)


def segment_pass_prompt(context: str, *, segment: Dict, segment_count: int, pass_number: int, pass_count: int,
                        beats: List[str], covered: List[str], recent_lines: List[Dict], words: int,
                        first_speaker: str, requirements: List[Dict]) -> str:
    """One writing pass. Earlier dialogue appears only as the last few lines, never in full."""
    index = segment["index"]
    recent = "\n".join(f"{line['speaker'].upper()}: {line['text']}" for line in recent_lines) or "(the show has not started)"
    covered_text = "\n".join(f"- {item}" for item in covered) or "- (nothing yet)"
    points = "\n".join(f"- {point}" for point in segment.get("point_texts", [])) or "- (none assigned)"
    episode_wide = "\n".join(
        f"- {item['text']}" + (" (address primarily in this segment)" if item.get('primary_segment') == index else "")
        for item in requirements) or "- (none)"
    return f"""CONTEXT PACKAGE:
{context}

SEGMENT {index} OF {segment_count}: {segment.get('title', '')}
Topic focus: {segment.get('focus', '')}
Must-include points assigned to this segment:
{points}
Episode-wide requirements:
{episode_wide}

ALREADY COVERED (from the segment plan, for progression). Product names, benefits, key messages,
slogans and callbacks may recur naturally; build on these rather than replaying them:
{covered_text}

LAST LINES SO FAR:
{recent}

YOUR TASK: write pass {pass_number} of {pass_count} of segment {index}. Cover only these beats, in order:
{chr(10).join(f'- {beat}' for beat in beats) or '- (continue the segment focus)'}
Write about {words} spoken words, roughly {max(4, round(words / 16))} turns. The first turn is {first_speaker.upper()}.
POSITION RULES (these override the context package's whole-episode instructions about welcoming listeners,
summarizing, signing off and total target length, which apply to the episode as a whole):
{_position_rules(index, segment_count, pass_number, pass_count)}
{_RULES}

{TRANSCRIPT_CONTRACT}
"""


def write_segment(context: str, *, segment: Dict, segment_count: int, target_words: int, max_pass_words: int,
                  covered_before: List[str], previous_lines: List[Dict], requirements: List[Dict],
                  continuity_lines: int = 5, cancel_event=None, progress=None) -> Dict:
    """Write one segment in passes of at most max_pass_words words.

    Each pass sees the full context package, its beats, a plan-derived list of
    covered points, and only the last few lines written. A pass whose reply
    cannot be parsed is retried once. Repetition never triggers a retry; it is
    reported on the draft for the owner to judge.
    """
    pass_count = max(1, math.ceil(target_words / max_pass_words))
    beat_groups = split_beats(list(segment.get("beats", [])), pass_count)
    pass_count = len(beat_groups)
    lines: List[Dict] = []
    log = []
    covered = list(covered_before)
    for pass_number, beats in enumerate(beat_groups, 1):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError('Generation cancelled; no script was activated')
        remaining = max(0, target_words - _words(lines))
        words = min(max_pass_words, max(150, round(remaining / (pass_count - pass_number + 1))))
        recent = (previous_lines + lines)[-continuity_lines:] if continuity_lines else []
        first = 'phil' if not recent or recent[-1]['speaker'] == 'jim' else 'jim'
        if progress:
            progress({'segment': segment['index'], 'pass': pass_number, 'passes': pass_count,
                      'words_so_far': _words(lines), 'target_words': target_words})
        entry = {'pass': pass_number, 'beats': beats, 'requested_words': words, 'attempts': []}
        prompt = segment_pass_prompt(context, segment=segment, segment_count=segment_count,
                                     pass_number=pass_number, pass_count=pass_count, beats=beats,
                                     covered=covered, recent_lines=recent, words=words,
                                     first_speaker=first, requirements=requirements)
        result = None
        for attempt in (1, 2):
            raw = _call_nvidia(prompt, kind="episode", cancel_event=cancel_event) or ""
            try:
                result = parse_dialogue(raw, first)
            except RuntimeError as exc:
                entry['attempts'].append({'attempt': attempt, 'rejected': str(exc)})
                if attempt == 2:
                    raise
                continue
            entry['attempts'].append({'attempt': attempt, 'turns': len(result), 'words': _words(result)})
            break
        for line in result:
            line.update(segment_index=segment['index'], segment_pass=pass_number)
        lines.extend(result)
        covered.extend(beats)
        log.append(entry)
    for number, line in enumerate(lines, 1):
        line['segment_line'] = number
    return {'script': lines, 'passes': log, 'word_count': _words(lines)}


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
