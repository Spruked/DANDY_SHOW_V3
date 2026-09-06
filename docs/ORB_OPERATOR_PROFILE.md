# ORB Operator Profile: Dandy Studio

## Current local authority

- Workspace: `C:\dev\Desktop\The Real Dandy\Dandy`
- Frontend: `http://127.0.0.1:5188`
- Backend: `http://127.0.0.1:8110`
- Startup: `powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart`

## Production path

1. Create and edit the Phil and Jim episode in `EPISODES`.
2. Generate the script through Windows llama.cpp at `http://127.0.0.1:8009/v1`.
3. Produce with selected local Qwen 3 TTS: Dandy bridge `8020` uses CUDA CustomVoice `8031`.
4. Build and export platform assets in `SOCIAL`.

The Qwen operator UI remains available at `http://127.0.0.1:7861` for direct voice work. Voice Forge source is first-party at `voice_forge_2.0/`; selection stays disabled until local Coqui XTTS and real minted embeddings are installed.

## Studio scope

- `STUDIO` provides OBS status, scene switching, streaming, and recording controls.
- Dandy renders audio files directly. There is no mixer backend or mixer control surface.
- `SYSTEM` reports the current writer, selected TTS engine, Qwen bridge health, and Voice Forge readiness.

## Core endpoints

- `GET /api/health`
- `GET` and `POST /api/tts-engine`
- `GET /api/episodes`
- `POST /api/episodes/create`
- `POST /api/episodes/generate-script?job_id={id}`
- `POST /api/episodes/produce?job_id={id}`
- `GET /api/obs/status`
- `GET /api/obs/scenes`
- `POST /api/obs/scene`
- `POST /api/obs/stream/toggle`
- `POST /api/obs/record/toggle`

## Verification

```powershell
curl.exe http://127.0.0.1:8110/health
curl.exe http://127.0.0.1:8020/health
curl.exe http://127.0.0.1:7861/
.venv\Scripts\python.exe scripts\audit_endpoints.py
cd frontend; npm.cmd run build
```
