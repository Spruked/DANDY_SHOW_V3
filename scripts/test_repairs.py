"""Focused regressions; all generated files use temporary directories."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api import production, library
from app.services.production import worker as worker_module
from app.services.production.worker import HardenedPodcastWorker
from app.services.production.intro_outro import _clip
from app.services.production import intro_outro
from app.services.storage import episode_store
from app.core import settings
from pydub import AudioSegment


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.audio = self.root / "audio.mp3"
        self.audio.write_bytes(b"previous production")
        self.paths = patch.object(production, "episode_dir", return_value=self.root)
        self.paths.start()
        production._CANCEL_EVENTS.clear()
        self.lines = [{"speaker": "phil", "text": "A complete test sentence.", "generated_by": "llamacpp"}]

    def tearDown(self):
        self.paths.stop()
        production._CANCEL_EVENTS.clear()
        self.temp.cleanup()

    def run_production(self, worker, export=None):
        with patch.object(production, "_get_worker", return_value=worker), \
             patch.object(production, "load_media_cues", return_value={}), \
             patch.object(production, "export_social_package", export or Mock()) as social:
            production._run_produce_background(
                episode_id="repair-test", job_id="repair-job", script=self.lines,
                title="Test", topic="Test", script_text="Test",
                personality_settings=None, voice_settings={},
            )
            return social

    def test_tts_failure_preserves_audio_and_does_not_export_silence(self):
        fake = Mock()
        fake.produce_episode.side_effect = RuntimeError("Kokoro unavailable")
        social = self.run_production(fake)
        status = json.loads((self.root / "status.json").read_text())
        self.assertEqual(status["status"], "production_failed")
        self.assertIn("Kokoro unavailable", status["error"])
        self.assertEqual(self.audio.read_bytes(), b"previous production")
        social.assert_not_called()
        self.assertFalse((self.root / "production_result.json").exists())
        self.assertNotIn("repair-job", production._CANCEL_EVENTS)

    def test_worker_initialization_failure_is_recorded(self):
        with patch.object(production, "_get_worker", side_effect=RuntimeError("initialization failed")):
            production._run_produce_background(
                episode_id="repair-test", job_id="repair-job", script=self.lines,
                title="Test", topic="Test", script_text="Test", personality_settings=None, voice_settings={},
            )
        self.assertEqual(json.loads((self.root / "status.json").read_text())["status"], "production_failed")

    def test_cancel_does_not_become_failure_or_success(self):
        production._job_cancel_event("repair-job").set()
        fake = Mock()
        self.run_production(fake)
        fake.produce_episode.assert_not_called()
        self.assertEqual(json.loads((self.root / "status.json").read_text())["status"], "production_cancelled")
        self.assertNotIn("repair-job", production._CANCEL_EVENTS)

    def test_social_failure_keeps_real_audio_success(self):
        fake = Mock()
        fake.produce_episode.return_value = {"audio_file": str(self.audio), "metadata": {}}
        self.run_production(fake, Mock(side_effect=RuntimeError("render failed")))
        status = json.loads((self.root / "status.json").read_text())
        self.assertEqual(status["status"], "produced")
        self.assertEqual(status["social_export_error"], "render failed")
        self.assertTrue((self.root / "production_result.json").exists())

    def test_missing_output_is_a_failure(self):
        fake = Mock()
        fake.produce_episode.return_value = {"audio_file": str(self.root / "missing.mp3")}
        social = self.run_production(fake)
        social.assert_not_called()
        self.assertEqual(json.loads((self.root / "status.json").read_text())["status"], "production_failed")

    def test_srt_rolls_over_minutes_and_hours(self):
        srt = production._script_as_srt(self.lines * 901)
        self.assertIn("00:00:56,000 --> 00:01:00,000", srt)
        self.assertIn("01:00:00,000 --> 01:00:04,000", srt)
        self.assertNotIn("00:00:60,000", srt)

    def test_invalid_edits_never_save(self):
        cases = [
            {"edit_type": "remove_line", "line_index": -1},
            {"edit_type": "reorder_lines", "new_order": [0, 0]},
            {"edit_type": "reorder_lines", "new_order": []},
            {"edit_type": "expand_script"},
        ]
        with patch.object(production, "load_script", return_value={"script": self.lines}), \
             patch.object(production, "save_script") as save:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(production.HTTPException):
                    asyncio.run(production.edit_script(production.EditScriptRequest(episode_id="test", **case)))
            save.assert_not_called()

    def test_selected_engine_does_not_fall_back(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.project_config = {"tts": {"primary_engine": "kokoro"}}
        worker.qwen_tts_config = {"enabled": True}
        worker._try_kokoro = Mock(side_effect=RuntimeError("unavailable"))
        worker._try_qwen_bridge = Mock()
        worker._synthesize_edge = Mock()
        with self.assertRaises(RuntimeError):
            worker._synthesize_line("text", "phil", "neutral", self.root / "new.mp3")
        worker._try_qwen_bridge.assert_not_called()
        worker._synthesize_edge.assert_not_called()
        worker.project_config["tts"]["primary_engine"] = "qwen"
        self.assertEqual(worker._synthesize_line("text", "phil", "neutral", self.root / "new.mp3"), "qwen")

    def test_wrap_failure_does_not_replace_published_audio(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.base_path = self.root
        worker.project_config = {"intro_outro": {"enabled": True}}
        worker.voices_config = {}
        worker._synthesize_segments = Mock(return_value=[{}])
        worker._concatenate_segments = Mock(side_effect=lambda segments, path: path.write_bytes(b"mix"))
        worker.post_processor = Mock()
        worker.post_processor.process_episode.side_effect = lambda **kw: (kw["output_file"].write_bytes(b"new") and {})
        destination = self.root / "episodes" / "repair-test" / "audio.mp3"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"published")
        with patch.object(worker_module, "wrap_episode_audio", side_effect=RuntimeError("announcer failed")):
            with self.assertRaisesRegex(RuntimeError, "announcer failed"):
                worker.produce_episode("repair-test", "Test", "Test", self.lines)
        self.assertEqual(destination.read_bytes(), b"published")

    def test_empty_intro_voice_uses_kokoro_default(self):
        with patch.object(intro_outro, "_load_music", return_value=AudioSegment.silent(20000)), \
             patch.object(intro_outro, "_synthesize_kokoro_sync", side_effect=RuntimeError("stop before audio export")) as synth:
            with self.assertRaises(RuntimeError):
                intro_outro.build_intro({"intro": {"announcer_voice": ""}}, self.root, self.audio)
        self.assertEqual(synth.call_args.args[1], "am_eric")

    def test_invalid_music_clip_fails_clearly(self):
        with self.assertRaises(ValueError):
            _clip(AudioSegment.silent(100), 100, 50)

    def test_settings_refresh_reaches_cached_worker(self):
        fake = Mock()
        with patch.object(production, "_WORKER", fake), \
             patch.object(settings, "load_project_config", return_value={"tts": {"primary_engine": "qwen"}}):
            self.assertEqual(production._get_worker().project_config["tts"]["primary_engine"], "qwen")

    def test_interrupted_job_is_reported_without_rewriting_status(self):
        with patch.object(library, "load_episode_detail", return_value={"status": "producing", "job_id": "old"}):
            detail = asyncio.run(library.episode_detail("test"))
        self.assertEqual(detail["status"], "interrupted")
        self.assertFalse(detail["job_active"])

    def test_duplicate_job_cannot_reset_cancellation(self):
        event = production._job_cancel_event("repair-job", reset=True)
        event.set()
        with self.assertRaises(production.HTTPException):
            production._job_cancel_event("repair-job", reset=True)
        self.assertTrue(event.is_set())


if __name__ == "__main__":
    unittest.main()
