"""
Voice Forge 2.0 Synthesis
Generate speech from minted embeddings with deterministic settings
"""

import torch
import torchaudio
from pathlib import Path
from typing import Optional, List, Dict
import json
from TTS.tts.models.xtts import Xtts
from config import CONFIG
import traceback

class VoiceSynthesizer:
    """Deterministic speech synthesis from permanent embeddings"""

    def __init__(self):
        self.model = None
        self.config = CONFIG
        self._load_model()

    def _load_model(self):
        """Load XTTS model (same as forge)"""
        print(f"🔥 Loading XTTS for synthesis on {self.config.DEVICE}...")

        try:
            from TTS.tts.configs.xtts_config import XttsConfig
            xtts_config = XttsConfig()
            xtts_config.load_json(
                str(Path.home() / f".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/config.json")
            )

            self.model = Xtts.init_from_config(xtts_config)
            self.model.load_checkpoint(
                xtts_config,
                checkpoint_dir=str(Path.home() / ".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"),
                eval=True,
                use_deepspeed=False
            )
            self.model.to(self.config.DEVICE)

            print("✅ Synthesis model loaded")

        except Exception as e:
            print(f"❌ Failed to load synthesis model: {e}")
            traceback.print_exc()
            raise

    def load_embedding(self, character: str) -> Optional[Dict[str, torch.Tensor]]:
        """Load character embedding from disk"""
        embedding_path = self.config.EMBEDDINGS_DIR / f"{character}_voice.pt"

        if not embedding_path.exists():
            print(f"❌ Embedding not found: {embedding_path}")
            return None

        try:
            embedding_data = torch.load(embedding_path, map_location=self.config.DEVICE)

            # Verify version compatibility
            if embedding_data.get("forge_version", "1.0") != self.config.VERSION:
                print(f"⚠️  Embedding version mismatch")
                print(f"   Expected: {self.config.VERSION}")
                print(f"   Found: {embedding_data.get('forge_version')}")

            return {
                "gpt_cond_latent": embedding_data["gpt_cond_latent"].to(self.config.DEVICE),
                "speaker_embedding": embedding_data["speaker_embedding"].to(self.config.DEVICE)
            }

        except Exception as e:
            print(f"❌ Failed to load embedding: {e}")
            return None

    def synthesize(
        self,
        character: str,
        text: str,
        output_path: Optional[Path] = None,
        language: str = "en"
    ) -> Optional[Path]:
        """
        Synthesize speech for character with deterministic settings

        Args:
            character: Character name
            text: Text to synthesize
            output_path: Optional custom output path
            language: Language code

        Returns:
            Path to generated audio or None
        """

        # Load embedding
        embedding = self.load_embedding(character)
        if not embedding:
            return None

        # Generate output filename
        if output_path is None:
            # Create sanitized filename from text start
            safe_text = "".join(c for c in text[:30] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_text = safe_text.replace(' ', '_')
            timestamp = Path().stat().st_mtime

            output_path = self.config.OUTPUT_DIR / f"{character}_{timestamp}_{safe_text}.wav"

        print(f"\n🎧 Synthesizing: {character}")
        print(f"   Text: \"{text[:60]}...\"")
        print(f"   Output: {output_path.name}")

        try:
            with torch.no_grad():
                # Generate with deterministic settings
                outputs = self.model.inference(
                    text=text,
                    language=language,
                    gpt_cond_latent=embedding["gpt_cond_latent"],
                    speaker_embedding=embedding["speaker_embedding"],
                    temperature=self.config.TEMPERATURE,
                    length_penalty=self.config.LENGTH_PENALTY,
                    repetition_penalty=self.config.REPETITION_PENALTY,
                    top_k=self.config.TOP_K,
                    top_p=self.config.TOP_P,
                    enable_text_splitting=True,
                    speed=1.0  # Natural speed
                )

                # Save audio
                torchaudio.save(
                    str(output_path),
                    torch.tensor(outputs["wav"]).unsqueeze(0),
                    sample_rate=self.config.SAMPLE_RATE
                )

            print(f"✅ Audio saved: {output_path.stat().st_size / 1024:.2f} KB")
            return output_path

        except Exception as e:
            print(f"❌ Synthesis failed: {e}")
            traceback.print_exc()
            return None

    def test_character(self, character: str) -> Optional[Path]:
        """Run standardized test phrases for character"""

        test_phrases_file = self.config.BASE_DIR / "output" / "test_phrases.json"

        if not test_phrases_file.exists():
            print(f"❌ Test phrases not found: {test_phrases_file}")
            return None

        with open(test_phrases_file, 'r') as f:
            test_data = json.load(f)

        if character not in test_data:
            print(f"⚠️  No test phrases for {character}")
            return None

        phrases = test_data[character]
        print(f"\n{'='*50}")
        print(f"TESTING {character.upper()}")
        print(f"{'='*50}")

        results = []

        for i, phrase in enumerate(phrases, 1):
            print(f"\n[{i}/{len(phrases)}] Testing: \"{phrase}\"")
            output_path = self.synthesize(character, phrase)

            if output_path:
                results.append({
                    "phrase": phrase,
                    "audio_path": str(output_path),
                    "success": True
                })
            else:
                results.append({
                    "phrase": phrase,
                    "audio_path": None,
                    "success": False
                })

        # Save test report
        report_path = self.config.OUTPUT_DIR / f"test_report_{character}.json"
        with open(report_path, 'w') as f:
            json.dump({
                "character": character,
                "results": results,
                "timestamp": Path().stat().st_mtime
            }, f, indent=2)

        print(f"\n✅ Test complete. Report: {report_path}")
        return report_path

def batch_synthesize(character: str, texts: List[str]) -> List[Path]:
    """Generate multiple lines for a character"""
    synthesizer = VoiceSynthesizer()
    paths = []

    for i, text in enumerate(texts, 1):
        print(f"\n[{i}/{len(texts)}] Generating...")
        path = synthesizer.synthesize(character, text)
        if path:
            paths.append(path)

    return paths

def main():
    """CLI for synthesis"""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python synthesize.py <character> <text>")
        print("Or: python synthesize.py test <character>")
        sys.exit(1)

    synthesizer = VoiceSynthesizer()

    if sys.argv[1] == "test":
        character = sys.argv[2]
        synthesizer.test_character(character)
    else:
        character = sys.argv[1]
        text = " ".join(sys.argv[2:])
        synthesizer.synthesize(character, text)

if __name__ == "__main__":
    main()
