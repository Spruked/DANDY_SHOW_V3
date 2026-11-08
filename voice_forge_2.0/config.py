"""
Voice Forge 2.0 Configuration
Broadcast-grade XTTS settings for character consistency
"""

from pathlib import Path
import torch

class VoiceForgeConfig:
    """Immutable XTTS configuration - change requires version bump"""

    # ── PATHS ──
    BASE_DIR = Path(__file__).parent.resolve()
    SAMPLES_DIR = BASE_DIR / "samples"
    EMBEDDINGS_DIR = BASE_DIR / "embeddings"
    OUTPUT_DIR = BASE_DIR / "output" / "generated"

    # ── XTTS MODEL ──
    MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    # ── MINTING SETTINGS ──
    # Longer samples = more stable embeddings
    MAX_REF_LENGTH = 90        # Seconds - matches your 60s+ samples
    GPT_COND_LEN = 12          # Conditioning length (DO NOT CHANGE)
    SAMPLE_RATE = 24000        # XTTS native rate

    # ── SYNTHESIS SETTINGS ──
    TEMPERATURE = 0.65         # Sweet spot: natural but controlled
    LENGTH_PENALTY = 1.0       # No artificial compression
    REPETITION_PENALTY = 2.0   # Prevents stuttering
    TOP_K = 50                 # Vocabulary sampling
    TOP_P = 0.85               # Nucleus sampling

    # ── CHARACTER PROFILES ──
    CHARACTERS = {
        "phil": {
            "name": "Phil Dandy",
            "age_range": "45-55",
            "vocal_traits": ["baritone", "measured", "witty_pause"],
            "baseline_emotion": "dry_humor",
            "speaking_pace": "deliberate",
            "comedic_timing": "deadpan_with_injections"
        },
        "jim": {
            "name": "Jim Dandy",
            "age_range": "40-50",
            "vocal_traits": ["tenor", "energetic", "staccato"],
            "baseline_emotion": "enthusiastic_sarcasm",
            "speaking_pace": "quick_witted",
            "comedic_timing": "punchline_focused"
        },
        "bryan": {
            "name": "Bryan Lund",
            "kokoro_voice": "am",     # American male voice
            "age_range": "35-45",
            "vocal_traits": ["bass_baritone", "thoughtful", "reserved_power"],
            "baseline_emotion": "earnest_intensity",
            "speaking_pace": "considered",
            "comedic_timing": "sudden_deadly_serious"
        },
        "cali": {
            "name": "Cali",
            "age_range": "30-40",
            "vocal_traits": ["alto", "confident", "smooth"],
            "baseline_emotion": "calm_assurance",
            "speaking_pace": "steady",
            "comedic_timing": "subtle_irony"
        }
    }

    # ── SECURITY ──
    # Prevent unauthorized model tampering
    ALLOWED_MODEL_SOURCES = [
        "coqui.ai",
        "huggingface.co/coqui"
    ]

    # ── VERSION ──
    VERSION = "2.1.0"
    VERSION_FILE = BASE_DIR / "forge_version.txt"

# ── Instantiate ──
CONFIG = VoiceForgeConfig()

# Ensure directories exist
CONFIG.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
CONFIG.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
