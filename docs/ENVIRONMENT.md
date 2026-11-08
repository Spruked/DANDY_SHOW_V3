# Environment and dependency boundaries

Supported baseline: Windows x64, Python 3.11, Node 24, system FFmpeg/FFprobe.

| Requirement | Purpose | Validation |
| --- | --- | --- |
| studio.txt | API, media processing and contract tests | Fresh install and tests |
| characters.txt | Studio plus real Torch for character modules | Fresh install and tests |
| dev.txt | Studio plus Ruff and pip-tools | Fresh install, lint and tests |
| qwen.txt | Separate Qwen/Gradio service | Resolved lock; clean CUDA installation still needs validation |
| semantic.in | Optional real semantic embeddings | Not needed for the character fallback |
| hardware.in | Optional Voicemeeter | Requires Windows hardware setup |
| legacy-tts.in | Optional historical synthesis | Required Qwen blocks substitution |

Locks were resolved from declarations in an isolated environment, not frozen from
system Python. The studio/character/dev locks target Windows Python 3.11.
To regenerate, install pip-tools 7.6.2 in a separate tooling venv and run
`python -m piptools compile --strip-extras -o requirements/NAME.txt requirements/NAME.in`.
Regenerate studio first, then characters/dev, then qwen. Test every lock update.

Reuse a verified existing CUDA environment for Qwen when available. New Qwen
environments require compatible Torch and torchaudio GPU builds. The current
model setup uses version 2.11.0 with CUDA 12.8. Install these builds from the official
https://download.pytorch.org/whl/cu128 index before applying qwen.txt; its
`==2.11.0` accepts the matching `+cu128` build. A CPU wheel is not CUDA readiness.
Drivers, model weights and external voice references are not Python dependencies.

The shared service launcher loads the configured 1.7B model offline and never
substitutes the cached 0.6B model. Dandy connects to the shared writer at
`http://127.0.0.1:16520/v1` and shared speech model at `http://127.0.0.1:8031`
through its bridge. GPU settings remain owned by `C:\llama.cpp\Start-ORB-LLM.ps1`
and `C:\AI-Services\Start-Shared-QwenTTS.ps1`. Dandy does not modify them.
Optional semantic embeddings are never replaced by a fake module.

Clean CUDA installation, human voice approval, full episode production, automatic
service supervision and scheduled off-disk backups require separate acceptance.
