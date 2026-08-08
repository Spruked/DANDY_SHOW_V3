# ORB Operator Profile: Dandy Studio + OBS

## Purpose
This profile gives the desktop ORB a local-first operator map for Dandy Studio and OBS.

## Workspace root
- `C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show`

## Primary runtime targets
- Frontend UI: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8010`
- Backend health: `http://127.0.0.1:8010/health`
- OBS executable: `C:\Program Files\obs-studio\bin\64bit\obs64.exe`
- OBS WebSocket default: `ws://127.0.0.1:4455`

## Start commands
### Backend
```powershell
cd C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show\backend
$env:PATH="C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show\staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin;$env:PATH"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

### Frontend
```powershell
cd C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

### OBS
```powershell
& "C:\Program Files\obs-studio\bin\64bit\obs64.exe"
```

## Source-of-truth files
- App root: `frontend/src/App.jsx`
- Episodes UI: `frontend/src/components/EpisodeTab.jsx`
- Ads UI: `frontend/src/components/AdTab.jsx`
- Social router: `frontend/src/components/SocialTab.jsx`
- Social exports: `frontend/src/components/ExportsMode.jsx`
- Slideshow builder: `frontend/src/components/SlideshowBuilder.jsx`
- Ad cards builder: `frontend/src/components/AdCardsBuilder.jsx`
- Studio control surface: `frontend/src/components/StudioTab.jsx`
- System diagnostics: `frontend/src/components/SystemTab.jsx`
- Frontend API client: `frontend/src/lib/api.js`
- Backend production routes: `backend/app/api/production.py`
- Backend OBS routes: `backend/app/api/obs.py`
- Backend mixer routes: `backend/app/api/mixer.py`

## Frontend page map
### Top-level tabs
- `EPISODES`
- `ADS`
- `SOCIAL`
- `STUDIO`
- `SYSTEM`

### Episodes abilities
- create episode draft
- generate script
- produce episode audio
- export script as `json`, `txt`, `srt`
- edit script lines
- reorder, insert, delete lines
- attach episode assets
- add media cues
- submit feedback
- connect episode websocket log

### Ads abilities
- generate ad copy per episode
- produce ad audio
- insert ads into episode script
- upload ad assets
- open ad assets and produced ad audio

### Social abilities
- queue social exports
- build slideshow decks
- build sponsor and CTA ad cards
- render slideshow and ad-card outputs

### Studio abilities
- read and patch mixer state through backend routes
- read and toggle OBS stream and recording state
- switch OBS scenes
- monitor source meters
- operate macro buttons
- operate simulated camera controls

### System abilities
- inspect backend health
- inspect registered voice engines
- inspect proxy and runtime notes
- copy health commands

## Backend control surface
### Health and voices
- `GET /api/health`
- `GET /api/voices`

### Episodes and production
- `GET /api/episodes`
- `POST /api/episodes/create`
- `GET /api/episodes/{id}/script`
- `POST /api/episodes/generate-script`
- `POST /api/episodes/edit-script`
- `POST /api/episodes/produce`
- `GET /api/episodes/{id}/export`

### Assets and cues
- `GET /api/episodes/{id}/assets`
- `POST /api/episodes/{id}/assets`
- `POST /api/episodes/{id}/media-cues`

### Ads
- `GET /api/episodes/{id}/ads`
- `POST /api/episodes/{id}/ads`
- `POST /api/episodes/{id}/ads/{ad_id}/produce`
- `POST /api/episodes/{id}/ads/{ad_id}/insert`
- `GET /api/episodes/{id}/ads/{ad_id}/assets`
- `POST /api/episodes/{id}/ads/{ad_id}/assets`

### Social
- `GET /api/episodes/{id}/social`
- `POST /api/social/generate`
- `GET /api/social/slideshow/load`
- `POST /api/social/slideshow/save`
- `POST /api/social/slideshow/render`
- `POST /api/social/slideshow/auto-generate`
- `POST /api/social/slideshow/snap`
- `GET /api/social/adcards/load`
- `POST /api/social/adcards/save`
- `POST /api/social/adcards/render`

### OBS
- `GET /api/obs/status`
- `GET /api/obs/scenes`
- `POST /api/obs/scene`
- `POST /api/obs/stream/toggle`
- `POST /api/obs/record/toggle`

### Mixer
- `GET /api/mixer/status`
- `POST /api/mixer/channel`
- `POST /api/mixer/master`
- `POST /api/mixer/bus/{index}`
- `POST /api/mixer/macro/{index}`

## OBS operating notes
- Dandy Studio `STUDIO` tab depends on OBS WebSocket connectivity.
- The backend OBS routes are the ORB’s preferred control path.
- The ORB should treat OBS scenes, stream state, and record state as mutable local operator targets.
- Studio scene switching and macro behavior are mapped in `frontend/src/components/StudioTab.jsx`.

## Local authority model
- Dandy Studio is local-first.
- OBS is local desktop software.
- The ORB may operate both by filesystem, local process launch, local HTTP, local WebSocket, and UI automation as needed.
