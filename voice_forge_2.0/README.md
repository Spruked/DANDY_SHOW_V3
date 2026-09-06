
# Voice Forge 2.0 - Broadcast Grade Voice System

## Overview
Voice Forge 2.0 now uses Kokoro TTS for high-quality voice synthesis with predefined character voices. No custom voice training required.

## Quick Start (2 Steps)

### Step 1: Setup
Install dependencies:
```bash
pip install -r requirements.txt
```

### Step 2: Test & Use

**Test a character:**
```bash
python synthesize.py test phil
# Generates test phrases and saves to output/test_report_phil.json
```

**Synthesize text:**
```bash
python synthesize.py phil "Your text here"
```

## Characters

**Phil** - Dry, observational humor, deliberate pacing
**Jim** - High energy, enthusiastic, quick-witted
**Bryan** - Intense, earnest, authoritative

All characters use Kokoro's American English voices.

**Generate specific text:**
```bash
python synthesize.py phil "Your custom text here"
# Creates: output/generated/phil_[timestamp]_[text].wav
```

**Batch generate:**
```python
from synthesize import batch_synthesize

lines = [
	"First line of dialogue",
	"Second line of dialogue",
	"Third line with different emotion"
]

paths = batch_synthesize("phil", lines)
```

## Integration with Dandy Show

Copy embeddings to your show directory:
```bash
cp embeddings/*_voice.pt ../phil_and_jim_dandy_show/voices/
```

Then in your show script:
```python
from voice_forge_v2.synthesize import VoiceSynthesizer

synth = VoiceSynthesizer()
synth.synthesize("phil", script_line)
```

## Voice Quality Checklist

After minting, test with these phrases:

1. **Consistency Test:** Generate same line 3 times - should sound identical
2. **Emotion Test:** Generate serious line, then funny line - should maintain character
3. **Length Test:** Generate 15-second line - should not drift or degrade
4. **Breathing Test:** Long sentences should sound natural, not rushed

## Troubleshooting

**"Sounds robotic":**
- Source recording quality issue
- Sample too short (<30 seconds)
- Too much background noise

**"Inconsistent between generations":**
- Temperature too high (>0.7)
- GPT cond length wrong (should be 12)

**"Doesn't sound like character":**
- Source recording doesn't match profile
- Re-record following personality guidelines

## Version & Stability

- **Version:** 2.0.0
- **Deterministic:** Yes (same input = same output)
- **Stable embeddings:** Mint once, use forever
- **Model:** XTTS v2 (frozen)

Never upgrade XTTS version. These settings are frozen for broadcast consistency.

---

This source is maintained as part of the Dandy repository at `voice_forge_2.0/`.

License
-------
This project is released under the MIT License. See the `LICENSE` file for details.

.gitignore
--------
A `.gitignore` has been added to exclude large artifacts (models, embeddings, generated audio, and raw sample WAVs). Adjust as needed before pushing.
