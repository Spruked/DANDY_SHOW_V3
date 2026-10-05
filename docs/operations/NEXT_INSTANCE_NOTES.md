# Dandy Studio - Next Instance Notes

## Active handoff - 2026-10-05, paused at the operator's request

**Resume this unfinished work; do not treat the audit/repairs as complete.** Operator requested stopping for usage-credit reset. No further implementation or runtime restart should be inferred from this handoff alone; resume when requested. Historical notes below refer to other dates/checkouts and are not current runtime authority.

### Canonical workspace and boundaries

- Active checkout: `C:\dev\Desktop\The Real Dandy\Dandy-Studio-Qwen` (PowerShell, Windows Python 3.12).
- Additional workspace: `C:\dev\Desktop\Phil_and_Jim_Dandy_Show`; do not migrate or overwrite its assets by assumption.
- Preserve all dirty/untracked operator episodes, `.drafts`, job records, root `package-lock.json`, audio/media and branding. No commit/push/cleanup has been authorized.
- User's hard contract: entered/selected script, duration and voice identity must survive UI -> API -> validation -> stored ad -> insertion -> TTS/render -> final output, or fail explicitly. Do not fix fake controls by removing options.
- Local inference only; no cloud/browser-voice fallback. ADS owns ad copy/voice/timing/insertion/visual treatment; SOCIAL owns standalone cards/post variants; STUDIO owns OBS/mixer/cameras; SYSTEM should own monitoring.
- User also requested 15-45-minute episodes in up-to-15-minute sections, ads between sections, reduced repetition, simpler intro/outro, and a saved visual/SFX/text/animation ad editor.

### Last verified runtime (re-probe on resume)

| Component | Endpoint | Last observed PID |
| --- | --- | --- |
| Frontend | `http://127.0.0.1:5173/` | 13936 |
| Backend | `http://127.0.0.1:8110/` | 6192 |
| DeepSeek llama.cpp | `http://127.0.0.1:40343/v1` | 11508 |
| Qwen bridge | `http://127.0.0.1:8020` | 15416 |
| Qwen CustomVoice | `http://127.0.0.1:8031` | 9868 |
| Qwen operator UI | `http://127.0.0.1:7861` | 13428 |

- Actual model: `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf`, discovered from `/v1/models`, not the old `8009` memory route.
- Python executable: `C:\Users\bryan\AppData\Local\Programs\Python\Python312\python.exe`; `py -3.12` also works.
- Real media binaries: `C:\dev\Desktop\The Real Dandy\Dandy\staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin`. Launcher sets `DANDY_FFMPEG` / `DANDY_FFPROBE` and PATH.
- Logs: `logs/backend.out.log`, `logs/backend.err.log`. Existing stack launcher: `scripts/start_dandy_stack.ps1`; avoid broad `-Restart` while unrelated/local jobs are active. Inspect exact ownership before stopping any PID.
- **Latest backend edits are NOT all loaded into PID 6192.** The last restart preceded the newer episode/voice/composer changes. Check active jobs before a scoped backend restart. Frontend HMR may already show newer controls than the backend supports.
- Live diagnostics `/api/system/diagnostics` answered before those later changes. Selected engine was Kokoro. Ubuntu is the default WSL; neither expected Kokoro Python nor worker file exists. Only `pops-website` appeared under `/home/bryan/.venvs`. Do not silently switch production voices to Qwen or invent a functioning Kokoro runtime.
- Required theme `audio/jingles/phil_jim_theme.mp3` and all six `social/templates` / `social/assets` brand PNGs are missing. Explicit plain backgrounds are supported; selecting a missing brand asset should fail validation.
- Writer/model availability is not inference proof; Qwen reachability is not synthesis proof. A bounded DeepSeek completion and Qwen MP3 sample were verified earlier, but recent logs still show script-writer timeouts. GPU snapshot was 5,572/6,144 MiB VRAM; recheck, do not assume spare capacity.

### What has been edited

1. Ads: `backend/app/api/ads.py`, `schemas/ads.py`, `services/storage/episode_store.py`, frontend `AdTab.jsx`, `lib/api.js`. Custom copy/voice/duration preservation, insertion tags/idempotence, asset-list filtering, selected presets, target/actual duration and voice provenance. New composition schema/routes. Audio shorter than target is padded, not script-expanded; overlong voice fails instead of being truncated. Custom registered voice keys are supported, but need acceptance tests.
2. Visual composition: new `frontend/src/components/VisualAdComposer.jsx`; shared renderer in `backend/app/services/social/slideshow_renderer.py`; audio mix helper in `services/production/ads.py`. Four tracks, timeline, attached image/video/SFX choices, saved motion/font/timing settings, actual MP4 download/preview. Renderer uses Pillow frames piped to local FFmpeg; none of its output has been tested yet.
3. Social exports: `api/social.py`, `schemas/social_visual.py`, `thumbnail_generator.py`, `audiogram_generator.py`, frontend `ExportsMode.jsx`, `SocialTab.jsx`. Typed options, real image/video sizing and clips, waveform switch, quote/post copy, unique manifests, downloads, real missing-asset state. `social_adcards.py` now accepts episode-scoped card lookup.
4. Telemetry: `api/system.py`, `tts/kokoro_wrapper.py`, `SystemTab.jsx`, `App.jsx`. Live service/model/GPU/tool/resource/storage/OBS/mixer checks, recorded job/generation ownership, cache/stale labels, real browser WebSocket echo. Windows ctypes resource counters were added because psutil is absent, but only the earlier version was live-probed.
5. Episodes: `schemas/episode.py`, `api/library.py`, `api/production.py`, `api/segment_production.py`, `services/production/segment_worker.py`, `worker.py`, `EpisodeTab.jsx`, `lib/api.js`. Targets 900-2700 seconds, latest config used for generation, user custom instructions preserved, sequential sections/prior history, stricter repetition report, generation lock/progress records, no active placeholder fallback or repetitive duration expansion. Produced ads should be reused only when their copy/voice fingerprint matches; shared SFX applies to assembly too. Intro/outro failure now fails production visibly.
6. Shared UI: `ui.jsx` labels/dialog focus/Escape/status; selected episode preserved across workflow tabs. Existing launcher/bridge-script edits from startup recovery remain.

### Verification completed and limits

- At pause, backend compileall, frontend production build and `git diff --check` all passed. No isolated regression tests have been added/run yet. No 15/30/45-minute final episode, visual ad MP4, selected social-export video, or final ad insertion/audio reuse has been accepted.
- Real Qwen probe: `secondary_systems/Dandy_Qwen_TTS_Ui/generated_audio/20261005_071538_phil.mp3`, 21,813 bytes, 2.56s, 24 kHz. Preserve it.
- Screenshots captured/inspected: `staging/audit-01-ads-before.png`, `audit-02-ad-form-before.png`, `audit-03-social-before.png`, `audit-04-social-form-before.png`, `audit-05-slideshow-before.png`, `audit-07-system-before.png`. Screenshot 06 and after-state captures remain pending. System screenshot 07 shows the old hardcoded/loading state, not the new live page.
- Browser fallback: installed Playwright via Node `require('C:/Users/bryan/AppData/Local/Programs/Python/Python312/Lib/site-packages/playwright/driver/package')`. No in-app browser/NodeREPL tool was available. Always close headless browser in `finally`; wait for observed DOM/data before screenshots. Do not repeat the policy-blocked GUI browser-launch workaround.
- Read skills `product-design:audit`, product-design index/user-context/references and browser control skill before resuming their workflows. Audit skill requires screenshot-first evidence and an inline, numbered flow-health report unless the user requests a canvas. Preserve the theme/layout.

### Resume order - separate acceptance tracks

1. **Establish current ownership/data first.** Inspect git diff, listener PIDs, current episode/job state and logs. The operator was interacting with the app during this work; do not undo their DANDY_EP_002 draft/config changes or untracked jobs. Re-probe services and only reload the exact backend when safe. Re-read repository instructions.
2. **Build isolated regressions before additional features.** Use existing `scripts/` layout, TemporaryDirectory and patched storage roots/TestClient; do not regenerate/insert/render against real episodes merely to test. Existing `scripts/smoke_test.py` contains mutating POSTs and historical assumptions; inspect before running it.
3. **Ads acceptance:** custom copy byte/text preservation; 60/90/120s validation across all layers; Phil/Jim/announcer/custom registry identity; deterministic insertion bounds/indexing/idempotence and tagged copies; metadata sidecar filtering; actual short-ad synthesis + target padding/overlong rejection; fingerprint-matched reuse in episode assembly, including SFX. Review catalog `services/ads/ad_engine.py`: its old normalization/filler logic still exists and can ignore duration intent. Generic `generate_ad_lines` remains repetitive/templated; refine without inventing sponsor claims.
4. **Composer acceptance:** save/reload all properties; validate unknown/missing assets and timing; render a short isolated sample with real local audio, text entrance/exit, image/video and SFX. Use ffprobe to prove aspect, duration and audio streams, inspect frames at beginning/middle/end and listen to SFX. Test every motion choice. Review frame-pipe subprocess cleanup/timeouts and layer ordering. Current version is a first implementation, not production-proven.
5. **Social acceptance:** presets and platform metadata; 1:1/16:9/9:16/4:5 dimensions; image/quote/show-notes without audio; clip start/duration with actual media; waveform on/off measurably changes output; literal quote and post copy survive; renderer failures/missing assets produce errors, not success; output uniqueness/download containment. Catch subprocess errors with useful API detail. Failed attempts currently may leave incomplete scratch exports (no completed manifest); handle deliberately.
6. **Finish standalone builders.** `SlideshowBuilder.jsx` and `AdCardsBuilder.jsx` still use raw fetch without response.ok handling, can claim saved/open downloads after failure, have stale-state/popup issues and wrong `/assets/...` preview URLs. Prepared file snapshots were read but not edited. Use shared `req`, explicit feedback and download links; correct deletion selection and load races. Renderer still lacks real slideshow animations/timing-gap semantics, UTF-8/path hardening, product-image/QR/template differentiation and robust text wrapping. Keep options; implement their contracts instead of removing them.
7. **Episodes acceptance:** test old loops/repeated 6-8-line sequences, cross-section near-duplicates, 15/30/45-minute plans, no global restart/seed padding, current edited config and instructions, and saved-ad-only boundary insertion without voice remapping. Check section word budgets/QC and long-form inference timeouts with actual DeepSeek. Persist failure state for every exit, including post-generation publication guard. Final MP3 duration still needs a measured 15-45-minute gate: word-count estimates alone cannot guarantee it. `_legacy_structure_unused` and old unused helpers remain; inspect callers before cleanup.
8. **Intro/outro is unfinished.** Simpler controls were added on System, but user now wants SYSTEM to be telemetry only: move editing into the episode workflow without dropping advanced options. `intro_outro.py` still synthesizes announcers through missing Kokoro WSL regardless of selected production engine. Align preview/final synthesis with explicit engine/voice semantics; keep existing spoken narration deterministic, no LLM rewrite. Missing music must be resolved by operator selection or explicit disabling, not an invented replacement.
9. **Telemetry acceptance:** verify current Win32 CPU/RAM/backend RSS against OS data, GPU against nvidia-smi, actual executable paths/version, disk and missing assets, current writer model, selected engine, WSL/Qwen status, authenticated OBS/mixer, handshake echo. Show unavailable/unverified/cached/stale honestly; do not infer camera frames from an OBS scene. Probe endpoints with bounded delays/errors and keep UI responsive during long generation. Per-probe server timeouts and synthesis/device provenance need further review. Current summary can say ready for dependencies while inference/synthesis remains explicitly unverified; assess whether to name that state more narrowly.
10. **Finish evidence/report.** Save accepted after screenshots and a concise findings/remaining-improvements report in existing docs, link evidence and distinguish static build, mocked regressions, bounded real output and whole-episode acceptance. Update dev log/handoff again. Do not mark the whole task done just because build/compile pass.

### Historical notes (not current runtime instructions)

## Runtime baseline
- Backend target port: `8010`
- Frontend path: `frontend/` (Vite dev server `5173`, proxy to `8010`)
- SKG runtime files in use:
  - `./phil_dandy_skg.py`
  - `./Jim_dandy_skg.py`

## Backend startup
```powershell
cd backend
$env:PATH="C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show\staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin;$env:PATH"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

## Frontend startup
```powershell
cd frontend
npm install
npm run dev
```

## Health checks
```powershell
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/api/voices
cd frontend; npm run build
```

## Notes
- Historical test/probe episode assets were moved under `archive/testing/results/episodes/`.
- Historical test/probe draft/job records were moved under `archive/testing/results/drafts/`.
- Runtime test logs were moved under `archive/testing/results/logs/`.
- Endpoint wiring audit is documented in `docs/ENDPOINT_WIRING_AUDIT.md`.

## Performance note (2026-04-04)
- Observed CPU pressure led by `vmmem` (WSL) and Orb runtime Python process (`R:\Orb_Assistant_Desktop\electron\src\floating_assistant_orb.py`).
- WSL CPU cap configured in `C:\Users\bryan\.wslconfig`:
  - `[wsl2]`
  - `processors=6`
  - `gpu=true`
- Per operator request, WSL and Orb were kept running (no immediate `wsl --shutdown`).
- CPU cap applies on next WSL restart.

## Session note (2026-04-24)
- Adaptive rhythm guardrails are now wired in production generation:
  - `backend/app/services/production/rhythm.py`
  - `backend/app/services/production/communication_layer.py`
  - `backend/app/services/production/dandy_harmonizer.py`
  - `backend/app/services/production/worker.py`
- Rhythm now includes observed vs commanded fields with:
  - bounded one-step changes (`tempo`, `intensity`, `verbosity`)
  - cooldown anti-thrash window (`cooldown_until_ms`)
  - monotonic update versioning (`version`)
- Startup/reboot reliability script added:
  - `scripts/start_dandy_stack.ps1`
  - supports `-Restart` to stop listeners on `8010` and `5173` before relaunch
- Log finding from previous startup failure:
  - `logs/backend_20260418_022854.err.log` shows a malformed PATH command being executed as standalone commands.
  - Use the startup script above (or exact README command blocks) to avoid PATH command corruption.

## Session note (2026-05-01)
- Studio was started for this session:
  - Backend: `http://127.0.0.1:8010`
  - Frontend: `http://127.0.0.1:5173`
  - Logs: `logs/backend.*.log`, `logs/frontend.*.log`
- Active SKG runtime files are still root-level:
  - `phil_dandy_skg.py`
  - `Jim_dandy_skg.py`
  - The referenced `backend/app/services/production/phil_client.py` and `jim_client.py` files do not exist.
- Script-generation fixes completed:
  - `backend/app/services/production/communication_layer.py`
    - `_generate_topic_banter` now selects `template_domain`, stores it in context, and routes stages through `opening -> expansion -> deepening -> reflection -> closing`.
    - `_select_template_domain` routes Happy Toes / Abby / poem / fatherhood / legacy / incarceration / literary / reinterpretation / book topics to `phil_jim_personal_story`.
    - `_build_context` hydrates personal-story variables: `title`, `idea`, `connection`, `insight`, `connected_idea`, `point`.
    - `_load_primary_source` added to load attached primary/reference/context assets and expose source text, summary, and keywords.
  - `phil_dandy_skg.py` and `Jim_dandy_skg.py`
    - `generate_response` accepts/preserves `template_domain` and sets `primary_source_priority`.
    - `semantic_template_selection` accepts `template_domain`, filters personal-story candidates to `domain == "personal_story"`, and boosts primary-source matches.
  - `backend/app/services/production/worker.py`
    - SKG script definitions include `episode_id` so asset loading can resolve primary sources.
    - Expansion QC now requires `ACCEPT`, not only non-`REJECT_RETRY`.
  - `backend/app/api/production.py`
    - Final generated scripts pass through `ScriptQualityGuard`; rejected output falls back to seed generation.
  - `backend/app/services/production/quality_guard.py`
    - Duplicate-line and unique-line-ratio checks added to reject looping output.
  - `backend/app/services/production/script_seed.py` and `script_expander.py`
    - Shortening improved for long narrative key points.
    - Personal-story fallback lines added.
    - Generic `{point}`, `{related}`, and `{earlier_point}` templates are bypassed when domain is `personal_story` or the point is long/unsafe.
  - `backend/app/services/storage/episode_store.py`
    - Script metadata recalculation added on `save_script`: line counts, speaker counts, ad count, estimated runtime.
- Investigation results:
  - No active `template_registry.json` found.
  - No active disk template folders found for `templates/phil_jim*`, `templates/conversational`, or `templates/general`.
  - `phil_dandy_skg_v3/` and `jim_dandy_skg_v3/` exist but are empty; no `learned_patterns_v3.jsonl` files were present.
  - Malformed phrases were traced to episode draft/config key points, not SKG learned-pattern storage:
    - `episodes/.drafts/DANDY_EP_002.json`
    - `episodes/DANDY_EP_002/config.json`
- Verification completed during session:
  - Python compile checks passed for modified production files.
  - A short `DANDY_EP_002` seed-generation probe no longer emitted:
    - `Happy Toes was written for Abby`
    - `poem expanded into a full book`
    - `project reveals about fatherhood`
- Current operator note:
  - Episode production was in progress when this note was added.
  - Do not modify code, episode files, script versions, audio outputs, or production status until the active production run finishes.

## Session note (2026-05-01) — LLM wiring and boundary rule

- LLM (Ollama/qwen3.5:4b via substrate governance bridge) wired into script generation:
  - `backend/app/services/production/llm_writer.py` — new file, governed LLM bridge caller
  - `backend/app/services/production/communication_layer.py` — `_try_llm_topic_banter()` calls LLM first; SKG is fallback
  - `backend/app/api/production.py` — `GET /writer-status` endpoint; `writer_engine` and `bridge_reachable_at_start` saved to every episode's `status.json` and `production_result.json`
  - `frontend/src/components/EpisodeTab.jsx` — Script Engine indicator (green/amber) above stats bar; PRODUCE warns and blocks if bridge is offline
  - `frontend/src/lib/api.js` — `api.writerStatus()` added
- Bridge URL: `http://127.0.0.1:5199` (start with `R:\substrate\governance\start_bridge.bat`)
- Role: `dandy_scriptwriter` (governance YAML: `R:\substrate\governance\llm_runtime_config.yaml`)
- Model: `qwen3.5:4b`, temperature 0.25, think: false, num_predict: 2048

### LLM role in Dandy Studio

- Dandy Studio is a single-operator tool — Bryan only. No ORB in this system.
- The LLM is a creative production assistant for the full ecosystem:
  scripts, ads, social content, descriptions, titles, captions, visual copy, promos.
- Bryan is the final decision maker on what ships.
- The LLM creates. Bryan decides.
- For script generation: SKG builds the brief → LLM writes the lines →
  ScriptQualityGuard checks quality → Dandy produces audio.
- Full context: `docs/operations/AI_Operating_Guidelines.md`
