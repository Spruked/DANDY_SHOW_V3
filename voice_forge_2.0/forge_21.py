"""
Voice Forge 2.1 - Character Voice Minting with Transformation
"""

import torch
import torchaudio
from pathlib import Path
from typing import Optional, Dict, Any
import json
import traceback
import argparse

# Import our transformation system
from voice_transformer import CharacterVoiceGenerator, VoiceCharacteristics
from config import CONFIG  # Same config as before

class VoiceForge21:
    """Voice Forge with character transformation capabilities"""

    def __init__(self, use_transformed: bool = True):
        self.use_transformed = use_transformed
        self.transformer = CharacterVoiceGenerator() if use_transformed else None
        self.model = None
        self.config = CONFIG
        self._load_model()

    def _load_model(self):
        """Load XTTS model (same as before)"""
        print(f"🔥 Loading XTTS v2.1 on {self.config.DEVICE}...")

        try:
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
            xtts_config = XttsConfig()
            model_dir = Path.home() / "AppData" / "Local" / "tts" / "tts_models--multilingual--multi-dataset--xtts_v2"
            xtts_config.load_json(str(model_dir / "config.json"))

            self.model = Xtts.init_from_config(xtts_config)
            self.model.load_checkpoint(
                xtts_config,
                checkpoint_dir=str(model_dir),
                eval=True,
                use_deepspeed=False
            )
            self.model.to(self.config.DEVICE)

            print("✅ XTTS loaded successfully")

        except Exception as e:
            print(f"❌ Failed to load XTTS: {e}")
            raise

    def mint_character_voice(
        self,
        character: str,
        source_sample_path: Path,
        overwrite: bool = False
    ) -> Optional[Path]:
        """
        Mint a character voice, optionally with transformation
        """

        if character not in self.config.CHARACTERS:
            print(f"❌ Unknown character: {character}")
            return None

        embedding_path = self.config.EMBEDDINGS_DIR / f"{character}_voice.pt"
        if embedding_path.exists() and not overwrite:
            print(f"⚠️  Embedding exists: {embedding_path}")
            return embedding_path

        if self.use_transformed:
            print(f"\n🎭 Creating {character} character voice from your sample...")
            transformed_path = self.config.SAMPLES_DIR / character / f"{character}_transformed.wav"
            transformed_path.parent.mkdir(parents=True, exist_ok=True)
            success = self.transformer.generate_character_sample(
                source_sample_path,
                character,
                transformed_path
            )
            if not success:
                print("❌ Character transformation failed")
                return None
            mint_sample_path = transformed_path
            self._save_transformation_comparison(source_sample_path, transformed_path, character)
        else:
            mint_sample_path = source_sample_path

        return self._mint_from_sample(character, mint_sample_path, embedding_path)

    def _mint_from_sample(
        self,
        character: str,
        sample_path: Path,
        embedding_path: Path
    ) -> Optional[Path]:
        """Mint embedding from sample (core minting logic)"""

        print(f"\n🎙️ Minting {character} voice...")
        print(f"   Source: {sample_path}")
        print(f"   Target: {embedding_path}")

        try:
            print(f"   Generating conditioning...")

            with torch.no_grad():
                gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
                    audio_path=str(sample_path),
                    max_ref_length=self.config.MAX_REF_LENGTH,
                    gpt_cond_len=self.config.GPT_COND_LEN,
                    sound_norm_refs=False,
                    load_sr=self.config.SAMPLE_RATE
                )

            embedding_data = {
                "character": character,
                "gpt_cond_latent": gpt_cond_latent.cpu(),
                "speaker_embedding": speaker_embedding.cpu(),
                "sample_path": str(sample_path),
                "sample_rate": self.config.SAMPLE_RATE,
                "minted_at": str(Path().stat().st_mtime),
                "forge_version": self.config.VERSION,
                "transformed": self.use_transformed,
                "transformation_profile": self.transformer.character_profiles[character] if self.use_transformed else None,
                "config": {
                    "max_ref_length": self.config.MAX_REF_LENGTH,
                    "gpt_cond_len": self.config.GPT_COND_LEN
                }
            }

            torch.save(embedding_data, embedding_path)

            print(f"✅ Voice minted successfully!")
            print(f"   Size: {embedding_path.stat().st_size / 1024 / 1024:.2f} MB")

            return embedding_path

        except Exception as e:
            print(f"❌ Minting failed: {e}")
            traceback.print_exc()
            return None

    def _save_transformation_comparison(
        self,
        original_path: Path,
        transformed_path: Path,
        character: str
    ):
        comparison_dir = self.config.BASE_DIR / "comparisons"
        comparison_dir.mkdir(exist_ok=True)
        original_copy = comparison_dir / f"{character}_original.wav"
        transformed_copy = comparison_dir / f"{character}_transformed.wav"
        import shutil
        shutil.copy2(original_path, original_copy)
        shutil.copy2(transformed_path, transformed_copy)
        report = {
            "character": character,
            "original_sample": str(original_path),
            "transformed_sample": str(transformed_path),
            "transformation_profile": self.transformer.character_profiles[character],
            "comparison_files": {
                "original": str(original_copy),
                "transformed": str(transformed_copy)
            }
        }
        report_path = comparison_dir / f"{character}_transformation_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n📊 Transformation comparison saved:")
        print(f"   Original: {original_copy}")
        print(f"   Transformed: {transformed_copy}")
        print(f"   Report: {report_path}")

    def mint_all_characters(self, source_samples: Dict[str, Path]):
        print("\n" + "="*60)
        print("VOICE FORGE 2.1 - CHARACTER VOICE MINTING")
        print("="*60)

        if self.use_transformed:
            print("🎭 TRANSFORMATION MODE: Your voice → Character voices")
        else:
            print("📻 DIRECT MODE: Using raw samples")

        results = {}

        for character, sample_path in source_samples.items():
            if not sample_path.exists():
                print(f"⚠️  Sample not found for {character}: {sample_path}")
                results[character] = None
                continue

            result = self.mint_character_voice(character, sample_path)
            results[character] = result

        print("\n" + "="*60)
        print("MINTING COMPLETE")
        print("="*60)

        for char, path in results.items():
            status = "✅" if path else "❌"
            mode = "transformed" if self.use_transformed and path else "direct"
            print(f"{status} {char}: {path} ({mode})")

        return results

def main():
    parser = argparse.ArgumentParser(description="Voice Forge 2.1 - Character Voice Minting")
    parser.add_argument(
        "--no-transform",
        action="store_true",
        help="Use raw samples without transformation"
    )
    parser.add_argument(
        "--character",
        choices=["phil", "jim", "bryan", "cali"],
        help="Mint single character (optional)"
    )
    parser.add_argument(
        "--sample",
        type=Path,
        help="Path to source sample (required if --character specified)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing embeddings"
    )

    args = parser.parse_args()

    forge = VoiceForge21(use_transformed=not args.no_transform)

    if args.character and args.sample:
        forge.mint_character_voice(args.character, args.sample, args.overwrite)
    else:
        source_samples = {
            "phil": CONFIG.SAMPLES_DIR / "phil" / "voice_sample.wav",
            "jim": CONFIG.SAMPLES_DIR / "jim" / "voice_sample.wav",
            "bryan": CONFIG.SAMPLES_DIR / "bryan" / "voice_sample.wav",
            "cali": CONFIG.SAMPLES_DIR / "cali" / "cali_sample.wav"
        }

        forge.mint_all_characters(source_samples)

if __name__ == "__main__":
    main()
