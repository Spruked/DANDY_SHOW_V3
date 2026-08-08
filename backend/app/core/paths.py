from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = PROJECT_ROOT / "config"
EPISODES_ROOT = PROJECT_ROOT / "episodes"
LOGS_ROOT = PROJECT_ROOT / "logs"
STAGING_ROOT = PROJECT_ROOT / "staging"
ARCHIVE_ROOT = PROJECT_ROOT / "archive"

