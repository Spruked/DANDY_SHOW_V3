"""Cross-branch contracts, isolated from operator episodes and live inference."""
import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.api import production, library
from app.services.storage import episode_store as store
from app.services.production import production_lifecycle as lifecycle
from app.services.production.worker import HardenedPodcastWorker


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        episodes = self.root / "episodes"
        for module in (store, library):
            for name, value in {"EPISODES_ROOT": episodes, "DRAFTS_ROOT": episodes / ".drafts",
                                "JOBS_ROOT": episodes / ".drafts/jobs"}.items():
                self.stack.enter_context(patch.object(module, name, value))
        self.stack.enter_context(patch.object(production, "PROJECT_ROOT", self.root))
        self.stack.enter_context(patch.object(lifecycle, "list_library_assets", return_value=[]))
        self.client = self.stack.enter_context(TestClient(create_app(self.root / "runtime", recover_jobs=False)))
        response = self.client.post("/api/episodes/create", json={"episode_id": "integration", "title": "Integration",
            "topic": "Consolidating code", "target_duration": 60, "generation_mode": "script_feed"})
        self.assertEqual(response.status_code, 200, response.text)
        self.job = response.json()["job_id"]
        self.script = [{"speaker": "phil", "text": "A careful integration preserves the existing work.", "generated_by": "script_feed"},
                       {"speaker": "jim", "text": "Then verify the whole workflow with concrete evidence.", "generated_by": "script_feed"}]
        store.save_script("integration", self.script)

    def approved(self):
        canonical = store.load_canonical_script("integration")
        lifecycle.save_preview_review("integration", {"canonical_version_id": canonical["version_id"],
            "canonical_source_hash": canonical["canonical_hash"], "overall_notes": "Reviewed", "line_reviews": {}, "section_notes": {}})
        state = lifecycle.create_draft("integration", canonical["version_id"])
        draft = copy.deepcopy(state["draft"])
        for proposal in draft["morb_proposals"]:
            proposal.update(reviewed=True, operator_decision="accept")
        lifecycle.save_draft("integration", draft)
        return lifecycle.approve_draft("integration", draft["draft_id"])

    def test_preview_approval_and_edit_invalidation(self):
        state = self.approved()
        self.assertEqual(state["approval_state"], "approved")
        self.assertEqual(store.load_script("integration")["script"], self.script)
        draft = copy.deepcopy(state["draft"])
        draft["script"][0]["text"] = "This changed after approval."
        lifecycle.save_draft("integration", draft)
        with self.assertRaisesRegex(ValueError, "stale"):
            lifecycle.current_approval("integration")

    def test_embedded_preview_without_saved_field_is_projected_as_saved(self):
        self.approved()
        path = store.episode_dir("integration") / "production_editor/drafts/draft_v0001.json"
        before = path.read_bytes()
        raw = json.loads(before)
        self.assertNotIn("saved", raw["preview_review"])
        result = lifecycle.editor_state("integration")
        self.assertTrue(result["draft"]["preview_review"]["saved"])
        self.assertEqual(result["draft"]["preview_review"]["overall_notes"], "Reviewed")
        self.assertEqual(path.read_bytes(), before)

    def test_modified_approved_payload_is_rejected(self):
        state = self.approved()
        path = store.episode_dir("integration") / "production_editor/approved" / (state["current_approved_version_id"] + ".json")
        saved = json.loads(path.read_text())
        saved["script"][0]["spoken_text"] = "Unapproved replacement."
        path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, "integrity"):
            lifecycle.current_approval("integration")

    def test_parallel_canonical_saves_have_unique_versions(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: store.save_script("integration", self.script), range(8)))
        versions = store.list_canonical_scripts("integration")
        self.assertEqual(len(versions), 9)
        self.assertEqual(len({row["version_id"] for row in versions}), 9)

    def test_short_production_retains_progress_and_approved_input(self):
        state = self.approved()
        expected = state["approved"]
        root = self.root
        calls = []
        class Worker:
            def produce_episode(self, **kwargs):
                calls.append(kwargs)
                kwargs["progress_callback"]({"stage": "synthesizing", "progress": 0.5})
                audio = root / "episodes/integration/audio.mp3"
                audio.write_bytes(b"isolated audio fixture")
                return {"audio_file": str(audio), "metadata": {"engine_stats": {"qwen": 2}}}
        with patch.object(production, "MergedDandyPodcastWorker", Worker), patch.object(production, "export_social_package"):
            response = self.client.post(f"/api/episodes/produce?job_id={self.job}", json={"approved_version_id": state["current_approved_version_id"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(calls[0]["script_lines"], expected["script"])
        self.assertEqual(calls[0]["approved_production"], expected)
        self.assertEqual(store.load_job(self.job)["status"], "produced")
        self.assertEqual(store.load_job(self.job)["engine_stats"], {"qwen": 2})

    def test_unapproved_editor_cannot_use_legacy_production_path(self):
        self.approved()
        with patch.object(production, "MergedDandyPodcastWorker") as worker:
            response = self.client.post(f"/api/episodes/produce?job_id={self.job}")
        self.assertEqual(response.status_code, 409)
        worker.assert_not_called()

    def test_cancellation_stops_before_synthesis(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.cancel_event = threading.Event()
        worker.cancel_event.set()
        worker._normalize_speaker = lambda value: value
        worker._synthesize_line = Mock()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker._synthesize_segments(self.script, self.root, "integration")
        worker._synthesize_line.assert_not_called()

    def test_replace_or_delete_during_production_is_rejected(self):
        store.save_json(store.episode_dir("integration") / "status.json", {"status": "producing", "job_id": self.job})
        self.assertEqual(self.client.post("/api/episodes/integration/replace-script", json={"text": "PHIL: Replacement."}).status_code, 409)
        self.assertEqual(self.client.delete("/api/episodes/integration").status_code, 409)
        self.assertEqual(store.load_script("integration")["script"], self.script)

    def test_failed_approved_mastering_preserves_previous_audio(self):
        approved = self.approved()["approved"]
        audio = store.episode_dir("integration") / "audio.mp3"
        audio.write_bytes(b"previous accepted master")
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.base_path = self.root
        worker.project_config = {}
        worker._synthesize_segments = Mock(return_value=[])
        worker._concatenate_segments = lambda segments, output, **kwargs: output.write_bytes(b"new mix")
        worker.post_processor = Mock()
        worker.post_processor.process_episode.side_effect = RuntimeError("encoder failure")
        with self.assertRaisesRegex(RuntimeError, "previous production was preserved"):
            worker.produce_episode("integration", "Title", "Topic", approved["script"], approved_production=approved)
        self.assertEqual(audio.read_bytes(), b"previous accepted master")

    def test_uninstalled_qwen_mode_does_not_stop_running_model(self):
        from app.api import qwen_studio
        with patch.object(qwen_studio, "_port_open", return_value=False), \
             patch.object(qwen_studio, "_cached_checkpoint", return_value=None), \
             patch.object(qwen_studio, "_stop_existing_locked") as stop:
            response = self.client.post("/api/qwen-studio/mode/clone/start")
        self.assertEqual(response.status_code, 409)
        stop.assert_not_called()

    def test_qwen_cannot_stop_during_production(self):
        from app.api import qwen_studio
        production._PRODUCTION_SLOT.acquire()
        try:
            with patch.object(qwen_studio, "_stop_existing_locked") as stop:
                response = self.client.post("/api/qwen-studio/stop")
            self.assertEqual(response.status_code, 409)
            stop.assert_not_called()
        finally:
            production._PRODUCTION_SLOT.release()

    def test_existing_mixer_routes_remain_registered(self):
        paths = set(self.client.app.openapi()["paths"])
        self.assertIn("/api/mixer/status", paths)
        self.assertIn("/api/mixer/channel", paths)

    def test_shared_library_file_is_readable_through_episode_assets(self):
        from app.api import assets
        media = self.root / "asset_library/sample.wav"
        media.parent.mkdir()
        media.write_bytes(b"shared media fixture")
        record = {"asset_id": "lib_fixture", "stored_path": str(media), "original_name": media.name}
        with patch.object(assets, "PROJECT_ROOT", self.root), \
             patch.object(assets, "load_library_asset", return_value=record):
            response = self.client.get("/api/episodes/integration/assets/lib_fixture/file")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"shared media fixture")

    def test_built_frontend_assets_are_not_treated_as_identifiers(self):
        dist = Path(__file__).resolve().parents[2] / "frontend/dist/assets"
        scripts = list(dist.glob("*.js"))
        if not scripts:
            self.skipTest("Build frontend before checking the production static route")
        response = self.client.get("/assets/" + scripts[0].name)
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
