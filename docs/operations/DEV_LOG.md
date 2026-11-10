# Dandy Studio Dev Log

## 2026-08-08 - Repo Context Scan

Scope: `S:\The Real Dandy\All things Dandy\Dandy`

- Created this dev log because no maintained dev log Markdown file was present in the checkout.
- Existing log files under `logs/` are runtime stdout/stderr/pid artifacts, not a task handoff or development log.
- Current folder is not a Git repository.
- Main project README: `README.md`.
- Docs index: `docs/README.md`.
- Most useful local handoff/runbook: `docs/operations/NEXT_INSTANCE_NOTES.md`.
- Orb handoff exists at `docs/ORB_HANDOFF_CONTEXT_2026-04-05.md`, but it targets external repo `R:\Orb_Assistant_Desktop`, not this Dandy app.
- Backend entrypoint: `backend/app/main.py`.
- Frontend API client: `frontend/src/lib/api.js`.
- Backend target port from docs: `8010`.
- Frontend target port from docs: `5173`.
- LLM writer bridge in source: `backend/app/services/production/llm_writer.py` targeting `http://127.0.0.1:5199/query` with role `dandy_scriptwriter`.

Next use: append concise task notes, files touched, verification run, and any blockers after each work item.

## 2026-08-08 - Folder Condition Audit

Overall condition: usable but fragile local studio checkout.

- Complete app structure is present: FastAPI backend, React/Vite frontend, config, episode storage, social export folders, audio assets, docs, scripts, and runtime logs.
- Folder is not a Git repository, so there is no local commit history, branch state, or clean/dirty tracking here.
- Python environment is incomplete from this shell: `.venv` contains `Lib` only, no `.venv/Scripts/python.exe`; `python` points to an inaccessible Windows Store stub; `py` reports no installed Python.
- Frontend toolchain is present: Node resolves to `C:\Program Files\nodejs\node.exe`, `node --version` returns `v24.15.0`, and `npm.cmd --version` returns `11.12.1`.
- Use `npm.cmd`, not `npm`, in PowerShell here because `npm.ps1` is blocked by execution policy.
- Runtime logs show previous backend startup and frontend Vite startup succeeded.
- Backend logs also show production script generation previously hit quality-gate failures, repeated seed lines, and emergency minimal fallback.
- Backend logs show `/api/health`, `/api/writer-status`, and `/api/mixer/status` returning `200 OK`; OBS endpoints returned `503 Service Unavailable`.
- Frontend logs show Vite 8.0.3 ready on `http://127.0.0.1:5173/` with only deprecation/performance warnings.
- Endpoint audit script exists but could not be run because no usable Python interpreter is available from this shell.
- Empty or scaffold-like folders remain: `phil_dandy_skg_v3`, `jim_dandy_skg_v3`, `backend/app/models`, `backend/app/services/audio`, several episode `_meta`/`ads` folders, `frontend/public`, and `staging/Dandy`.
- Root-level production files and backend production files are not identical by hash, so edits must target the active backend/root pair deliberately instead of assuming they are duplicates.
- Large Audacity project files sit at repo root, including `sovereign_software_special_001_final.aup3` at about 677 MB.
- A stale-looking root PID file exists: `spruked-start-3001.pid`.

Recommended next stabilization order: restore/point Python runtime, run endpoint audit and backend smoke test, verify live backend/frontend ports, then address script-generation fallback quality before broad UI work.

## 2026-08-08 - Root SKG File Inspection

Files inspected:

- `Jim_dandy_skg.py`
- `phil_dandy_skg.py`

Findings:

- These are active production character files, not archive-only files. `config/voices.json` points Phil to `./phil_dandy_skg.py` and Jim to `./Jim_dandy_skg.py`.
- Backend loader path is `backend/app/services/production/personality_loader.py`; it dynamically loads the configured root files and instantiates `PhilDandySKG` / `JimDandySKG`.
- Backend worker initializes both personalities in `backend/app/services/production/worker.py` and passes them into `DandyCommunicationLayer`.
- Both files are large canonical SKG engines: Jim about 55 KB, Phil about 58 KB, last modified 2026-05-01.
- Both constructors create/use `phil_dandy_skg_v3` and `jim_dandy_skg_v3`, but those folders are currently empty.
- No `learned_patterns_v3.jsonl` files were present in those v3 folders, so learned-pattern behavior is effectively cold-start unless created at runtime later.
- Both SKGs include `phil_jim_personal_story` template-domain handling and safe template formatting that falls missing slots back to topic/current_topic instead of emitting `[unknown]`.
- The personal-story candidate pool is intentionally narrow. For long-form 5000-word output, repeated-template risk remains if generation relies mostly on SKG instead of the LLM bridge.
- Earlier backend logs showing repeated lines came from the seed fallback path after quality rejection, not direct proof that these SKG files alone are corrupt.
- Live import/runtime verification was not possible in this shell because Python is not currently usable.

## 2026-11-10 - Canonical Persona, Context, Vault, and GitHub Handoff

This work completed the persona/SKG integration needed for Episode 001 and documented the surrounding production decisions from the handoff.

### Completed

- Installed the supplied canonical persona files as the source of truth:
  - `config/characters/phil.persona.json`
  - `config/characters/jim.persona.json`
- Replaced the active root SKGs with the supplied versions:
  - `phil_dandy_skg.py`
  - `Jim_dandy_skg.py`
- Added the shared persona loader/canon validation in `persona_canon.py`.
- Updated the episode context pack so the writer receives the complete persona data, including shared family history and continuity facts, while preserving exactly two Show Bible character entries: Phil and Jim.
- Preserved the shared-family fingerprint check so the two persona files cannot silently diverge.
- Added `backend/tests/test_persona_canon.py`, including the learning-cache default/override and manifest coverage.
- Archived the supplied character source documents and previous SKG files in `Dandy_Vault_System/memory_archives/persona_sources/20261110/` before replacement.
- Preserved the production voice requirement: Jim uses `jimsample18.wav` and Phil uses `PHIL17SAMPLE.wav` through the configured voice system.
- Captured the production architecture decisions for Voice Studio/Qwen fallback, seven independent replaceable advertising slots, ad-slot reservation versus assigned advertisements, and continuity records for approved episodes. The ad-slot handoff remains documented for follow-up rather than being changed during this persona deployment.
- Retained the existing Nemotron script-generation/context workflow and its validation requirements; no external Nemotron request was made during validation.

### Verification

- Persona suite: `python -m unittest backend.tests.test_persona_canon -v`
  - Result: all 7 tests passed.
- Full suite: `python scripts/test.py`
  - Result: 82 tests ran; 7 known environment/dependency errors and 2 known Nemotron 502/410 failures remain.
  - No persona/SKG failures remained.
- Git working tree was committed and pushed to GitHub `origin/main`.
- Commit: `423bedb Install validated canonical persona SKGs`
- Local `main` and `origin/main` are synchronized.

### Known remaining items

- The seven unrelated baseline errors involve the existing `memory_core` vault tests plus `pypdf` and `_verified_model` environment/dependency coverage.
- The two expected failures exercise Nemotron 502/410 behavior.
- The supplied source package and reference DOCX/PDF files remain retained locally as uncommitted safety/reference material; they were not included in the production commit.

### Handoff summary

Dandy now has a durable, test-covered persona boundary: canonical JSON is authoritative, both SKGs load it, the context writer sees the brothers' shared history without inventing a third character, and the change is safely pushed to GitHub. The result is a much stronger foundation for consistent Phil-and-Jim identity across episodes, while keeping voice production, ad replacement, and continuity concerns separable for future work.

## 2026-11-10 - Three Commercial VoiceStudio Production Package

Scope: reusable commercial assets only. Episode 001, its context package, host script, host personas, host voice references, and the existing TrueMark Mint advertisement were not modified.

- Inspected the active advertising API, ad storage conventions, VoiceStudio wrapper, worker routing, voice configuration, and running VoiceStudio service.
- Confirmed the authoritative production path is the existing Dandy worker with `primary_engine: voicestudio`, VoiceStudio at `http://127.0.0.1:3900`, and the existing `announcer_male` VoiceStudio profile (`echo`). No direct Qwen request was used.
- Created a separate `commercial_library_20261110` record so the three reusable commercials remain independent from Episode 001.
- Produced three new commercials through the existing `POST /episodes/{episode_id}/ads` and `POST /episodes/{episode_id}/ads/{ad_id}/produce` workflow:
  - ORB Weaver — `ad_3f17e82f` — `episodes/commercial_library_20261110/ads/ad_3f17e82f.mp3`
  - Shiloh Ridge Katahdins — `ad_8488b34b` — `episodes/commercial_library_20261110/ads/ad_8488b34b.mp3`
  - Pro Prime Series AI LLC — `ad_dece1b21` — `episodes/commercial_library_20261110/ads/ad_dece1b21.mp3`
- Each asset is registered with its own script, sponsor, product, offer, CTA, announcer identity, VoiceStudio resolution, production timestamp, duration, and audio fingerprint. All three resolved to VoiceStudio with no fallback.
- Added the three advertiser keys to `backend/app/services/ads/ad_engine.py` so they are independently selectable in the existing catalog. The seven-slot architecture was not changed.
- Restarted the backend so the live catalog loaded the new keys.

### Audio verification

- ORB Weaver: 29.999750 seconds, 601,484 bytes, SHA-256 `4752DD68C917D04B8C1778EF4A5C6CB15120F21E3B9A304E15C65582A11A7...`.
- Shiloh Ridge Katahdins: 30.001958 seconds, 601,964 bytes, SHA-256 `69C4EF6EFF554FEF4476F2D4BBF0CC5BAFE13578461E92C61C4E0AB206B14...`.
- Pro Prime Series AI LLC: 30.001958 seconds, 601,964 bytes, SHA-256 `EF4A98D8A8D4396B58F0042AB3013A67744D634F947506489C04432DF9CC1...`.
- `ffprobe` confirmed all files have valid nonzero MP3 duration and size.
- Episode 001 remained `script_ready`, with 3 existing ad-only lines, 1 existing TrueMark Mint ad, and the original TrueMark audio fingerprint.

### Boundaries

- TrueMark Mint was preserved unchanged.
- Phil and Jim voice settings and samples were untouched.
- Episode 001 was not generated, modified, or assembled with the new commercials.
- The new commercials were not inserted into any episode.
- Owner approval remains distinct from production status; the three assets are produced/draft assets until explicitly approved.
