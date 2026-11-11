"""Nemotron reasoning-budget probe for Dandy Studio.

Thinking cannot be switched off on the big prompt. This probe replays
the REAL Episode 001 prompt from the saved evidence file with a capped thinking
budget, to see whether Nemotron thinks briefly and then writes the JSON script.
2 calls (~11k input tokens each, 3,500 output max), testing a capped thinking budget. Changes nothing in Dandy.

    python scripts\nemotron_budget_probe.py data\\debug\\nemotron_EVIDENCE_6ac4f6eb.json
"""
import json
import os
import sys
import time
import urllib.request
from urllib.error import HTTPError, URLError

URL = os.getenv("DANDY_NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1").rstrip("/") + "/chat/completions"
MODEL = os.getenv("DANDY_NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
KEY = os.getenv("NVIDIA_API_KEY")
EPISODE_SYSTEM = ("Write the complete episode at the requested length. Use supplied facts only. "
                  "Return only the JSON array requested.")


def find(obj, names):
    """Depth-first search for the first key in names."""
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
        for value in obj.values():
            hit = find(value, names)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = find(value, names)
            if hit is not None:
                return hit
    return None


def load_evidence(path):
    data = json.load(open(path, encoding="utf-8"))
    payload = find(data, ["request_payload", "payload", "request"])
    if isinstance(payload, dict) and "messages" in payload:
        print("Saved request payload found.")
        print(f"   chat_template_kwargs in the REAL request: {payload.get('chat_template_kwargs')!r}")
        print(f"   temperature: {payload.get('temperature')}  max_tokens: {payload.get('max_tokens')}\n")
        user = next(m["content"] for m in payload["messages"] if m.get("role") == "user")
        return user, payload.get("chat_template_kwargs")
    prompt = find(data, ["prompt", "user_prompt", "request_prompt"])
    if not isinstance(prompt, str) or len(prompt) < 1000:
        raise SystemExit("Could not find the episode prompt in that file. Send me its top-level keys.")
    print("No saved request payload; using the saved prompt.")
    print("   (Cannot confirm whether the real request carried enable_thinking=false.)\n")
    return prompt, None


def run(name, prompt, temperature, system_prefix="", extra=None, max_tokens=600):
    payload = {"model": MODEL, "temperature": temperature, "max_tokens": max_tokens, "stream": False,
               "messages": [{"role": "system", "content": system_prefix + EPISODE_SYSTEM},
                            {"role": "user", "content": prompt}]}
    payload.update(extra if extra is not None else {"chat_template_kwargs": {"enable_thinking": False}})
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode())
    except HTTPError as exc:
        print(f"{name}\n   HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}\n")
        return
    except (URLError, TimeoutError) as exc:
        print(f"{name}\n   {type(exc).__name__}: {exc}\n")
        return
    usage = body.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning = details.get("reasoning_tokens", usage.get("reasoning_tokens", "n/a"))
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = (msg.get("content") or "").strip()
    print(f"{name}\n   {time.monotonic() - started:.1f}s | finish={choice.get('finish_reason')} | "
          f"prompt={usage.get('prompt_tokens')} | completion={usage.get('completion_tokens')} | "
          f"reasoning={reasoning} | separate_reasoning_field={bool(msg.get('reasoning_content') or msg.get('reasoning'))}")
    print(f"   content starts: {content[:160]!r}")
    print(f"   content length: {len(content):,} chars | starts with '[': {content.startswith('[')}\n")


if __name__ == "__main__":
    if not KEY:
        raise SystemExit("NVIDIA_API_KEY is not set in this window.")
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/nemotron_budget_probe.py <evidence json>")
    episode_prompt, _ = load_evidence(sys.argv[1])
    print(f"Prompt length: {len(episode_prompt):,} characters\n")
    run("D  reasoning_budget=2000 (thinking allowed, capped)", episode_prompt, 0.7,
        extra={"reasoning_budget": 2000}, max_tokens=3500)
    run("E  reasoning_budget=2000 + enable_thinking=false", episode_prompt, 0.7,
        extra={"reasoning_budget": 2000, "chat_template_kwargs": {"enable_thinking": False}}, max_tokens=3500)
    print("Good = reasoning stops near 2,000, then content starts with '[' before the 3,500 cut-off.")
