import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, Mock

from app.core.safety import atomic_json, contained_path, validate_id, file_lock
from app.services.storage import episode_store as store
from app.services.production.worker import HardenedPodcastWorker


class SafetyTests(unittest.TestCase):
    def test_traversal_and_absolute_ids_rejected(self):
        for value in ["../config", "..", "C:\\Windows", "a/b", "a\\b", ".drafts", "x:y", "a."]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_id(value)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                contained_path(Path(directory), "../escape")

    def test_failed_atomic_replace_preserves_existing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_json(path, {"before": True})
            with patch("app.core.safety.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"after": True})
            self.assertEqual(json.loads(path.read_text()), {"before": True})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_parallel_versions_are_unique_and_recovery_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch.multiple(store,
                EPISODES_ROOT=Path(directory), DRAFTS_ROOT=Path(directory)/".drafts",
                JOBS_ROOT=Path(directory)/".drafts/jobs"):
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: store.save_script_version("test", [{"text": "line"}]), range(12)))
            self.assertEqual(len(store.list_script_versions("test")), 12)
            store.save_json(store.episode_dir("test")/"status.json", {"status": "producing", "job_id": "job_test"})
            store.recover_interrupted_jobs()
            self.assertEqual(store.load_episode_detail("test")["status"], "interrupted")
            self.assertEqual(store.load_job("job_test")["status"], "interrupted")

    def test_required_qwen_never_calls_other_engines(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.qwen_tts_config = {"enabled": True, "production": {"required_engine": "qwen"}}
        worker.runtime = Mock(primary_engine="kokoro")
        worker._try_qwen_bridge = Mock(side_effect=RuntimeError("offline"))
        worker._try_kokoro = Mock()
        worker._synthesize_edge = Mock()
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, "substitution is disabled"):
            worker._synthesize_line("test", "phil", "neutral", Path(directory)/"voice.mp3")
        worker._try_kokoro.assert_not_called()
        worker._synthesize_edge.assert_not_called()

    def test_busy_production_slot_is_rejected(self):
        from app.api import production
        self.assertTrue(production._PRODUCTION_SLOT.acquire(blocking=False))
        try:
            self.assertFalse(production._PRODUCTION_SLOT.acquire(blocking=False))
        finally:
            production._PRODUCTION_SLOT.release()


class BackupTests(unittest.TestCase):
    def test_media_roundtrip_and_traversal_rejection(self):
        import importlib.util
        import zipfile
        source = Path(__file__).resolve().parents[2] / "scripts/studio/backup.py"
        spec = importlib.util.spec_from_file_location("studio_backup", source)
        backup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backup)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/"source"
            audio = root/"episodes/test/audio.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"original media")
            with patch.multiple(backup, ROOT=root, BACKUP_DIR=root/"archive/backups"):
                archive = backup.run("test")
            restored = Path(directory)/"restored"
            backup.restore_archive(archive, restored)
            self.assertEqual((restored/"episodes/test/audio.mp3").read_bytes(), b"original media")
            unsafe = Path(directory)/"unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as zf:
                zf.writestr("../escape", "bad")
            with self.assertRaises(ValueError):
                backup.restore_archive(unsafe, Path(directory)/"rejected")
            self.assertFalse((Path(directory)/"escape").exists())
