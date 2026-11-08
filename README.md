# Phil and Jim Dandy Show Studio

Private local-first studio for document context, externally written scripts, ad production, audio and social exports.

The current authoring flow is **sources → context package → external LLM → script import → Preview → approval → audio**. See [context authoring](docs/CONTEXT_AUTHORING.md) and [vault safekeeping](docs/VAULT_INTEGRATION.md).

This is the active Dandy development workspace. The older `Desktop/Projects/Dandy`
copy is retained as reference only. See [the consolidation report](docs/CONSOLIDATION_REPORT.md)
for transferred features, exclusions, checkpoints, and remaining production verification.

## Stack
- **Frontend**: React 18 + Vite 8 + Tailwind CSS (`frontend/`), Node 24
- **Backend**: FastAPI + Uvicorn, Python 3.11 (`backend/app/`)
- **Short-copy writer**: Required Qwen2.5-7B-Instruct Q4_K_M for ads and posts; episode dialogue is written externally
- **Audio**: System FFmpeg/FFprobe and separate CUDA Qwen speech service
- **TTS voices**: Qwen3-TTS-12Hz-1.7B-CustomVoice; Phil = Ryan, Jim = Eric
- **Fallback**: Required Qwen failures stop production; no voice substitution
- **Storage**: JSON flat-files under `episodes/{id}/` (config, script, status, ads, assets)

## App surface
- **Episodes**: sources → context → import → Preview → approve → produce → export · rollback versions · feedback · asset uploads · media cues · **EDIT CONFIG** (saves title/topic/description/key points/intensity to config.json)
- **Ads**: preset catalog + per-episode ad generation + ad audio fetch · insert-line positions persist across sessions
- **Social**: presets + package generation + slideshow/adcard builders + export listing/download
- **Studio**: Voicemeeter + OBS control panel wiring
- **System**: health checks, voice inventory, runtime status · **Intro/Outro settings** (enable toggle, music file, timing, voice, preview)

## SKG system
- `phil_dandy_skg.py` / `Jim_dandy_skg.py` — template-based character banter generators
- `backend/app/services/production/communication_layer.py` — orchestrates SKG calls with full 45-key context mapping, word-count-driven expansion (target 5 000 words, max 7 200)
- `backend/app/services/production/rhythm.py` — adaptive rhythm estimator with observed/commanded split, cooldown hysteresis, and bounded one-step pacing shifts
- Quality guards reject unresolved placeholders and invalid writer output.

## Installation boundaries

Create an isolated Python 3.11 studio environment and install
`requirements/characters.txt`. The API-only lock is `requirements.txt`; development
tools are in `requirements/dev.txt`. Qwen runs in a separate CUDA environment.
See [environment setup](docs/ENVIRONMENT.md). Do not overwrite existing environments.

Copy `config/runtime.local.example.json` to `config/runtime.local.json` and set
verified Python executables, FFmpeg location and the existing writer endpoint.
This machine-specific configuration is ignored by Git. Model weights and external
voice references are separately provisioned assets.

## Run locally

> **Prerequisites**: FFmpeg/FFprobe on PATH, verified writer and cached Qwen 1.7B model.

1. **Recommended one-command startup / reboot-safe restart**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart
```

2. **Backend** on `:8110`
```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8110
```
3. **Frontend** on `:5173` (proxies `/api` and `/ws` to `:8110`)
```bash
cd frontend
npm ci
npm run dev
```

For the built frontend, run `npm run build` from `frontend/`, then start with
`scripts/start_dandy_stack.ps1 -Production` and open `http://127.0.0.1:8110/studio`.
This serves the build through FastAPI without Vite. Automatic boot supervision is
a separate operator deployment task. Stop dedicated Dandy services with
`powershell -File scripts/stop_dandy_stack.ps1`; the shared writer is preserved.

## Verification
```bash
# Backend health
curl http://127.0.0.1:8110/health
curl http://127.0.0.1:8110/api/voices

# Full smoke test (29 endpoints)
.venv\Scripts\python.exe scripts/smoke_test.py

# Isolated regression tests (can run alongside the studio)
.venv\Scripts\python.exe scripts/test.py

# Frontend build check
cd frontend && npm run build
```

## Key API endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/episodes` | List all episodes |
| POST | `/api/episodes/create` | Create episode and receive job ID |
| PATCH | `/api/episodes/{id}/config` | Save episode config |
| POST | `/api/episodes/generate-script?job_id=...` | Generate through required writer |
| POST | `/api/episodes/produce?job_id=...` | Queue required Qwen production |
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


## Production hardening status

See [the repair record](docs/PRODUCTION_HARDENING.md). Qwen is required by
`config/qwen_tts.json` (`production.required_engine`); unavailable Qwen fails
production instead of substituting Kokoro/Edge. Current cleanup decisions and
verification are in [the cleanup record](docs/CLEANUP_RECORD.md).

Run only one backend process: the application holds an OS advisory runtime lock.
At startup, unfinished production records become `interrupted`, requiring an
explicit production retry. GPU production is limited to one active episode.
`/api/ready` returns 503 if FFmpeg, FFprobe, Qwen or the script writer is unavailable.
This checks dependencies, not final voice identity or media quality.

Create a complete media backup while production is idle:
```powershell
.venv\Scripts\python.exe scripts/studio/backup.py --label before-production
.venv\Scripts\python.exe scripts/studio/backup.py --restore archive/backups/NAME.zip --destination C:/DandyRestoreCheck
```
The restore destination must be empty. Copy verified archives to separate storage;
a backup on this disk does not protect against disk failure. External voice prompts
outside this repository need a separate backup.

Episode records and generated media are local runtime data, ignored by Git. All
existing local records were preserved when tracking was removed; earlier committed
records remain in history. Root Python worker/helper imports are compatibility
wrappers; historical originals are preserved in `archive/legacy-python`.
