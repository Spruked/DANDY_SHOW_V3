"""Compatibility CLI for explicit direct episode production (no work on import)."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_id", help="Existing episode to produce")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.safety import contained_path, validate_id
    from app.services.production import HardenedPodcastWorker
    directory = contained_path(ROOT / "episodes", validate_id(args.episode_id))
    script = json.loads((directory / "script.json").read_text(encoding="utf-8"))["script"]
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    result = HardenedPodcastWorker(ROOT).produce_episode(
        args.episode_id, config.get("title", args.episode_id), config.get("topic", ""), script)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
