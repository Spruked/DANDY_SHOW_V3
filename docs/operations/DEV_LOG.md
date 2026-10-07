# Dandy Studio Dev Log

## 2026-10-06 - Production Editor first operational layer and addressable takes

The operator clarified that the Episodes **Audio** player is the destination for produced audio. The earlier statement that Dandy has no place for it was incorrect. `ep_1791247143016/audio.mp3` is a real 6,090,669-byte MP3, 253.725896 seconds, 48 kHz stereo; status is `produced`. A matching-hash copy is retained at `episodes/ep_1791247143016/audio.baseline_001.mp3`. The player screenshot showed `0:00 / 0:00`; the API had been returning `Content-Disposition: attachment`. Normal GET/HEAD now serve inline audio; `?download=1` serves an attachment. Live through the 5173 proxy, HEAD is 200 and a byte-range GET is 206 with `Content-Range: bytes 0-1023/6090669`. Browser playback after the change is not yet visually verified.

Operator listening review of Baseline 001: the Qwen voices and full assembly are usable, but the middle sounds read rather than conversational; similar handoff gaps make edit boundaries audible. Treat that as the A/B comparison target. This implementation varies pauses and prepares known abbreviations for TTS; it does not claim to solve reaction, callbacks, mispronunciation, or acting quality. Controlled BRIDGE and richer Performance suggestions remain later editor work. Do not overwrite Baseline 001.

Implemented the first functional Production Editor boundary before TTS, based on the two operator-supplied design notes:

- `production_editor.py` defines bounded Editorial, Performance, Director, Campaign, Arbiter and QC MORB roles. Proposals are structured; Arbiter policy alone decides. Current automatic changes are whitespace/known-abbreviation normalization and bounded handoff timing chosen from a five-turn context window. Existing generated pauses can be varied; `pause_locked` retains an intentional setting. Incomplete endings are flagged, unknown/non-audio DIRECT assets are rejected, and `allow_embellish` is off unless explicitly enabled. No model call is made by this first editor; generative editorial proposals are not yet enabled.
- The editor preserves `script.json` and writes `production_script.v1.json`, `change_ledger.v1.json`, `production_plan.v1.json`, and `editor_run_ledger.v1.json`. Same script/config/assets produce byte-identical production script and change ledger. An editor failure passes the approved script through and records the failure.
- `worker.py` now stores individual Qwen line/chunk takes under each episode's `takes/` directory and writes `production_manifest.json` with segment IDs, source hash, speaker/text, delivery, take number, relative audio path, duration and SHA-256. It builds a candidate master before replacing `audio.mp3`; previous full masters/manifests are retained. Existing audio is not touched by the code change itself.
- A selected line in Episodes can request one new Qwen take. The background revision endpoint validates the current script/cues and every saved take hash, synthesizes only that line, reuses the rest, reapplies current saved media cues plus recorded global SFX/theme settings, and rebuilds the master. It retains prior takes/master and writes revision status/change ledger. A baseline without saved takes cannot use this feature until produced once through this version.
- After production, the assembly graph records dialogue/pause nodes and global treatments; QC verifies final audio presence, take integrity by line ID, implausibly short takes, unfinished approved lines, and configured treatments. Advanced ASR, mispronunciation, clipping and perceptual performance measurements remain future work. The UI exposes the editor report, line QC flags, and line regenerate control without a layout redesign.

Files changed for this layer: `backend/app/services/production/production_editor.py`, `production_manifest.py`, `worker.py`, `backend/app/api/production.py`, `backend/app/api/segment_production.py`, `frontend/src/components/EpisodeTab.jsx`, `frontend/src/lib/api.js`, `README.md`, and this log. Existing unrelated working-tree changes were preserved.

Verification: Python compileall passed; frontend Vite build passed; `git diff --check` passed. A temporary two-line run through the actual `SegmentAwarePodcastWorker` with synthetic MP3s and mocked Qwen/post-processing showed two initial takes, one Phil-only revision synthesis, Jim take reuse and a changed rebuilt master. Another temporary test proved editor output determinism, unchanged canonical script, invalid cue rejection and pass-through on registry failure. A further 24-line editor check preserved the source script and produced six distinct pause values; a synthetic normalization/manifest check retained the original line ID and source text after changing `e.g.` to its spoken form. A separate synthetic QC fixture produced two findings tied to one line ID (implausibly short take and unfinished source line). These tests did not call the real Qwen service or perform a full new episode production. Backend 8110 was restarted for the editor refinements; 8110, 5173, 40343 and 8020 returned HTTP 200. The launcher needed an explicit model ID because llama.cpp currently exposes the loaded model as `local` rather than a DeepSeek-named ID; no llama.cpp process was restarted.

Remaining scope from the aspirational MORB roadmap: generative editorial/Performance suggestions, operator approval for substantive changes, addressable FX/ad/theme replacement, reusable take cache, richer audio QC/ASR, campaign adaptation, derivative cuts and distribution. Those are not claimed by this first layer. The completed baseline should be listened to before a new production overwrites the active `audio.mp3`.

## 2026-10-06 - Bounded saved-episode production repair; operator test pending

Scope: prepare `ep_1791247143016` (24 Phil/Jim lines, 612 words) for real Qwen/FFmpeg production. No script regeneration, synthesis, listening, episode rendering, clone creation, saved-profile conversion, fallback voices, UI redesign, commit or push was performed. The operator owns end-to-end acceptance.

Findings and dispositions:

| Severity | Finding | Disposition |
| --- | --- | --- |
| Blocker | Bridge 8020 inherited `DANDY_FFMPEG` and `DANDY_FFPROBE` pointing under this checkout's absent `staging/ffmpeg` installation. `subprocess.run` in reference duration validation therefore failed before the synthesis call to 8032. | Bridge/launcher now resolve the existing sibling installation; explicit invalid overrides fail with the exact missing dependency. Health exposes both tool paths. |
| Blocker | Reference audio was passed to `Client.predict(ref_aud=...)` as a string. The running 8032 `/run_voice_clone` schema requires Gradio FileData. | Both reference WAV and saved-prompt branches use `gradio_client.handle_file`. Verified against the live API schema and mocked transport contracts, without inference. |
| Blocker | Enabled intro/outro narration invoked the unavailable Kokoro WSL worker after dialogue synthesis. | Per the operator's existing instruction to use `introclip.mp3` for episode opening/ending, explicit `narration_enabled=false` plays the real theme alone for 18 seconds at each end. Existing announcer text is retained. This is a project-wide intro/outro setting, not a voice-provider substitution. |
| High concern | Bridge availability selection preferred 8031, allowing configured clone identities to become CustomVoice speakers when switching models. | Clone requests now require 8032 and fail clearly if a conflicting backend is selected or Base is unavailable. Startup defaults to clone; no model was switched/restarted in this repair. |
| Medium concern | Pydub generated pause MP3s at 11.025 kHz while Qwen segments are 24 kHz, introducing stream rate changes in FFmpeg concat. | Pause generation now matches each source's sample rate, channels and sample width. Isolated mocked assembly contract passed. |
| Medium concern | Unicode Qwen errors could raise a second cp1252 logging exception; only a short FileNotFoundError reached prior logs. | Phase output escapes non-ASCII safely; synthesis exceptions now log full Python tracebacks. |

Additional findings (not changed; not blockers for saved Phil/Jim speech):

- Eleven saved lines lack terminal sentence punctuation; several visibly end mid-thought. Production preserves them as saved. Same-speaker consecutive lines and unverified manufacturer-specific examples need operator editorial review. The saved script was not edited.
- Brief generation review found a concrete instruction-loss problem: `segment_worker` appends continuity, creative instructions and the beat/governor agenda into `persona_brief`, while `llm_writer._build_prompt` includes only `persona_brief[:600]`. Later assignments can therefore be absent from actual inference prompts. Fix next by giving current assignments a separate bounded field that is always retained, rather than lengthening all history. No generation code was changed here.
- The writer still limits individual dialogue turns to 180 characters in grammar and parsing. This can force abrupt endings despite its complete-sentence instruction. Add a bounded complete-sentence validation/repair design in a separate generation change. Current settings remain 180-second request timeout, exchange-scaled budget capped at 1200 tokens, temperature 0.8, top-p 0.9, repeat penalty 1.12, frequency/presence penalties 0.05.
- Generation targets five-minute sections plus the remainder, with 90 spoken WPM (450 nominal words per five minutes), deterministic beats, EpisodeGovernor validation, conservative duplicate rejection and repetition warnings. No real inference was run. `/v1/models` is liveness/model metadata, not inference proof.
- Global SFX is enabled but the five configured slugs (`papers_rustling`, `papers_shuffling`, `phone_ring_distant`, `drawer_open`, `keyboard_typing`) are missing from `audio/sfx`. That helper skips missing effects. The separate library-media-cue path exists, but this saved episode has no media cues or ads. Map desired existing assets explicitly in a later content/config change; do not silently substitute sounds.
- `config/voices.json` still uses the existing `phildandyclone.wav` and `jimdandyclone.wav` plus stored transcripts. No Qwen-native saved prompt profiles are configured. This route is reference-conditioned synthesis through Base; it does not load a persistent `.pt` identity. Verify the transcripts match the current WAVs during acceptance. No reference, clone, transcript, or voice configuration was replaced.
- Current voice metadata still labels Qwen slots Ryan/Eric (and old primary_voice labels), although the clone path is reference-conditioned. Future provenance should record the actual reference/profile and backend instead of presenting those slot labels as proof of identity.
- VRAM snapshot was 5602/6144 MiB. Latency, peak-memory stability and the existing 180-second per-chunk synthesis timeout require the operator's real test. Avoid concurrent script generation during that test. This repair does not modify llama.cpp, Qwen CUDA configuration or switching architecture.
- Optional social package export happens after audio status/result publication. Social rendering can fail independently of a completed episode MP3. Loudness post-processing also has an existing direct real-MP3 export path on filter failure; inspect `production_metadata.json` for processing compliance. Final runtime is determined by audio measurement, not the UI word estimate.

Files changed in this repair (earlier working-tree changes were preserved):

- `secondary_systems/Dandy_Qwen_TTS_Ui/bridge.py`: media resolution/health, clone selection protection, FileData upload, bounded reference probe and full traceback logging.
- `secondary_systems/Dandy_Qwen_TTS_Ui/scripts/Start-QwenTTSBridge.ps1`: sibling media tools, startup dependency validation before stopping the old bridge, media PATH, UTF-8/unbuffered logs.
- `scripts/start_dandy_stack.ps1`: default Qwen mode clone.
- `backend/app/services/production/intro_outro.py`: explicit theme-only option.
- `backend/app/services/production/worker.py`: compatible pause encoding for concat.
- `config/config.json`: `intro_outro.narration_enabled=false`; theme and voice assets retained.
- `README.md` and this dev log: current production route, verification limits, next test and findings.

Validation completed:

- Python compile checks passed for the changed production/bridge modules; PowerShell parsing passed for both launchers; `git diff --check` passed.
- Seven isolated reference/upload/routing/error/theme contracts and one pause/concat contract passed. Client inference, output export and concatenation were mocked; these checks do not prove synthesis or final assembly.
- Real read-only ffprobe checks: Phil WAV 10.000s, mono 24 kHz; Jim WAV 10.320s, mono 24 kHz; theme 18.000s, stereo 48 kHz. Both existing FFmpeg and FFprobe executables run successfully.
- Bridge 8020 and FastAPI 8110 restarted with confirmed media tools. Logs were copied to `*.before_repair_*` first. Frontend 5173, Qwen 8032 and llama.cpp 40343 were left running. Live health confirms clone/Base 8032 and both media tools available; frontend HTTP 200 and writer model-list endpoint answered.
- Actual process CWD before restart: bridge at `secondary_systems/Dandy_Qwen_TTS_Ui`, Qwen 8032 at `R:/Services/qwen_engine`, FastAPI at `backend`. Backend and Qwen already inherited the working sibling tools; only bridge had stale missing paths.
- Saved-script SHA256: `a1e0bdecacb04c71cf99d5ba7b29288426c0aef23b7fb13d8e47f27a4400d6ea`. Original failed episode status was preserved; no production was queued.

Resume operator acceptance at **Episodes -> ep_1791247143016 -> PRODUCE** using its existing script. No further restart is required. Check first Phil/Jim voice identity, all 24 lines, audible pause timing, 18-second theme at both ends, then ffprobe the final MP3. Successful artifacts: `episodes/ep_1791247143016/audio.mp3`, `transcript.json`, `production_metadata.json`, `production_result.json`, and `status.json` with `produced`. For failure, capture the latest job ID and bridge `.out.log` phases / `.err.log` traceback plus backend logs. No end-to-end success or listening acceptance is claimed.

## 2026-10-05 - Generation progress, studio cleanup and camera connection

Canonical checkout: `C:\dev\Desktop\The Real Dandy\Dandy-Studio-Qwen`.

Completed and verified:

- Fixed the local DeepSeek/llama.cpp script path with bounded completion grammar, stage-sized exchange counts, scaled token budgets, opening-stage retry, and exchange-count telemetry.
- Added live job status at `/api/episodes/jobs/{job_id}` and visible frontend progress for script generation and background episode production.
- Removed Voicemeeter from the active app surface, diagnostics, and backend router registration.
- Added the Dandy Show Phil & Jim logo to the top navigation and enlarged/separated navigation tabs.
- Added browser camera discovery, permission-based connection, live preview, reconnect/disconnect controls, and device refresh under Studio > Cameras.
- Recovered the Episodes page after moving the progress polling hook below its `epId` initialization.

Verification:

- `py -3.12 -m compileall -q backend/app` passed.
- `npm run build` in `frontend` passed.
- `git diff --check` passed.
- Backend restarted and `/health` returned `healthy`.
- `/api/system/diagnostics` no longer reports a mixer check.
- No full 15-minute generation test was run by the agent; manual episode validation remains operator-owned.

Delivery:

- Code commit: `8e66384` (`Fix generation progress and studio runtime controls`).

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
## 2026-10-07 - Explicit Production Editor stage

- Added a dedicated top-level **PRODUCTION EDITOR** page based on `frontend/M4V9eui.jpg`, with an episode selector, read-only canonical pane, editable production-copy pane, MORB review, provenance hashes, approval state, and audio preview.
- Added canonical snapshot lookup by version, write-once versioned canonical scripts, separate editor drafts, and immutable approved production snapshots.
- Produce now requires the current approved version ID and passes that exact plan to the worker. Removed the implicit editor-preparation path and fail-closed the legacy `ProductionEditor.prepare()` compatibility method.
- Added validation for canonical/source hashes, production-copy hashes, production settings and cue assets; draft changes make approval stale. Line regeneration now addresses persistent production-line IDs and requires the current approved version.
- Checks: `python -m compileall -q backend/app`; backend application import and route registration; `npm run build`; isolated temporary-episode lifecycle smoke test (canonical immutability, selected historical snapshot, MORB review, approval hashes, stale approval after draft edit). No Qwen synthesis or episode production was run.
- The existing episode and baseline audio were not modified by the lifecycle smoke test. Backend 8110 was restarted after code changes; 8110 health and writer-status passed, 5173 served the new Production Editor page/tab, and 40343 `/v1/models` remained available as model `local`. The 5173 process and llama.cpp process were not restarted; Qwen services were not restarted. No script generation or episode production was run.

## 2026-10-07 - Four-stage script review flow

- Added a distinct Preview workspace between Generate and Production Editor. It selects immutable canonical versions and supports line marks/comments, section notes, and overall notes without changing canonical text.
- Preview review revisions are stored per canonical version with canonical-source and review hashes. Sending to Production Editor saves the current review and opens a draft that carries the full Preview package; Produce approval becomes stale if the bound Preview review changes.
- Production Editor displays the Preview handoff and only opens drafts from a saved Preview review. The four-step Generate → Preview → Production Editor → Produce state is visible in the episode flow and editor workspace. Preview and Production Editor page tabs are placed after SYSTEM in the top navigation, matching the supplied layout marking.
- Updated README with the four-stage contract and Preview endpoints.
- Verification: backend `compileall` and frontend `npm run build` pass. Temporary episode lifecycle test passed Preview save → handoff into Editor draft → approval → stale approval after changing Preview notes, while the canonical hash remained unchanged. Live API is healthy on 8110 and exposes all three Preview routes; Vite returns HTTP 200 on 5173 and its bundle contains the Preview handoff UI; llama.cpp `/v1/models` remains available on 40343 as `local`. Restarted only the backend listener (old PID 6124, current listener PID 20008); frontend PID 19952 and llama.cpp PID 10116 stayed running. No generation or production was run.

## 2026-10-07 - Social exports and preset panel

- Refined the Social > Exports right panel to use two columns of platform-colored, outlined preset buttons; widened the panel and added the exact asset-folder guidance plus ready/missing filenames.
- Preset clicks still open the Generate modal with platform/type/aspect populated. When the matching thumbnail or waveform base is available, it is selected as the default background. The logo slot is excluded from the background picker and identified as a Slideshow/Ad Cards asset.
- Social export list records now expose inline previews for image, video, and audio artifacts through a safe, root-confined preview route. The center-pane preview is height-limited; the existing download route remains separate.
- Inspection of the supplied screenshot found the old video cards were blank because `preview_url` was omitted for MP4 files; the export panel was also a 220px single-column preset list. The live asset API currently reports all six files missing. There is no upload control; files must be copied into `social/templates/` or `social/assets/` with their expected names.
- Checks: frontend production build and backend compile pass; live Social preset/asset APIs report 7 presets and 6 slots; an existing MP4 preview responded with HTTP 206, `video/mp4`, and byte-range support; Vite module returned HTTP 200; backend health passed. No export generation was run. A fresh after-change screenshot was unavailable in this session.
