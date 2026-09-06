# Dandy Studio - Current Runtime Notes (2026-09-06)

> Supersession: the active Dandy root is `C:\dev\Desktop\The Real Dandy\Dandy`; current ports are backend `8110`, frontend `5188`, llama.cpp `8009/v1`, Qwen bridge `8020`, CustomVoice `8031`, and Qwen UI `7861`. Historical `8010`, `5173`, governance-bridge, and mixer notes below are retained only as dated history.

## Runtime baseline
- Backend target port: `8110`
- Frontend path: `frontend/` (Vite dev server `5188`, proxy to `8110`)
- SKG runtime files in use:
  - `./phil_dandy_skg.py`
  - `./Jim_dandy_skg.py`

## Backend startup
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dandy_stack.ps1 -Restart
```

## Frontend startup
```powershell
cd frontend
npm install
npm.cmd run dev -- --host 127.0.0.1 --port 5188 --strictPort
```

## Health checks
```powershell
curl.exe http://127.0.0.1:8110/health
curl.exe http://127.0.0.1:8110/api/voices
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
