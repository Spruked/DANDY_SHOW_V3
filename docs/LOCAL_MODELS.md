# Dandy local models

Episode script generation and short-copy authoring use NVIDIA Nemotron through the NVIDIA Integrate OpenAI-compatible API. `config/writer.json` pins the Nemotron model and endpoint; `NVIDIA_API_KEY` remains process-local. The episode generator sends the saved context package and requires a structured alternating Phil/Jim response before saving a canonical draft.

The legacy Qwen2.5-7B llama.cpp writer settings remain in `config/writer.json` for compatibility with older diagnostics, but are no longer the active episode writer when the provider is set to `nvidia`.

Speech uses Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice, a separate audio model. Run `secondary_systems/Dandy_Qwen_TTS_Ui/start_custom_voice.cmd` to launch the cached model on port 8031 and Dandy bridge on port 8020. The launcher uses installed Python 3.11, bfloat16 CUDA, PyTorch attention, one concurrent synthesis request, and offline model loading. Existing listeners are preserved.

Phil uses Ryan; Jim uses Eric. The 0.6B model remains cached but is not selected. The older R: drive launchers for clone/design are legacy and are outside this CustomVoice setup.

The shared launch configurations are owned outside this repository:

- Writer: `C:\llama.cpp\Start-ORB-LLM.ps1`, `--n-gpu-layers 99`.
- Speech: `C:\AI-Services\Start-Shared-QwenTTS.ps1`, `--device cuda:0 --dtype bfloat16`.
- Model cache: `C:\Users\bryan\.cache\huggingface\hub`.

Dandy only connects to these services; cleanup does not alter their GPU settings,
model files or global configuration. Normal Dandy shutdown preserves both shared
models. Configure the bridge Python/shared launcher in ignored runtime.local.json.
No alternate writer, smaller speech model or voice-engine fallback is permitted.
