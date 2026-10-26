"""Contract tests use temporary storage and fake TTS/LLM; never touch episodes."""
import asyncio
from copy import deepcopy
from contextlib import ExitStack
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.api import production
from app.services.production.worker import HardenedPodcastWorker


class ProductionTests(unittest.TestCase):
    def test_websocket_and_status_route_contract(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.websockets.manager import manager
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(production, "episode_dir", return_value=Path(directory)), \
             TestClient(app) as client:
            self.assertEqual(client.get("/api/episodes/test/production-status").json()["status"], "new")
            production.save_json(Path(directory) / "status.json", {"status": "producing", "progress": 0.5})
            self.assertEqual(client.get("/api/episodes/test/production-status").json()["progress"], 0.5)
            with client.websocket_connect("/ws/test") as ws:
                self.assertEqual(ws.receive_json()["type"], "connected")
                client.portal.call(manager.broadcast, "test", {"type": "production_progress", "progress": 0.5})
                self.assertEqual(ws.receive_json()["progress"], 0.5)
                ws.send_text("still compatible")
                self.assertEqual(ws.receive_json()["type"], "echo")

    def run_job(self, fail=False, export_fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def episode_dir(episode_id):
                path = root / "episodes" / episode_id
                path.mkdir(parents=True, exist_ok=True)
                return path
            class Worker:
                def produce_episode(self, **kwargs):
                    kwargs["progress_callback"]({"stage": "synthesizing", "progress": 0.5})
                    if fail:
                        raise RuntimeError("TTS unavailable")
                    audio = episode_dir("test") / "audio.mp3"
                    audio.write_bytes(b"fake audio for orchestration test")
                    return {"audio_file": str(audio), "metadata": {"engine_stats": {"kokoro": 2}, "engine_line_stats": {"kokoro": 1}}}
            async def run():
                with patch.object(production, "episode_dir", side_effect=episode_dir), \
                     patch.object(production, "MergedDandyPodcastWorker", Worker), \
                     patch.object(production, "load_media_cues", return_value={}), \
                     patch.object(production, "export_social_package", side_effect=RuntimeError("export failed") if export_fail else None), \
                     patch("app.websockets.manager.manager.broadcast", new_callable=AsyncMock) as broadcast:
                    await asyncio.to_thread(production._run_produce_background,
                        "test", "job_test", [{"speaker": "phil", "text": "A real test line", "generated_by": "manual_edit"}],
                        "Title", "Topic", "Text", None, {}, event_loop=asyncio.get_running_loop())
                    await asyncio.sleep(0)
                    events = [call.args[1] for call in broadcast.call_args_list]
                    return events
            events = asyncio.run(run())
            import json
            status = json.loads((episode_dir("test") / "status.json").read_text())
            job = json.loads((root / "episodes/.drafts/jobs/job_test.json").read_text())
            self.assertEqual(status, job)
            self.assertTrue(any(event["type"] == "production_progress" for event in events))
            if fail or export_fail:
                self.assertEqual(status["status"], "failed")
                self.assertEqual(events[-1]["type"], "production_error")
                self.assertNotIn("production_complete", [event["type"] for event in events])
                if fail:
                    self.assertFalse((episode_dir("test") / "audio.mp3").exists())
            else:
                self.assertEqual(status["status"], "produced")
                self.assertEqual(status["progress"], 1)
                self.assertEqual(events[-1]["type"], "production_complete")
                self.assertEqual(status["engine_stats"], {"kokoro": 2})

    def test_persisted_progress_and_completion(self):
        self.run_job()

    def test_tts_failure_does_not_create_silent_success(self):
        self.run_job(fail=True)

    def test_export_failure_is_not_reported_as_complete(self):
        self.run_job(export_fail=True)

    def test_chunk_progress_and_missing_audio(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.voices_config = {"phil": {"primary_voice": "test"}}
        events = []
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(worker, "_synthesize_line", return_value="kokoro"):
            with self.assertRaisesRegex(RuntimeError, "no audio"):
                worker._synthesize_segments([{"speaker": "phil", "text": "Test dialogue"}], Path(directory), "test", events.append)
        self.assertEqual(events, [])


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.script = [{"speaker": "phil" if i % 2 == 0 else "jim",
                        "text": f"Discussion point {i} has specific evidence and practical consequences for the people involved today.",
                        "generated_by": "governance_bridge", "line_number": i + 1, "pause_after": 0.4,
                        "custom_metadata": {"preserve": i}} for i in range(12)]
        self.raw = "PHIL [curious]: The revised evidence shows a different practical outcome for the families using this service today.\nJIM [pragmatic]: We should measure that outcome before assuming the change has solved the original problem for everyone."

    def request(self, raw=None, start=2, end=4, changed=False):
        from fastapi.testclient import TestClient
        from app.main import app
        reads = [deepcopy(self.script), deepcopy(self.script)]
        if changed:
            reads[1][0]["text"] = "Concurrent edit"
        with patch.object(production, "load_script", side_effect=[{"script": value} for value in reads]), \
             patch.object(production, "load_episode_detail", return_value={"config": {"target_duration": 60, "topic": "Evidence"}}), \
             patch.object(production, "build_source_context", return_value={}), \
             patch("app.services.production.llm_writer._call_bridge", return_value=(self.raw if raw is None else raw, "governance_bridge")), \
             patch.object(production, "save_script") as save, TestClient(app) as client:
            response = client.post("/api/episodes/edit-script", json={"episode_id": "test", "edit_type": "regenerate_section", "section_start": start, "section_end": end})
            saved = save.call_args.args[1] if save.called else None
        return response, saved

    def test_only_selected_slice_changes(self):
        response, saved = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(saved[:2], self.script[:2])
        self.assertEqual(saved[4:], self.script[4:])
        self.assertNotEqual(saved[2:4], self.script[2:4])
        self.assertEqual(saved[2]["line_number"], 3)
        self.assertEqual(saved[3]["generated_by"], "governance_bridge")

    def test_bad_range_is_rejected_without_saving(self):
        response, saved = self.request(start=-1)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(saved)

    def test_offline_writer_leaves_script_unchanged(self):
        response, saved = self.request(raw="")
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_quality_checks_reject_unresolved_templates(self):
        response, saved = self.request(raw=self.raw.replace("revised evidence", "{missing_source}"))
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_wrong_speaker_order_is_rejected(self):
        response, saved = self.request(raw=self.raw.replace("PHIL [curious]", "JIM [curious]"))
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_concurrent_edit_is_not_overwritten(self):
        response, saved = self.request(changed=True)
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(saved)


class ToneTests(unittest.TestCase):
    def test_dialogue_changes_are_scoped_and_keep_authorship(self):
        from app.services.production.script_edits import adjust_tone
        original = [{"speaker": "phil", "text": "An idea", "generated_by": "llamacpp"},
                    {"speaker": "jim", "text": "Show me evidence", "generated_by": "llamacpp"},
                    {"speaker": "announcer_male", "text": "Sponsor message"}]
        changed = adjust_tone(original, "more_humorous")
        self.assertEqual(changed[0]["text"], "An idea!")
        self.assertEqual(changed[1]["text"], "Show me evidence You know?")
        self.assertEqual(changed[0]["generated_by"], "llamacpp")
        self.assertEqual(changed[2], original[2])
        self.assertEqual(adjust_tone(changed, "more_humorous"), changed)
        self.assertEqual(original[0]["text"], "An idea")
        self.assertEqual(adjust_tone(original, "faster_paced", 1, 2)[0], original[0])

    def test_pacing_is_used_by_audio_segments(self):
        from app.services.production.script_edits import adjust_tone
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.voices_config = {"phil": {"primary_voice": "test"}}
        def synthesize(**kwargs):
            kwargs["output_path"].write_bytes(b"fake TTS")
            return "kokoro"
        for adjustment, expected in [("faster_paced", 0.2), ("slower_paced", 1.0)]:
            script = adjust_tone([{"speaker": "phil", "text": "Test dialogue"}], adjustment)
            with tempfile.TemporaryDirectory() as directory, \
                 patch.object(worker, "_synthesize_line", side_effect=synthesize), \
                 patch.object(worker, "_probe_duration_seconds", return_value=1):
                segments = worker._synthesize_segments(script, Path(directory), "test")
            self.assertEqual(segments[0]["pause_after"], expected)

    def test_version_history_and_rollback_preserve_original_script(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.storage import episode_store as store
        original = [{"speaker": "phil", "text": "Original dialogue!", "generated_by": "llamacpp"},
                    {"speaker": "jim", "text": "Keep the evidence", "generated_by": "llamacpp"}]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(store, "EPISODES_ROOT", Path(directory)), TestClient(app) as client:
            store.save_script("test", original)
            response = client.post("/api/episodes/edit-script", json={"episode_id": "test", "edit_type": "adjust_tone", "tone_adjustment": "more_serious"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(store.load_script("test")["script"][0]["text"], "Original dialogue.")
            self.assertEqual(len(store.list_script_versions("test")), 2)
            response = client.post("/api/episodes/test/rollback?version=1")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(store.load_script("test")["script"], original)


class EngineStatisticsTests(unittest.TestCase):
    def test_split_lines_report_actual_engines_in_metadata_and_progress(self):
        from types import SimpleNamespace
        import json
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.voices_config = {"phil": {"primary_voice": "test"}, "jim": {"primary_voice": "test"}}
        worker.project_config = {}
        worker.qwen_tts_config = {}
        engines = iter(["kokoro", "edge", "qwen", "kokoro"])
        def synthesize(**kwargs):
            kwargs["output_path"].write_bytes(b"fake TTS")
            return next(engines)
        def mix(segments, path):
            path.write_bytes(b"fake mix")
        def process(**kwargs):
            kwargs["output_file"].write_bytes(b"fake processed audio")
            return {"processing_chain": "test"}
        worker.post_processor = SimpleNamespace(process_episode=process)
        events = []
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(worker, "_synthesize_line", side_effect=synthesize), \
             patch.object(worker, "_split_for_tts", return_value=["First chunk", "Second chunk"]), \
             patch.object(worker, "_concatenate_segments", side_effect=mix), \
             patch.object(worker, "_probe_duration_seconds", return_value=1):
            worker.base_path = Path(directory)
            result = worker.produce_episode("test", "Title", "Topic", [
                {"speaker": "phil", "text": "First original line"},
                {"speaker": "jim", "text": "Second original line"}], events.append)
            metadata = result["metadata"]
            self.assertEqual(metadata["engine_stats"], {"kokoro": 2, "edge": 1, "qwen": 1})
            self.assertEqual(metadata["engine_line_stats"], {"kokoro": 2, "edge": 1, "qwen": 1})
            self.assertEqual(metadata["synthesized_line_count"], 2)
            self.assertEqual(events[-2]["engine_stats"], metadata["engine_stats"])
            self.assertEqual(json.loads((Path(directory) / "episodes/test/production_metadata.json").read_text())["engine_stats"], metadata["engine_stats"])

    def test_two_chunks_on_one_engine_count_as_one_line(self):
        stats = HardenedPodcastWorker.summarize_engines([
            {"engine": "kokoro", "line_index": 1}, {"engine": "kokoro", "line_index": 1}])
        self.assertEqual(stats["engine_stats"], {"kokoro": 2})
        self.assertEqual(stats["engine_line_stats"], {"kokoro": 1})


class EpisodeContractTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.storage import episode_store as store
        self.store = store
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        episodes = root / "episodes"
        for name, value in [("EPISODES_ROOT", episodes), ("DRAFTS_ROOT", episodes / ".drafts"),
                            ("JOBS_ROOT", episodes / ".drafts/jobs")]:
            self.stack.enter_context(patch.object(store, name, value))
        self.stack.enter_context(patch.object(production, "PROJECT_ROOT", root))
        self.client = self.stack.enter_context(TestClient(app))

    def create(self, **extra):
        response = self.client.post("/api/episodes/create", json={"episode_id": "contract", "title": "Title", "topic": "Topic", **extra})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["job_id"]

    def test_config_edits_and_script_feed_reuse_the_original_job(self):
        job = self.create(generation_mode="script_feed", provided_script=[{"speaker": "phil", "text": "Old text"}])
        response = self.client.patch("/api/episodes/contract/config", json={"provided_script": [{"speaker": "phil", "text": "New supplied text"}]})
        self.assertEqual(response.status_code, 200)
        detail = self.client.get("/api/episodes/contract").json()
        self.assertEqual(detail["job_id"], job)
        response = self.client.post(f"/api/episodes/generate-script?job_id={job}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["script"][0]["text"], "New supplied text")

    def test_production_keeps_word_gate_and_persists_job_statistics(self):
        job = self.create()
        self.store.save_script("contract", [{"speaker": "phil", "text": "Too short", "generated_by": "llamacpp"}])
        response = self.client.post(f"/api/episodes/produce?job_id={job}")
        self.assertEqual(response.status_code, 400)
        script = [{"speaker": "phil" if i % 2 == 0 else "jim", "text": f"Point {i} " + " ".join(f"evidence{j}" for j in range(50)), "generated_by": "llamacpp"} for i in range(100)]
        self.store.save_script("contract", script)
        store = self.store
        class Worker:
            def produce_episode(self, **kwargs):
                kwargs["progress_callback"]({"stage": "synthesizing", "progress": 0.5, "engine_stats": {"kokoro": 1}})
                audio = store.episode_dir("contract") / "audio.mp3"
                audio.write_bytes(b"mock TTS audio")
                return {"audio_file": str(audio), "metadata": {"engine_stats": {"kokoro": 2, "edge": 1}, "engine_line_stats": {"kokoro": 2, "edge": 1}}}
        with patch.object(production, "MergedDandyPodcastWorker", Worker), \
             patch.object(production, "export_social_package"):
            response = self.client.post(f"/api/episodes/produce?job_id={job}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "queued")
        status = self.client.get("/api/episodes/contract/production-status").json()
        self.assertEqual(status["status"], "produced")
        self.assertEqual(status["job_id"], job)
        self.assertEqual(self.store.load_job(job)["status"], "produced")
        self.assertEqual(self.client.get("/api/episodes/contract").json()["engine_stats"], {"kokoro": 2, "edge": 1})

    def test_duplicate_production_does_not_replace_active_job(self):
        job = self.create()
        self.store.save_json(self.store.episode_dir("contract") / "status.json", {"status": "producing", "job_id": job})
        response = self.client.post(f"/api/episodes/produce?job_id={job}")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/episodes/contract").json()["job_id"], job)

    def test_existing_editor_and_export_routes(self):
        self.create(generation_mode="script_feed")
        self.store.save_script("contract", [{"speaker": "phil", "text": "First line"}, {"speaker": "jim", "text": "Second line"}])
        actions = [
            {"edit_type": "modify_line", "line_index": 0, "new_content": {"speaker": "phil", "text": "Changed first line"}},
            {"edit_type": "add_line", "line_index": 1, "new_content": {"speaker": "jim", "text": "Inserted line"}},
            {"edit_type": "reorder_lines", "new_order": [2, 1, 0]},
            {"edit_type": "remove_line", "line_index": 1},
        ]
        for action in actions:
            response = self.client.post("/api/episodes/edit-script", json={"episode_id": "contract", **action})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([line["text"] for line in self.store.load_script("contract")["script"]], ["Second line", "Changed first line"])
        for format in ("json", "txt", "srt"):
            self.assertEqual(self.client.get(f"/api/episodes/contract/export?format={format}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
