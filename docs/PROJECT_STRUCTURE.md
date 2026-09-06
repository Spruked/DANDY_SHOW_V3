# Project Structure

Current production-oriented local layout.

> Current authority (2026-09-06): repository root is `Dandy/`. The legacy mixer service is removed; `backend/app/services/tts/` includes the guarded Voice Forge adapter and `voice_forge_2.0/` is first-party source.

## Current root baseline
- `phil_dandy_skg.py`
- `Jim_dandy_skg.py`

These are the active SKG modules loaded by backend personality wiring.

## Active structure

```text
Dandy/
├── phil_dandy_skg.py
├── Jim_dandy_skg.py
├── archive/
│   ├── testing/              # Archived test/probe outputs and logs
│   └── cleanup/              # Archived empty/obsolete local folders/files
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── models/
│       ├── schemas/
│       ├── services/
│       │   ├── mixer/
│       │   ├── obs/
│       │   ├── production/
│       │   ├── social/
│       │   ├── storage/
│       │   └── tts/
│       └── websockets/
├── config/
├── docs/
│   └── operations/
├── assets/
│   ├── fonts/
│   └── images/
├── audio/
│   ├── ads/
│   ├── jingles/
│   └── sfx/
├── episodes/
├── frontend/                  # React/Vite app (current UI)
│   ├── public/
│   └── src/
│       ├── components/
│       ├── hooks/
│       ├── lib/
│       └── styles/
├── logs/
├── scripts/
├── social/
│   ├── assets/
│   ├── branding/
│   ├── generated/
│   ├── renders/
│   └── templates/
└── staging/
```

## Intent by area
- `backend/`: FastAPI application and services
- `frontend/`: React/Vite studio dashboard
- `episodes/`: active episode artifacts and metadata
- `assets/`: shared fonts and miscellaneous project assets
- `audio/`: ad beds, jingles, and sound effects
- `config/`: project, voice, and social configuration
- `docs/`: maintained technical and operational documentation
- `social/templates/`: fixed social asset slots used by builders and social generation
- `social/assets/`: extra reusable images for cards, promos, and one-off social work
- `archive/testing/`: archived test/probe runs and test logs
- `archive/cleanup/`: archived empty/obsolete local directories/files
