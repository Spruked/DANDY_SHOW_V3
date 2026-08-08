"""Direct production script — bypasses the API and runs the worker directly."""
import sys
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.environ.setdefault("DANDY_PROJECT_ROOT", str(PROJECT_ROOT))

# Add ffmpeg to PATH
ffmpeg_bin = PROJECT_ROOT / "staging" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin"
os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + os.environ.get("PATH", "")

from app.services.production import MergedDandyPodcastWorker

EPISODE_ID = "sovereign_software_special_001"
episode_dir = PROJECT_ROOT / "episodes" / EPISODE_ID
script_path = episode_dir / "script.json"

# Load script
with open(script_path, encoding="utf-8") as f:
    data = json.load(f)
script_lines = data["script"]

print(f"Script loaded: {len(script_lines)} lines")
words = sum(len(l["text"].split()) for l in script_lines)
print(f"Word count: {words} (~{words/160:.1f} min)")

# Run production
worker = MergedDandyPodcastWorker(PROJECT_ROOT)
print("Worker initialized. Starting production...")

result = worker.produce_episode(
    episode_id=EPISODE_ID,
    title="The Phil and Jim Dandy Show — Sovereign Software Special",
    topic="TrueMark Sovereign Software Ecosystem pitch: Mint, GOAT, and the ORB",
    script_lines=script_lines,
)

print("\n=== PRODUCTION COMPLETE ===")
print(f"Audio file: {result.get('audio_file')}")
print(f"Lines produced: {len(result.get('transcript', []))}")
if result.get("metadata"):
    meta = result["metadata"]
    print(f"Processing: {meta.get('processing', {}).get('processing_chain', 'unknown')}")
    if meta.get("warning"):
        print(f"Warning: {meta['warning']}")
