# Dandy Studio Dev Log

## 2026-10-05 - App recovery, audit and repair work paused for credit reset

Canonical checkout: `C:\dev\Desktop\The Real Dandy\Dandy-Studio-Qwen`. This entry supersedes historical runtime assumptions below; it does not replace their history.

Status: **IN PROGRESS, NOT ACCEPTED AS COMPLETE.** The operator requested a handoff and a pause with approximately 12% usage credits remaining. No commit or push was requested or performed. Implementation stopped after compile/build checks and this documentation update.

Authorized scope accumulated during this session:

- Start/recover the local app and use the running DeepSeek 7B llama.cpp writer.
- Review/refine ad creation, voice/duration/custom-copy preservation, deterministic insertion, and Social Post Maker output contracts.
- Replace decorative System status with real service/resource checks, source labels, timestamps and honest readiness states.
- Repair repetition in older generation paths; target 15-45-minute episodes using sections of at most 15 minutes, with saved ads between sections and easier intro/outro controls.
- Add a persisted Visual Ad Composer under ADS with text, visuals, animation, SFX and a timing strip. Keep live controls in STUDIO and standalone promotional cards under SOCIAL.

Startup recovery completed earlier in the session:

- Restored frontend `5173`, backend `8110`, writer `40343/v1`, Qwen bridge `8020`, CustomVoice `8031` and operator UI `7861`.
- Updated the existing launcher to use hidden, logged processes and the real sibling FFmpeg installation when this checkout lacks binaries.
- Verified a real DeepSeek completion and a real Qwen MP3 synthesis. The latter is `secondary_systems/Dandy_Qwen_TTS_Ui/generated_audio/20261005_071538_phil.mp3` (21,813 bytes; 2.56 seconds; 24 kHz). This proves that bounded sample only, not an entire episode or the new composer.

Repair code now present, but workflow acceptance is still pending:

- Ads: expanded validated target range 5-120 seconds; custom script and speaker identities persisted; requested/resolved voice provenance; one-based UI insertion with zero-based API positions; idempotent insertion; asset metadata excluded from the ad-record listing. Produced ad audio is padded only when shorter than the requested target, while overlong speech raises an explicit validation failure. Added saved composition schema, save/render routes, and `VisualAdComposer.jsx`.
- Social: typed export options now consumed; aspect sizing, quote copy, clip timing, waveform setting, platform metadata and downloadable post copy; static exports no longer require audio; unique output directories/manifests; real brand-image availability endpoint; path-boundary checks. Presets are connected to the form. Slideshow/ad-card error handling and rendering gaps remain unfinished.
- System: concurrent diagnostics for writer/model, WSL Kokoro, Qwen services, GPU, OS/process resources, media tools, storage/assets, job records, OBS and mixer. Frontend refreshes every 15 seconds, labels probe sources/timestamps and stale readings, and tests WebSocket handshake/echo without calling it production progress. New Win32 CPU/RAM counters are compiled but not live-verified yet.
- Episodes: 15-45-minute schema/UI targets, section-aware generation with prior-section history/repeat filters, stricter exact-repeat gate, progress records and generation ownership lock. Removed the active 5,000-word production floor/template expansion and silent placeholder-audio fallback. Added reuse of fingerprint-matched produced ad audio and shared SFX mixing. These changes need isolated regression and real bounded acceptance tests.
- Shared UI: associated form labels, dialog semantics/focus trap/Escape, accessible toast status and cross-tab selected-episode continuity.

Verified at pause:

- `py -3.12 -m compileall -q backend/app` passed.
- `npm run build` in `frontend` passed: 1,500 modules, JS bundle 288.81 kB / gzip 83.45 kB. Existing Vite/plugin and Browserslist warnings remain.
- `git diff --check` passed.
- Live early-version diagnostics answered and identified DeepSeek correctly; GPU read 5,572 / 6,144 MiB VRAM, 3% utilization, 73 C at that particular check.
- That live check found selected Kokoro unavailable: `/home/bryan/.venvs/gpu/bin/python` and `/home/bryan/wsl_tts_worker.py` are missing in the default Ubuntu WSL. Configured theme music and all six brand PNGs are missing. These are not repaired or substituted.
- Before screenshots are saved in `staging/audit-01-ads-before.png` through `audit-05-slideshow-before.png`, plus `audit-07-system-before.png`. No accepted after-render screenshots exist yet.

Important: the running backend was last restarted before the later episode/composer changes. Successful compile/build does not mean those latest changes are loaded or working end to end. Recent backend logs still include a writer timeout. Operator episode/draft/config/job changes are present in the dirty tree; preserve them.

Resume instructions and separate acceptance tracks are at the top of `docs/operations/NEXT_INSTANCE_NOTES.md`.

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
