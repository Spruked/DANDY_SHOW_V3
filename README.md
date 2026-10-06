# Phil and Jim Dandy Show Studio

Private local-first studio for episode scripting, Qwen voice production, ad insertion, and social package export.

## Stack
- **Frontend**: React 18 + Vite 8.0 + Tailwind CSS (`frontend/`) — Node v24.14.0
- **Backend**: FastAPI + Uvicorn, Python 3.12 (`backend/app/`)
- **Audio**: FFmpeg (Windows) + local Qwen TTS bridge; production fails clearly when the selected Qwen identity is unavailable
- **TTS voices**: Phil and Jim use configured Qwen identities/prompts; no silent browser, Edge, or Kokoro fallback
- **GPU**: RTX 3050, `torch 2.5.1+cu121`, WSL2 Ubuntu-24.04 at `/home/bryan/.venvs/gpu`
- **Storage**: JSON flat-files under `episodes/{id}/` (config, script, status, ads, assets)

## App surface
- **Episodes**: draft ? local DeepSeek script generation ? edit ? Qwen production ? export ? live generation/production progress
- **Ads**: preset catalog + per-episode ad generation + ad audio fetch · insert-line positions persist across sessions
- **Social**: presets + package generation + slideshow/adcard builders + export listing/download
- **Studio**: OBS controls, connected browser camera preview, Qwen studio controls, and live status
- **System**: health checks, voice inventory, runtime status · **Intro/Outro settings** (enable toggle, music file, timing, voice, preview)

## SKG system
- `phil_dandy_skg.py` / `Jim_dandy_skg.py` — template-based character banter generators
- `backend/app/services/production/communication_layer.py` ? orchestrates bounded local LLM stages with retry and exchange-count telemetry
- `backend/app/services/production/rhythm.py` — adaptive rhythm estimator with observed/commanded split, cooldown hysteresis, and bounded one-step pacing shifts
- Quality guard: if >30% of generated lines contain `[unknown]`, falls back to seed script

## TTS architecture - local Qwen bridge
Production TTS is routed through the local Qwen bridge:
```
Windows FastAPI backend
  -> Qwen bridge :8020
       -> selected local Qwen voice backend
            -> writes dialogue audio to the episode workspace
  -> FFmpeg (Windows): dialogue + ads/SFX/music -> final MP3
```
- Qwen bridge: `http://127.0.0.1:8020`
- DeepSeek/llama.cpp writer: `http://127.0.0.1:40343/v1`
- Dandy backend: `http://127.0.0.1:8110`
- Frontend: `http://127.0.0.1:5173`
- No silent browser, Edge, or Kokoro fallback when Qwen is selected

## Run locally

> **Prerequisites**: Local Qwen services running, FFmpeg available on Windows, and the frontend/backend dependencies installed.

1. **Recommended one-command startup / reboot-safe restart**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart
```

2. **Backend** on `:8110`
```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8110
```
3. **Frontend** on `:5173` (proxies `/api` and `/ws` to `:8110`)
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

# Local writer status
  curl http://127.0.0.1:8110/api/writer-status

# Live job status
  curl http://127.0.0.1:8110/api/episodes/jobs/<job_id>

# Frontend build check
cd frontend && npm run build
```

## Key API endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/episodes` | List all episodes |
| POST | `/api/episodes` | Create episode |
| PATCH | `/api/episodes/{id}/config` | Save episode config |
| POST | `/api/episodes/generate-script?job_id=...` | Generate script through local DeepSeek/llama.cpp |
| GET | `/api/episodes/jobs/{job_id}` | Read live generation or production status |
| POST | `/api/episodes/produce?job_id=...` | Queue Qwen/FFmpeg episode production |
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
