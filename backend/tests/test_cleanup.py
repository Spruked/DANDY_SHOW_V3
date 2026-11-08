import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.safety import file_lock
from app.api import production


class CleanupTests(unittest.TestCase):
    def test_tests_can_run_while_runtime_lock_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with file_lock(root / "production" / "studio-runtime"):
                with TestClient(create_app(runtime_root=root / "tests", recover_jobs=False)) as client:
                    self.assertEqual(client.get("/").status_code, 200)

    def test_placeholder_expansion_never_saves(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(production, "load_script", return_value={"script": [{"speaker": "phil", "text": "Keep original"}]}), \
             patch.object(production, "save_script") as save, \
             TestClient(create_app(runtime_root=Path(directory), recover_jobs=False)) as client:
            response = client.post("/api/episodes/edit-script", json={"episode_id": "test", "edit_type": "expand_script"})
            self.assertEqual(response.status_code, 422)
            save.assert_not_called()

    def test_legacy_imports_delegate_to_canonical_modules(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        for name, symbol in [("worker", "HardenedPodcastWorker"), ("context_builder", "build_rich_context"), ("quality_guard", "ScriptQualityGuard")]:
            legacy = importlib.import_module(name)
            canonical = importlib.import_module("backend.app.services.production." + name)
            self.assertIs(getattr(legacy, symbol), getattr(canonical, symbol))

    def test_semantic_dependency_is_not_stubbed(self):
        import sys
        from app.services.production import personality_loader
        self.assertFalse(hasattr(personality_loader, "_ensure_sentence_transformers_stub"))
        self.assertNotIn("sentence_transformers", sys.modules)

    def test_render_limit_releases_after_failure(self):
        from app.core.resources import render_slot
        from fastapi import HTTPException
        with self.assertRaises(RuntimeError):
            with render_slot():
                with self.assertRaises(HTTPException) as busy:
                    with render_slot():
                        pass
                self.assertEqual(busy.exception.status_code, 429)
                raise RuntimeError("render failed")
        with render_slot():
            pass

    def test_failed_postprocessing_preserves_previous_audio(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        from app.services.production.worker import HardenedPodcastWorker
        with tempfile.TemporaryDirectory() as directory:
            worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
            worker.base_path = Path(directory)
            worker.project_config = {}
            worker.voices_config = {}
            worker._synthesize_segments = Mock(return_value=[])
            worker._concatenate_segments = lambda segments, output: output.write_bytes(b"new mix")
            worker.post_processor = SimpleNamespace(process_episode=Mock(side_effect=RuntimeError("encoder failed")))
            previous = worker.base_path / "episodes/test/audio.mp3"
            previous.parent.mkdir(parents=True)
            previous.write_bytes(b"previous accepted audio")
            with self.assertRaisesRegex(RuntimeError, "previous production was preserved"):
                worker.produce_episode("test", "Title", "Topic", [{"speaker": "phil", "text": "Test line"}])
            self.assertEqual(previous.read_bytes(), b"previous accepted audio")

    def test_real_ffmpeg_normalization(self):
        import shutil
        import subprocess
        from app.services.production.audio_post_processor import FFmpegPostProcessor
        if not shutil.which("ffmpeg"):
            self.skipTest("System FFmpeg is required for real media integration")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=5", "-y", str(root/"input.wav")], check=True, timeout=30)
            result = FFmpegPostProcessor(root).process_episode(root/"input.wav", root/"output.mp3", "phil_jim_mix")
            self.assertTrue(result["compliant"], result)
            self.assertLessEqual(float(result["true_peak"]), -1.0)

    def test_missing_social_outputs_are_not_reported_as_exported(self):
        from app.services.social import package_builder as package
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(package, "_probe_audio_duration", return_value=10), \
             patch.object(package, "build_clip_exports", return_value=[]), \
             patch.object(package, "generate_thumbnail", return_value=None), \
             patch.object(package, "generate_audiogram", return_value=None), \
             patch.object(package, "build_post_copy", return_value={}):
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "nonempty thumbnail"):
                package.export_social_package("test", "Title", "Topic", "Text", [], root/"audio.mp3", root/"social")
            self.assertFalse((root/"social/social_export.json").exists())
