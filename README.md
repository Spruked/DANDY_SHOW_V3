# Phil and Jim Dandy Show Studio

Private local-first studio for episode scripting, ad insertion, production, and social package export.

> Current runtime (2026-09-06): frontend `5188`; backend `8110`; local llama.cpp writer `8009/v1`; Windows Qwen 3 TTS bridge `8020` to CustomVoice `8031`; Qwen operator UI `7861`. Production uses only the selected local engine, with no cloud fallback. Voice Forge is integrated but remains unavailable until local Coqui XTTS and real minted embeddings are present.

## Stack
- **Frontend**: React 18 + Vite 8.0 + Tailwind CSS (`frontend/`) — Node v24.14.0
- **Backend**: FastAPI + Uvicorn, Python 3.12 (`backend/app/`)
- **Audio**: Windows FFmpeg + selected local engine: Windows CUDA Qwen 3 TTS (current), Kokoro WSL sidecar, or guarded local Voice Forge XTTS
- **TTS voices**: Phil → `am_michael` · Jim → `am_liam` · Announcer → `am_eric` (all Kokoro, always)
- **GPU**: RTX 3050, `torch 2.5.1+cu121`, WSL2 Ubuntu-24.04 at `/home/bryan/.venvs/gpu`
- **Storage**: JSON flat-files under `episodes/{id}/` (config, script, status, ads, assets)

## App surface
- **Episodes**: draft → generate (5 000-word min) → edit → produce → export · rollback versions · feedback · asset uploads · media cues · **EDIT CONFIG** (saves title/topic/description/key points/intensity to config.json)
- **Ads**: preset catalog + per-episode ad generation + ad audio fetch · insert-line positions persist across sessions
- **Social**: presets + package generation + slideshow/adcard builders + export listing/download
- **Studio**: OBS control panel; Dandy renders audio directly to local files
- **System**: health checks, voice inventory, runtime status · **Intro/Outro settings** (enable toggle, music file, timing, voice, preview)

## SKG system
- `phil_dandy_skg.py` / `Jim_dandy_skg.py` — template-based character banter generators
- `backend/app/services/production/communication_layer.py` — orchestrates SKG calls with full 45-key context mapping, word-count-driven expansion (target 5 000 words, max 7 200)
- `backend/app/services/production/rhythm.py` — adaptive rhythm estimator with observed/commanded split, cooldown hysteresis, and bounded one-step pacing shifts
- Quality guard: if >30% of generated lines contain `[unknown]`, falls back to seed script

## TTS architecture — WSL2 GPU sidecar
Windows cannot run Kokoro directly (torch/torchvision version mismatch). TTS synthesis is routed through WSL2:
```
Windows FastAPI backend
  └─ subprocess: wsl -- /home/bryan/.venvs/gpu/bin/python /home/bryan/wsl_tts_worker.py
       └─ Kokoro KPipeline (torch 2.5.1+cu121, RTX 3050 CUDA)
            └─ writes 24 kHz PCM WAV → shared /mnt/c/... path
  └─ FFmpeg (Windows): WAV → MP3
```
- WSL worker: `/home/bryan/wsl_tts_worker.py` (also at `backend/app/services/production/wsl_tts_worker.py`)
- A TTS failure is reported to the episode job; it does not invoke a cloud fallback or publish substitute audio
- First run per voice downloads the voice model (~500 KB) from HuggingFace

## Run locally

> **Prerequisites**: WSL2 running with Ubuntu-24.04 and `/home/bryan/.venvs/gpu` venv active; FFmpeg on Windows PATH.

1. **Recommended one-command startup / reboot-safe restart**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart
```

2. **Backend** on `:8110`
```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8110
```
3. **Frontend** on `:5188` (proxies `/api`, `/ws`, and `/renders` to `:8110`)
```bash
cd frontend
npm install
npm run dev
```

## Verification
```bash
# Backend health
curl http://127.0.0.1:8110/health
curl http://127.0.0.1:8110/api/voices

# Full smoke test (29 endpoints)
.venv\Scripts\python.exe scripts/smoke_test.py

# WSL TTS direct test
wsl -- /home/bryan/.venvs/gpu/bin/python /home/bryan/wsl_tts_worker.py \
  --text "Phil here, Kokoro on CUDA." --voice am_michael --speed 1.0 \
  --output /tmp/test_tts.wav

# Frontend build check
cd frontend && npm run build
```

## Key API endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/episodes` | List all episodes |
| POST | `/api/episodes/create` | Create episode and generation job |
| PATCH | `/api/episodes/{id}/config` | Save episode config |
| POST | `/api/episodes/generate-script?job_id={id}` | Generate a script through the local writer |
| POST | `/api/episodes/produce?job_id={id}` | Queue production with the selected local TTS engine |
| GET | `/api/voices` | Voice inventory |
| GET | `/api/intro-outro-config` | Intro/Outro settings |
| POST | `/api/intro-outro-config` | Save Intro/Outro settings |
| GET | `/health` | Backend health |

## Documentation
- Architecture/layout: `docs/PROJECT_STRUCTURE.md`
- Wiring decision: `docs/DASHBOARD_DECISION.md`
- Endpoint audit: `docs/ENDPOINT_WIRING_AUDIT.md`
- Brand system: `docs/BRAND_SYSTEM.md`
- Operations notes: `docs/operations/NEXT_INSTANCE_NOTES.md`
- User guide: `docs/USER_GUIDE_AND_OPERATOR_MANUAL.md`
- Archived testing: `archive/testing/`
