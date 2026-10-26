# Dandy local models

Text generation and rewrites use Qwen2.5-7B-Instruct Q4_K_M through llama.cpp at http://127.0.0.1:16520/v1. `config/writer.json` pins the required GGUF filename. The writer checks the loaded model before each request and blocks other models. SKG supplies persona guidance. There is no alternate model provider fallback.

Speech uses Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice, a separate audio model. Run `secondary_systems/Dandy_Qwen_TTS_Ui/start_custom_voice.cmd` to launch the cached model on port 8031 and Dandy bridge on port 8020. The launcher uses installed Python 3.11, bfloat16 CUDA, PyTorch attention, one concurrent synthesis request, and offline model loading. Existing listeners are preserved.

Phil uses Ryan; Jim uses Eric. The 0.6B model remains cached but is not selected. The older R: drive launchers for clone/design are legacy and are outside this CustomVoice setup.
