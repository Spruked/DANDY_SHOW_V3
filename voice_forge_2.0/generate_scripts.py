#!/usr/bin/env python3
"""
Batch generate audio for all character scripts
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from synthesize import VoiceSynthesizer

def generate_audio_for_character(character: str):
    """Generate audio for all scripts of a character"""
    scripts_dir = Path(__file__).parent / "scripts" / character
    output_dir = Path(__file__).parent / "output" / "generated"

    if not scripts_dir.exists():
        print(f"Scripts directory not found: {scripts_dir}")
        return

    synthesizer = VoiceSynthesizer()

    for script_file in scripts_dir.glob("script*.txt"):
        with open(script_file, 'r') as f:
            text = f.read().strip()

        print(f"Generating audio for {character} - {script_file.name}")

        # Create output filename
        output_name = f"{character}_{script_file.stem}.wav"
        output_path = output_dir / output_name

        result = synthesizer.synthesize(character, text, output_path)
        if result:
            print(f"✅ Generated: {result}")
        else:
            print(f"❌ Failed: {script_file}")

def main():
    characters = ["phil", "jim", "cali"]

    for character in characters:
        print(f"\n{'='*50}")
        print(f"GENERATING AUDIO FOR {character.upper()}")
        print(f"{'='*50}")
        generate_audio_for_character(character)

if __name__ == "__main__":
    main()