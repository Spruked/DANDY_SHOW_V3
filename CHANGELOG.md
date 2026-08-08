# Dandy Studio — Changelog

## [Unreleased]

### Added
- `audio/jingles/intro_outro.mp3` — show intro/outro jingle (freemusiclab energetic pop)
- `config/config.json` — `audio.jingles` block with intro/outro/bumper/bed slot definitions
- `audio/jingles/`, `audio/sfx/`, `audio/ads/` — structured audio asset folders
- `backend/app/schemas/social_visual.py` — Pydantic models for Slide, AdCard, Slideshow
- `backend/app/services/social/slideshow_renderer.py` — Pillow + FFmpeg slide/ad card renderer
- `backend/app/api/social_slideshow.py` — slideshow CRUD + auto-generate + render endpoints
- `backend/app/api/social_adcards.py` — ad card CRUD + render endpoints
- `frontend/src/components/SocialTab.jsx` — upgraded: Exports / Slideshow / Ad Cards sub-tabs
- `frontend/src/components/ExportsMode.jsx` — existing export UI preserved as sub-mode
- `frontend/src/components/SlideshowBuilder.jsx` — 3-panel slide deck composer
- `frontend/src/components/AdCardsBuilder.jsx` — template-driven ad card builder
- `frontend/src/styles/social-tab.css` — Dandy-themed styles for social builders
- `social/renders/` — render output directory (git-ignored)
- `scripts/studio/backup.py` — incremental backup of configs + episode metadata
- `scripts/studio/restore_point.py` — git tag + snapshot for named restore points
- `scripts/studio/restore.py` — restore from a named restore point
- `scripts/studio/check_structure.py` — folder discipline validator
- `scripts/studio/deps.py` — dependency map generator
- `CHANGELOG.md` — this file
- `.git/hooks/pre-commit` — runs structure check before every commit
- `backend/app/services/production/rhythm.py` — adaptive rhythm estimator/state with cooldown + bounded deltas
- `scripts/start_dandy_stack.ps1` — restart-safe local startup script for backend/frontend stack

### Fixed
- `backend/app/api/ads.py` — duration validation now accepts 5–120s (was 15/20/30 only)
- `backend/app/main.py` — added port 5174 to CORS allowed origins (Vite fallback port)
- `backend/app/main.py` — added `/renders` StaticFiles mount for slide/ad card downloads
- `backend/app/services/production/worker.py` — fixed SKG init scope issue so `DandyCommunicationLayer` always imports in `_init_skg_systems`

### Changed
- `.gitignore` — added `social/renders/`, audio binary folders, backup/restore archives
- `backend/app/services/production/communication_layer.py` — rhythm-aware pacing/verbosity control and per-exchange rhythm metadata
- `backend/app/services/production/dandy_harmonizer.py` — rhythm-aware segment timing/verbosity adaptation
- `backend/app/services/production/worker.py` — rhythm metadata passed through script generation + pause timing derived from rhythm state

---

## [0.1.0] — 2026-04-04

### Added
- Initial studio: React/Vite frontend + FastAPI backend
- Episodes tab: script generation, TTS production, asset management, media cues
- Ads tab: ad script generation with voice/tone/type presets
- Social tab: audiogram, thumbnail, quote card, promo clip exports
- Studio tab: Voicemeeter mixer, OBS scene control, camera controls, macros
- System tab: health, diagnostics, voice list
- Dual TTS engine: Kokoro (local) + Edge TTS (cloud fallback)
- Audio post-processing: 2-pass FFmpeg normalize → compress → encode
- Brand asset system: gold city sign, countryside alternate, character logo, tech talk card
- WebSocket channel for live UI updates

---

## Format

```
### Added   — new features
### Changed — changes to existing functionality
### Fixed   — bug fixes
### Removed — removed features
### Security — security fixes
```
