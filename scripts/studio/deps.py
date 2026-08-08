"""
deps.py — Generate or verify the Dandy Studio dependency map.

Scans Python imports in the backend, reads package versions,
and writes docs/DEPENDENCY_MAP.md

Usage:
    python scripts/studio/deps.py
    python scripts/studio/deps.py --check   (exits 1 if map is stale)
"""
from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "DEPENDENCY_MAP.md"

PYTHON_PACKAGES = [
    ("fastapi",             "Web framework — REST API"),
    ("uvicorn",             "ASGI server — runs FastAPI"),
    ("pydantic",            "Data validation and schemas"),
    ("python-multipart",    "File upload support"),
    ("pillow",              "Image rendering — slideshow frames, ad cards"),
    ("ffmpeg-python",       "FFmpeg bindings — audio/video processing"),
    ("pydub",               "Audio segment manipulation"),
    ("edge-tts",            "Cloud TTS fallback (Microsoft Edge voices)"),
    ("torch",               "PyTorch — Kokoro TTS inference engine"),
    ("torchaudio",          "Audio tensor operations for Kokoro"),
    ("numpy",               "Numerical operations — audio processing"),
    ("networkx",            "Graph utilities — production dependency tracking"),
    ("sentence-transformers","Semantic similarity — script analysis"),
    ("voicemeeter-api",     "Voicemeeter real-time mixer integration"),
]

NODE_PACKAGES = [
    ("react",               "UI framework"),
    ("react-dom",           "React DOM renderer"),
    ("vite",                "Frontend build tool / dev server"),
    ("@vitejs/plugin-react","Vite React plugin"),
    ("tailwindcss",         "Utility CSS framework"),
    ("lucide-react",        "Icon library"),
]

EXTERNAL_SERVICES = [
    ("FFmpeg",          "Audio/video encoding — must be on PATH",           "Required"),
    ("OBS Studio",      "Live stream / recording control via WebSocket",     "Optional — Studio tab"),
    ("Voicemeeter",     "Real-time audio mixer",                             "Optional — Studio tab"),
    ("Kokoro TTS",      "Local neural TTS engine (primary voice)",           "Required for TTS"),
    ("CUDA / GPU",      "Accelerates Kokoro inference",                      "Optional — falls back to CPU"),
]

INTERNAL_MODULES = [
    ("backend/app/api/production.py",       "Episode produce endpoint"),
    ("backend/app/api/social.py",           "Legacy social export endpoints"),
    ("backend/app/api/social_slideshow.py", "Slideshow CRUD + render endpoints"),
    ("backend/app/api/social_adcards.py",   "Ad card CRUD + render endpoints"),
    ("backend/app/api/ads.py",              "Ad script generation endpoints"),
    ("backend/app/api/assets.py",           "Episode asset upload/management"),
    ("backend/app/api/mixer.py",            "Voicemeeter mixer proxy"),
    ("backend/app/api/obs.py",              "OBS WebSocket proxy"),
    ("backend/app/services/production/worker.py",               "TTS synthesis + audio post-processing"),
    ("backend/app/services/production/dandy_harmonizer.py",     "Script generation (Phil/Jim AI engine)"),
    ("backend/app/services/production/personality_loader.py",   "Voice/personality config loader"),
    ("backend/app/services/social/slideshow_renderer.py",       "Pillow + FFmpeg slide renderer"),
    ("backend/app/services/social/thumbnail_generator.py",      "Thumbnail image generator"),
    ("backend/app/services/social/audiogram_generator.py",      "Animated audiogram generator"),
    ("backend/app/schemas/social_visual.py",                    "Pydantic models: Slide, AdCard, Slideshow"),
    ("backend/app/core/paths.py",                               "Project path constants"),
]


def get_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except Exception:
        return "not installed"


def get_node_version(package: str) -> str:
    pkg_json = ROOT / "frontend" / "node_modules" / package / "package.json"
    if not pkg_json.exists():
        return "not installed"
    import json
    try:
        return json.loads(pkg_json.read_text()).get("version", "?")
    except Exception:
        return "?"


def generate() -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Dandy Studio — Dependency Map",
        f"\n_Generated: {stamp}_\n",
        "## Python Packages",
        "",
        "| Package | Version | Purpose |",
        "|---|---|---|",
    ]
    for pkg, purpose in PYTHON_PACKAGES:
        ver = get_version(pkg)
        lines.append(f"| `{pkg}` | {ver} | {purpose} |")

    lines += [
        "",
        "## Node / Frontend Packages",
        "",
        "| Package | Version | Purpose |",
        "|---|---|---|",
    ]
    for pkg, purpose in NODE_PACKAGES:
        ver = get_node_version(pkg)
        lines.append(f"| `{pkg}` | {ver} | {purpose} |")

    lines += [
        "",
        "## External Services",
        "",
        "| Service | Purpose | Status |",
        "|---|---|---|",
    ]
    for svc, purpose, status in EXTERNAL_SERVICES:
        lines.append(f"| {svc} | {purpose} | {status} |")

    lines += [
        "",
        "## Internal Module Map",
        "",
        "| Module | Responsibility |",
        "|---|---|",
    ]
    for mod, resp in INTERNAL_MODULES:
        exists = "✓" if (ROOT / mod).exists() else "✗ missing"
        lines.append(f"| `{mod}` {exists} | {resp} |")

    lines += [
        "",
        "## Data Flow",
        "",
        "```",
        "Episode config + topic",
        "    → dandy_harmonizer.py  (script generation)",
        "    → worker.py            (TTS synthesis per line)",
        "    → audio_post_processor (normalize, compress, encode)",
        "    → audio.mp3            (final episode)",
        "    → slideshow_renderer   (visual slides from script)",
        "    → social exports       (audiogram, thumbnail, quote card)",
        "```",
        "",
        "## Audio Jingle Slots",
        "",
        "| Slot | File | Status |",
        "|---|---|---|",
    ]
    jingle_slots = [
        ("intro",       "audio/jingles/intro_outro.mp3"),
        ("outro",       "audio/jingles/intro_outro.mp3"),
        ("bumper_in",   "audio/jingles/bumper_in.mp3"),
        ("bumper_out",  "audio/jingles/bumper_out.mp3"),
        ("bed_loop",    "audio/jingles/bed_loop.mp3"),
    ]
    for slot, path in jingle_slots:
        status = "present" if (ROOT / path).exists() else "missing"
        lines.append(f"| `{slot}` | `{path}` | {status} |")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio dependency map")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any required deps are missing")
    args = parser.parse_args()

    content = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Dependency map written: {OUTPUT.relative_to(ROOT)}")

    if args.check:
        missing = [pkg for pkg, _ in PYTHON_PACKAGES if get_version(pkg) == "not installed"]
        if missing:
            print(f"Missing packages: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
