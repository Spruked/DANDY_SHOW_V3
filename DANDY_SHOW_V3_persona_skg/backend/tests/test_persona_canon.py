"""Canon persona files: loading, fingerprints, family content and the learning guard.

Standard library only (persona_canon.py), so this runs in CI without torch.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import persona_canon as canon  # noqa: E402


class PersonaCanonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "config" / "characters", self.tmp / "config" / "characters")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edit(self, character_id, change):
        path = self.tmp / "config" / "characters" / f"{character_id}.persona.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_both_personas_load_with_brothers_and_birth_order(self):
        phil = canon.load_persona("phil", self.tmp)
        jim = canon.load_persona("jim", self.tmp)
        self.assertEqual(phil["identity"]["full_name"], "Phillip Dandridge")
        self.assertEqual(jim["identity"]["full_name"], "James Arthur Dandridge")
        self.assertEqual(phil["identity"]["birth_order"], "younger")
        self.assertEqual(jim["identity"]["birth_order"], "older")
        self.assertEqual(phil["shared_family"], jim["shared_family"])

    def test_brief_carries_family_canon_for_each_brother_only(self):
        phil = canon.persona_brief(canon.load_persona("phil", self.tmp))
        jim = canon.persona_brief(canon.load_persona("jim", self.tmp))
        for word in ("Dandridge", "Joplin", "younger", "Mary Virginia", "Lip", "Stew", "Milo", "Precious",
                     "Duke", "Phillip Micheal", "Rose Mary"):
            self.assertIn(word, phil)
        for word in ("Dandridge", "Joplin", "older", "Laura", "Ethan", "Claire", "Duke",
                     "Phillip Micheal", "Rose Mary"):
            self.assertIn(word, jim)
        for word in ("Laura", "Ethan", "Claire"):
            self.assertNotIn(word, phil)
        for word in ("Mary Virginia", "Milo", "Precious"):
            self.assertNotIn(word, jim)

    def test_shared_family_edited_without_fingerprint_fails_closed(self):
        self._edit("phil", lambda d: d["shared_family"]["childhood_dog"].update(name="Rex"))
        for character_id in ("phil", "jim"):
            with self.assertRaises(canon.PersonaIntegrityError):
                canon.load_persona(character_id, self.tmp)

    def test_shared_family_that_differs_between_files_fails_closed(self):
        def change(d):
            d["shared_family"]["childhood_dog"]["name"] = "Rex"
            d["shared_family_sha256"] = canon.shared_family_fingerprint(d["shared_family"])
        self._edit("phil", change)
        with self.assertRaises(canon.PersonaIntegrityError):
            canon.load_persona("jim", self.tmp)

    def test_birth_order_contradiction_fails_closed(self):
        self._edit("phil", lambda d: d["identity"].update(birth_order="older"))
        with self.assertRaises(canon.PersonaIntegrityError):
            canon.load_persona("phil", self.tmp)

    def test_learning_guard_rejects_family_references(self):
        phil = canon.load_persona("phil", self.tmp)
        sibling = set(phil["_sibling_canon_names"])
        self.assertTrue(canon.style_only("You ever think about how a reel is a feedback loop...", phil, sibling))
        self.assertFalse(canon.style_only("Milo taught Lip to fish...", phil, sibling))
        self.assertFalse(canon.style_only("Laura would never buy that.", phil, sibling))

    def test_cache_dir_default_and_override_and_manifest(self):
        phil = canon.load_persona("phil", self.tmp)
        default = canon.skg_cache_dir("phil", self.tmp)
        self.assertEqual(default, self.tmp / "phil_dandy_skg_v3")
        canon.write_cache_manifest(default, phil, "test")
        manifest = json.loads((default / "cache_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["persona_sha256"], phil["_file_sha256"])
        import os
        os.environ[canon.CACHE_ENV] = str(self.tmp / "cache_root")
        try:
            self.assertEqual(canon.skg_cache_dir("jim", self.tmp), self.tmp / "cache_root" / "jim")
        finally:
            del os.environ[canon.CACHE_ENV]


if __name__ == "__main__":
    unittest.main()
