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
- **Episodes**: canonical script generation, episode configuration, generation status, exports, and audio playback
- **Preview**: version selection and full script review with line flags, line/section comments, and overall notes carried forward by canonical hash
- **Production Editor**: separate human workspace with immutable canonical source, Preview handoff, editable production copy, MORB review, provenance hashes, and explicit approval before production
- **Ads**: preset catalog + per-episode ad generation + ad audio fetch · insert-line positions persist across sessions
- **Social**: presets + package generation + slideshow/adcard builders + export listing/download
- **Studio**: OBS controls, connected browser camera preview, Qwen studio controls, and live status
- **System**: health checks, voice inventory, runtime status · **Intro/Outro settings** (enable toggle, music file, timing, voice, preview)

## SKG system
- `phil_dandy_skg.py` / `Jim_dandy_skg.py` — separate character state and validation
- `backend/app/services/production/segment_worker.py` — five-minute sections plus the exact remainder, deterministic beats, EpisodeGovernor directives and stage telemetry
- `backend/app/services/production/rhythm.py` — adaptive rhythm estimator with observed/commanded split, cooldown hysteresis, and bounded one-step pacing shifts
- Active segmented generation uses 90 spoken WPM (450 words per five-minute section), preserves short generated dialogue, and flags uncertain repetition for editing. Production reads the saved script; it does not regenerate it.

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

## Episode production checkpoints

The episode path is split into four explicit stages: **Generate → Preview → Production Editor → Produce**.

- Generate writes a versioned canonical snapshot at `episodes/{id}/canonical_scripts/canonical_vNNNN.json`. The active `script.json` remains a compatibility projection; saved canonical snapshots are write-once and hash-verified. A later generation creates another version without rewriting the older snapshot.
- The top-level **Preview** tab opens a selected canonical snapshot read-only and records review marks, line comments, section notes, and overall notes. The handoff is hash-bound to that exact canonical version.
- The top-level **Production Editor** tab receives the Preview handoff as a separate draft. It keeps the canonical text read-only and owns production-copy edits, pronunciation/spoken forms, pauses, delivery notes, production cues, and MORB review.
- Approving a draft writes an immutable `approved_vNNNN.json` snapshot with the canonical source hash, production-copy hash, settings fingerprint, and approval timestamp. An edit to the draft or a relevant settings/asset change makes approval stale.
- Produce requires the current approved version ID and synthesizes that saved plan. It does not run implicit editor preparation or substitute an unapproved script. The active Qwen voice bridge remains the configured production engine.
- Editor state is stored under `episodes/{id}/production_editor/`; canonical and approved snapshots are retained for provenance.

## Saved test episode: resume production (2026-10-06)

`ep_1791247143016` has 24 saved Phil/Jim lines and 612 words. Its first real production completed on 2026-10-06: `status.json` is `produced`, and `audio.mp3` is a 253.73-second stereo MP3. The original master is also preserved as `audio.baseline_001.mp3` for comparison with later editor runs. Open it in **Episodes** at `http://127.0.0.1:5173` and use the **Audio** player or **DOWNLOAD MP3**.

- The bridge validates the existing configured WAVs (`asset_library/voice/phildandyclone.wav`, `jimdandyclone.wav`), uploads Gradio FileData and calls the running VoiceClone/Base service on `8032`. No new saved profiles or replacement voice assets are created by this repair. This reference-audio route does not require a `.pt` profile.
- Media tools resolve from this checkout, then the existing sibling `Dandy/staging/ffmpeg/ffmpeg-master-latest-win64-gpl/bin`, then PATH. Explicit `DANDY_FFMPEG` / `DANDY_FFPROBE` overrides must point to real executables. Bridge health now exposes their resolved paths and availability.
- Startup defaults to Qwen **clone** mode. A request with a clone identity cannot silently select CustomVoice if another model is available. Keep the existing one-model-at-a-time switching workflow.
- Intro/outro are explicitly theme-only: `config/config.json` sets `intro_outro.narration_enabled=false`. Each full production opens and ends with the existing 18-second `asset_library/sfx/introclip.mp3`. Announcer text remains stored but is not synthesized. Re-enabling narration requires the configured narrator runtime; it currently calls Kokoro WSL.
- Successful final output is `episodes/ep_1791247143016/audio.mp3`, with `transcript.json`, `production_metadata.json`, `production_result.json` and `status.json`. Only `status=produced` plus a playable final file establishes completion. The five-minute target is an estimate, not a final audio-duration guarantee.

Watch `secondary_systems/Dandy_Qwen_TTS_Ui/logs/qwen-bridge-8020.out.log` for reference probing and synthesis phases, `.err.log` for full tracebacks, and `logs/backend.out.log` / `backend.err.log` for assembly errors. Previous logs were preserved as `*.before_repair_*`. Job/episode status is available through `/api/episodes/jobs/{job_id}` and the episode's `status.json`.

The earlier bridge repair was validated with compilation, PowerShell parsing, isolated contracts and ffprobe checks; it did not run production at that time. The operator subsequently completed the saved 24-line production. Listening acceptance of both voices, every line and theme endings remains an operator review step.

Known concerns remain: eleven saved lines lack terminal sentence punctuation; the writer grammar/parser caps turns at 180 characters; its `persona_brief[:600]` can discard appended beat/governor instructions; configured ambient SFX slugs are absent from `audio/sfx`; clone provenance labels still contain built-in speaker names; social exports run after audio publication. These are documented in the dev log, and do not justify regenerating this saved test script.

## Production Editor and line takes

The top-level **Production Editor** page is the explicit human checkpoint between canonical script generation and Qwen TTS. Canonical snapshots are immutable and read-only in the editor. The production copy contains editable dialogue, pronunciation/spoken form, pause, delivery notes and line cues. MORB output is a proposal requiring operator review; approve is blocked until proposals are reviewed and the draft is saved. An editor or approval error blocks production; there is no implicit transformation or pass-through.

Editor state is stored under `episodes/{id}/production_editor/` as drafts and write-once approved snapshots. Approval records the canonical source and production-copy hashes, settings fingerprint, cue-asset hashes and timestamp. Production accepts only the current approved version ID. It synthesizes that saved plan, saves individual Qwen takes under `takes/`, then writes `production_manifest.json`, `assembly_graph.v1.json`, and `qc_report.v1.json`. QC identifies missing/hash-mismatched audio, implausibly short duration, or unfinished approved source lines; it does not yet assess pronunciation or acting quality. Line regeneration uses persistent production-line IDs and is allowed only while the rendered master matches the current approval. Previous takes and masters are retained.

The completed baseline episode predates saved line takes, so it has no regeneration control until it is produced again. Automatic campaign adaptation, generative embellishment, ASR-based QC, multi-format fan-out, and asset replacement remain outside this initial editor implementation. The assembly graph currently addresses dialogue and pauses; theme and configured SFX are recorded as global treatments.

The Audio player serves the MP3 inline with byte-range requests; **DOWNLOAD MP3** requests an attachment. If the player still shows `0:00`, refresh the Episodes page and inspect `/api/audio/{episode_id}/final.mp3` plus the browser media error. A completed file on disk alone does not prove browser playback.

## Social assets

The Social > Exports asset status checks six exact PNG filenames in `social/templates/` and then `social/assets/`: `thumbnail_base.png`, `waveform_base.png`, `alternate_cover.png`, `character_logo.png`, `segment_tech_talk.png`, and `logo.png`. Copy the selected images into either folder using those filenames, then reload Social to refresh availability. There is currently no in-app uploader. Thumbnail and audiogram presets preselect their matching base image when it is available; `logo.png` is used by the Slideshow and Ad Cards builders.

Social export history previews image, video, and audio files inline; the separate download action remains available for each export.

## Run locally

> **Prerequisites**: Local Qwen services running, FFmpeg available on Windows, and the frontend/backend dependencies installed.

1. **Recommended one-command startup / reboot-safe restart**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart -QwenMode clone
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
| GET | `/api/episodes/{id}/production-editor` | Review editor decisions and QC artifacts |
| GET | `/api/episodes/{id}/canonical-scripts/{version_id}/preview` | Read Preview notes/flags for a canonical version |
| GET/PUT | `/api/episodes/{id}/preview` | Read selected Preview handoff / save a hash-bound review |
| GET | `/api/episodes/{id}/production-manifest` | Read saved line/take identities |
| POST | `/api/episodes/{id}/production/segments/line_001/regenerate` | Regenerate one saved Qwen line and rebuild master |
| GET | `/api/episodes/{id}/production-revision` | Poll a line revision |
| GET | `/api/audio/{id}/final.mp3` | Stream final audio inline; add `?download=1` for attachment |
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
