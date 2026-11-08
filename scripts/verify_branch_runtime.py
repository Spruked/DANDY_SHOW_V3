"""Opt-in real local-model acceptance sample, isolated from operator episodes.

Run with the pinned writer, Qwen bridge, and FFmpeg available:
    .venv/Scripts/python scripts/verify_branch_runtime.py
Artifacts remain under archive/testing/results; no live episode/config is edited.
"""
import copy
import json
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api import library, production
from app.core import settings
from app.services.production import llm_writer, production_lifecycle as lifecycle
from app.services.production.segment_worker import SegmentAwarePodcastWorker
from app.services.storage import episode_store as store


def main():
    output = ROOT / "archive/testing/results" / ("branch-runtime-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.mkdir(parents=True)
    print(f"Artifacts: {output}", flush=True)
    status = llm_writer.writer_status()
    if not status["bridge_reachable"]:
        raise RuntimeError(status["warning"])
    script = llm_writer.generate_segment(topic="Safely combining software branches", stage="opening",
        key_points=["Preserve the existing work", "Verify the complete production workflow"], history_lines=[], n_exchanges=2)
    if len(script) != 4:
        raise RuntimeError(f"Expected four real model-written lines, received {len(script)}")
    print(f"Writer produced {len(script)} lines / {sum(len(line['text'].split()) for line in script)} words", flush=True)
    config = copy.deepcopy(settings.load_project_config())
    # This bounded sample tests dialogue, approval, takes, mastering and exports.
    # Operator intro/outro and hardware acceptance remain separate.
    config["intro_outro"] = {"enabled": False}
    config["sfx"] = {"enabled": False}
    config["tts"]["primary_engine"] = "qwen"
    episodes = output / "episodes"
    with ExitStack() as stack:
        for module in (store, library):
            for name, value in {"EPISODES_ROOT": episodes, "DRAFTS_ROOT": episodes / ".drafts",
                                "JOBS_ROOT": episodes / ".drafts/jobs"}.items():
                stack.enter_context(patch.object(module, name, value))
        stack.enter_context(patch.object(production, "PROJECT_ROOT", output))
        stack.enter_context(patch.object(settings, "load_project_config", return_value=config))
        stack.enter_context(patch.object(lifecycle, "load_project_config", return_value=config))
        stack.enter_context(patch.object(lifecycle, "list_library_assets", return_value=[]))
        class SampleWorker(SegmentAwarePodcastWorker):
            def __init__(self):
                super().__init__(base_path=output)
        stack.enter_context(patch.object(production, "MergedDandyPodcastWorker", SampleWorker))
        episode_id, job_id = "acceptance_sample", "job_acceptance_sample"
        store.create_episode_draft({"episode_id": episode_id, "title": "Branch integration acceptance",
            "topic": "Preserving work and verifying production", "target_duration": 60,
            "generation_mode": "ai_generate"}, job_id)
        store.save_script(episode_id, script)
        canonical = store.load_canonical_script(episode_id)
        lifecycle.save_preview_review(episode_id, {"canonical_version_id": canonical["version_id"],
            "canonical_source_hash": canonical["canonical_hash"], "overall_notes": "Automated isolated acceptance fixture",
            "line_reviews": {}, "section_notes": {}})
        state = lifecycle.create_draft(episode_id, canonical["version_id"])
        draft = state["draft"]
        for item in draft["morb_proposals"]:
            item.update(reviewed=True, operator_decision="accept")
        lifecycle.save_draft(episode_id, draft)
        state = lifecycle.approve_draft(episode_id, draft["draft_id"])
        approved = state["approved"]
        print("Rendering approved copy through real Qwen and FFmpeg...", flush=True)
        production._run_produce_background(episode_id, job_id, approved["script"],
            "Branch integration acceptance", "Preserving work and verifying production",
            production._script_as_text(approved["script"]), None, {},
            writer_engine="llamacpp", bridge_reachable_at_start=True, approved_production=approved)
        result = store.load_job(job_id)
        (output / "acceptance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if result["status"] != "produced":
            raise RuntimeError(json.dumps(result, indent=2))
        manifest = production.load_manifest(store.episode_dir(episode_id))
        production.validate_takes(store.episode_dir(episode_id), manifest["segments"])
        print(json.dumps({"status": result["status"], "audio": result["audio_file"],
            "engine_stats": result["engine_stats"], "saved_takes": len(manifest["segments"]),
            "outputs": str(output)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
