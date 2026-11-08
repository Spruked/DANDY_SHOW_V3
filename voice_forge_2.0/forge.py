"""
Voice Forge 2.0 - Deterministic Voice Minting
Mint once, use forever. No retries, no randomness, no complexity.
"""

import torch
import torchaudio
from pathlib import Path
from typing import Optional, Dict, Any
import json
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from config import CONFIG
import traceback

class VoiceForge:
    """
    Deterministic voice minting engine.
    Loads XTTS once, mints embeddings deterministically.
    """

    def __init__(self):
        self.model = None
        self.config = CONFIG
        self._load_model()

    def _load_model(self):
        """Load XTTS model - immutable after load"""
        print(f"🔥 Loading XTTS v2 on {self.config.DEVICE}...")

        try:
            # Load config
            xtts_config = XttsConfig()
            xtts_config.load_json(
                str(Path.home() / f".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/config.json")
            )

            # Initialize model
            self.model = Xtts.init_from_config(xtts_config)
            self.model.load_checkpoint(
                xtts_config,
                checkpoint_dir=str(Path.home() / ".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"),
                eval=True,
                use_deepspeed=False
            )
            self.model.to(self.config.DEVICE)

            print("✅ XTTS loaded successfully")

        except Exception as e:
            print(f"❌ Failed to load XTTS: {e}")
            traceback.print_exc()
            raise

    def mint_voice_embedding(
        self,
        character: str,
        sample_path: Path,
        overwrite: bool = False
    ) -> Optional[Path]:
        """
        Mint a permanent voice embedding from a single clean sample.

        Args:
            character: Character name (phil, jim, bryan, cali)
            sample_path: Path to WAV file (45-90 seconds, clean)
            overwrite: Whether to replace existing embedding

        Returns:
            Path to saved embedding or None if failed
        """

        # Validate character
        if character not in self.config.CHARACTERS:
            print(f"❌ Unknown character: {character}")
            return None

        # Check if embedding already exists
        embedding_path = self.config.EMBEDDINGS_DIR / f"{character}_voice.pt"
        if embedding_path.exists() and not overwrite:
            print(f"⚠️  Embedding exists: {embedding_path}")
            print(f"   Use overwrite=True to replace")
            return embedding_path

        # Validate sample exists
        if not sample_path.exists():
            print(f"❌ Sample not found: {sample_path}")
            return None

        print(f"\n🎙️ Minting voice: {character}")
        print(f"   Sample: {sample_path}")
        print(f"   Target: {embedding_path}")

        try:
            # Load audio
            waveform, sample_rate = torchaudio.load(sample_path)

            # Ensure mono
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)

            # Resample if needed
            if sample_rate != self.config.SAMPLE_RATE:
                print(f"   Resampling {sample_rate} → {self.config.SAMPLE_RATE}")
                resampler = torchaudio.transforms.Resample(
                    sample_rate, self.config.SAMPLE_RATE
                )
                waveform = resampler(waveform)

            # Get reference audio tensor
            reference_audio = waveform.squeeze().numpy()

            # Generate conditioning (deterministic)
            print(f"   Generating conditioning (this takes ~30s)...")

            with torch.no_grad():
                # Use multiple reference frames for stability
                gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
                    audio_path=str(sample_path),
                    max_ref_length=self.config.MAX_REF_LENGTH,
                    gpt_cond_len=self.config.GPT_COND_LEN,
                    sound_norm_refs=False,
                    load_sr=self.config.SAMPLE_RATE
                )

            # Save embedding
            embedding_data = {
                "character": character,
                "gpt_cond_latent": gpt_cond_latent.cpu(),
                "speaker_embedding": speaker_embedding.cpu(),
                "sample_path": str(sample_path),
                "sample_rate": self.config.SAMPLE_RATE,
                "minted_at": str(Path().stat().st_mtime),
                "forge_version": self.config.VERSION,
                "config": {
                    "max_ref_length": self.config.MAX_REF_LENGTH,
                    "gpt_cond_len": self.config.GPT_COND_LEN
                }
            }

            torch.save(embedding_data, embedding_path)

            print(f"✅ Voice minted successfully")
            print(f"   Size: {embedding_path.stat().st_size / 1024 / 1024:.2f} MB")

            return embedding_path

        except Exception as e:
            print(f"❌ Minting failed: {e}")
            traceback.print_exc()
            return None

    def mint_all_characters(self):
        """Mint all character voices from samples directory"""
        print("\n" + "="*50)
        print("VOICE FORGE 2.0 - MINTING ALL CHARACTERS")
        print("="*50)

        results = {}

        for character in self.config.CHARACTERS.keys():
            sample_dir = self.config.SAMPLES_DIR / character
            sample_files = list(sample_dir.glob("*.wav"))

            if not sample_files:
                print(f"⚠️  No sample found for {character} in {sample_dir}")
                results[character] = None
                continue

            # Use first WAV found
            sample_path = sample_files[0]
            result = self.mint_voice_embedding(character, sample_path)
            results[character] = result

        print("\n" + "="*50)
        print("MINTING COMPLETE")
        print("="*50)

        for char, path in results.items():
            status = "✅" if path else "❌"
            print(f"{status} {char}: {path}")

        return results

def main():
    """CLI entry point"""
    forge = VoiceForge()
    forge.mint_all_characters()

if __name__ == "__main__":
    main()
