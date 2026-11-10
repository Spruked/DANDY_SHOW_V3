"""One bounded sample request; never publishes an episode or imports its writer."""
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
import urllib.request
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]


def protected_hashes():
    files = set()
    for folder in (ROOT / "episodes", ROOT / "config" / "characters"):
        files.update(path for path in folder.rglob("*") if path.is_file() and path.suffix != ".lock")
    for name in ("config/voices.json", "config/config.json", "config/writer.json",
                 "config/qwen_tts.json", "PHIL17SAMPLE.wav", "jimsample18.wav",
                 "phil_dandy_skg.py", "Jim_dandy_skg.py"):
        files.add(ROOT / name)
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files) if path.is_file()}


def main():
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise SystemExit("NVIDIA_API_KEY is not set; no request sent.")
    original = ROOT / "data/debug/nemotron_last_episode_response.json"
    evidence = json.loads(original.read_text(encoding="utf-8"))
    _, marker, context = evidence["prompt"].partition("CONTEXT PACKAGE:")
    if not marker or len(context) < 1000:
        raise SystemExit("Complete saved context was not found; no request sent.")
    config = json.loads((ROOT / "config/writer.json").read_text(encoding="utf-8"))
    url = os.getenv("DANDY_NVIDIA_API_URL", config["nvidia_base_url"]).rstrip("/") + "/chat/completions"
    model = os.getenv("DANDY_NVIDIA_MODEL", config["nvidia_model"])
    instruction = (
        "Diagnostic sample only: use the complete context below to write exactly eight alternating "
        "Phil/Jim turns, starting with phil, totaling about 200 spoken words. The saved episode "
        "remains 25 minutes; its full-episode length instructions do not apply to this sample. "
        "Return ONLY a complete JSON array. Each object must have exactly speaker (phil or jim), "
        "text (spoken dialogue), emotion (string), and pause_after (number of seconds, e.g. 0.4). "
        "Use supplied facts and canon only. Include no planning, word counts, or producer notes."
    )
    payload = {"model": model, "temperature": 0.7, "max_tokens": 6000,
               "reasoning_budget": 2000, "stream": False,
               "messages": [{"role": "system", "content": instruction},
                            {"role": "user", "content": instruction + "\n\nCONTEXT PACKAGE:" + context}]}
    before = protected_hashes()
    started = time.monotonic()
    record = {"captured_at": datetime.now(timezone.utc).isoformat(),
              "source_evidence": str(original.relative_to(ROOT)),
              "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
              "context_characters": len(context), "endpoint": url, "request_payload": payload}
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                    headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    print("Sending one diagnostic request: full context, eight turns, reasoning budget 2000, max_tokens 6000.", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            record["http_status"] = response.status
            record["request_id"] = response.headers.get("x-request-id")
            record["response"] = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        record.update(http_status=exc.code, error_body=exc.read().decode("utf-8", errors="replace"))
    except (URLError, TimeoutError) as exc:
        record.update(error_type=type(exc).__name__, error=str(exc))
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    after = protected_hashes()
    record["protected_files_unchanged"] = before == after
    record["protected_file_count"] = len(before)
    record["changed_protected_files"] = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    body = record.get("response", {})
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    result = {"finish_reason": choice.get("finish_reason"), "usage": body.get("usage"),
              "visible_characters": len(content), "separate_reasoning_characters": len(reasoning),
              "content_start": content[:500], "content_end": content[-250:]}
    try:
        parsed = json.loads(content)
        result["json_parseable"] = True
        result["schema_valid"] = isinstance(parsed, list) and len(parsed) == 8 and all(
            isinstance(turn, dict) and set(turn) == {"speaker", "text", "emotion", "pause_after"}
            and turn["speaker"] == ("phil" if index % 2 == 0 else "jim")
            and isinstance(turn["text"], str) and bool(turn["text"].strip())
            and isinstance(turn["emotion"], str)
            and isinstance(turn["pause_after"], (int, float)) and not isinstance(turn["pause_after"], bool)
            for index, turn in enumerate(parsed))
        result["spoken_words"] = sum(len(turn.get("text", "").split()) for turn in parsed if isinstance(turn, dict)) if isinstance(parsed, list) else 0
    except (ValueError, TypeError):
        result.update(json_parseable=False, schema_valid=False, spoken_words=None)
    record["analysis"] = result
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "data/debug" / f"nemotron_transition_{stamp}.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"evidence": str(output), "http_status": record.get("http_status"),
                      "elapsed_seconds": record["elapsed_seconds"],
                      "protected_files_unchanged": record["protected_files_unchanged"], **result}, indent=2))


if __name__ == "__main__":
    main()
