import json
import tempfile
import unittest
from pathlib import Path

from app.services.storage.vault_store import DandyVault


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'enabled': True, 'vault_root': 'Dandy_Vault_System/storage/dandy',
                       'aims_store': 'Dandy_Vault_System/AIMS/data/dandy',
                       'project_paths': ['episodes', 'Dandy_Vault_System', 'frontend/ORBS']}
        self.vault = DandyVault(self.root, self.config)
        self.source = self.root / 'episodes/test/source.txt'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('Original source evidence.', encoding='utf-8')

    def test_restart_dedup_and_restore_preserve_original_versions(self):
        first = self.vault.capture()
        self.assertEqual(self.vault.capture()['snapshot_id'], first['snapshot_id'])
        self.source.write_text('Revised source evidence.', encoding='utf-8')
        second = self.vault.capture()
        self.assertNotEqual(first['snapshot_id'], second['snapshot_id'])
        restarted = DandyVault(self.root, self.config)
        self.assertTrue(restarted.verify()['valid'])
        destination = self.root / 'recovered'
        result = restarted.restore(first['snapshot_id'], destination)
        self.assertEqual(result['restored_files'], 1)
        self.assertEqual((destination / 'episodes/test/source.txt').read_text(), 'Original source evidence.')
        self.assertEqual(self.source.read_text(), 'Revised source evidence.')
        with self.assertRaisesRegex(ValueError, 'new directory'):
            restarted.restore(first['snapshot_id'], destination)

    def test_vault_data_and_git_metadata_never_enter_snapshots(self):
        orb = self.root / 'frontend/ORBS/README.md'
        orb.parent.mkdir(parents=True); orb.write_text('ORBS source')
        git = self.root / 'Dandy_Vault_System/.git/config'
        git.parent.mkdir(parents=True); git.write_text('nested metadata')
        receipt = self.vault.capture()
        self.assertEqual(receipt['file_count'], 2)
        self.assertEqual(self.vault.capture()['snapshot_id'], receipt['snapshot_id'])
        self.assertEqual(len(self.vault.project_files()), 2)

    def test_blob_corruption_is_detected_and_never_overwritten(self):
        receipt = self.vault.capture()
        blob = next((self.vault.root / 'objects').glob('*/*'))
        blob.write_bytes(b'damaged evidence')
        self.assertFalse(self.vault.verify()['valid'])
        with self.assertRaisesRegex(RuntimeError, 'integrity failure'):
            self.vault.capture()
        with self.assertRaisesRegex(RuntimeError, 'damaged vault object'):
            self.vault.restore(receipt['snapshot_id'], self.root / 'recovered')
        self.assertEqual(blob.read_bytes(), b'damaged evidence')
        self.assertEqual(self.source.read_text(), 'Original source evidence.')

    def test_ledger_corruption_fails_closed(self):
        self.vault.capture()
        ledger = self.vault.aims / 'dandy_artifacts.ledger'
        text = ledger.read_text(encoding='utf-8')
        ledger.write_text(text.replace('dandy_snapshot', 'altered_snapshot'), encoding='utf-8')
        with self.assertRaises(Exception):
            self.vault.verify()
        self.assertEqual(self.source.read_text(), 'Original source evidence.')

    def test_outside_project_capture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.vault.capture([self.root.parent / 'outside.txt'])
