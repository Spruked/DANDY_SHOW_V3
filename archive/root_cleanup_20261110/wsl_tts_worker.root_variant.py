"""
WSL TTS Worker -- called as a subprocess by the Windows backend.

Usage:
    /home/bryan/.venvs/gpu/bin/python wsl_tts_worker.py \
        --text "Hello world" \
        --voice am_michael \
        --speed 1.0 \
        --output /path/to/output.wav

Writes a WAV file at 24 kHz mono (Kokoro native output).
The Windows side converts to MP3 via FFmpeg.

Exit codes:
    0 -- success
    1 -- error (message on stderr)
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        import torch
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"

        pipeline = KPipeline(lang_code="a")

        generator = pipeline(
            args.text,
            voice=args.voice,
            speed=args.speed,
            split_pattern=r"\n+",
        )

        segments = [audio for _, _, audio in generator]
        if not segments:
            print("ERROR: Kokoro returned no audio segments", file=sys.stderr)
            sys.exit(1)

        full = np.concatenate([
            s.numpy() if hasattr(s, "numpy") else s
            for s in segments
        ])

        sf.write(args.output, full, 24000)
        print(f"OK device={device} samples={len(full)}", flush=True)
        sys.exit(0)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
