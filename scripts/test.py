"""Run isolated backend tests from any working directory."""
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root / "backend/tests")))
raise SystemExit(not result.wasSuccessful())
