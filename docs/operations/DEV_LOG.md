# Dandy Studio Dev Log

## 2026-09-06 - Windows-native Qwen Studio and Voice Forge integration

Scope: `C:\dev\Desktop\The Real Dandy\Dandy`

- Repaired Dandy's local llama.cpp writer target to `http://127.0.0.1:8009/v1`; health reports the loaded Qwen 2.5 1.5B GGUF model.
- Wired the existing Windows CUDA Qwen 3 TTS stack: bridge `8020`, CustomVoice `8031`, and operator UI `7861`. The bridge now uses the active Dandy root and `R:\Services\qwen_tts_312` runtime.
- Selected Qwen as production TTS. A bridge probe generated `staging/qwen_studio/qwen_studio_probe.mp3` successfully after first-run warm-up.
- Added `voice_forge_2.0/` as first-party source and added a guarded Dandy adapter. It remains disabled until Coqui XTTS and non-placeholder minted embeddings are local.
- Removed the mixer backend, dependency, routes, polling, controls, and macros. Studio is now OBS-only; episode creation, production, and social exports remain the primary workflow.
- Validation: 14 repair tests passed; endpoint audit found `37` frontend routes, `112` backend routes, and `0` unmatched; `npm.cmd run build` passed.

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
