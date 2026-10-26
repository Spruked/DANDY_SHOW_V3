# Dandy workspace consolidation

Reviewed October 26, 2026. The active development target is
`C:\Users\bryan\Desktop\Dandy\DANDY_SHOW_V3` (`Spruked/DANDY_SHOW_V3`).
`C:\Users\bryan\Desktop\Projects\Dandy` (`Spruked/Dandy`, source commit
`74bbdc1`) is retained as a reference. No source, episode data, repository,
or VS Code window in the older workspace was deleted or changed.

## Transferred functionality

| Capability | Integration in V3 | Verification |
| --- | --- | --- |
| Live production progress | Existing episode WebSocket channel and persisted job/status records now report stage, line/chunk, percentage, completion, and errors. Editor connects automatically; polling recovers status after disconnect/reload. | Worker callbacks, real ASGI WebSocket delivery, persisted status route, browser progress and reload checks. |
| Selected-section regeneration | Existing edit-script endpoint calls V3's configured LLM writer in a worker thread. Replaces 1–30 Phil/Jim lines, preserving the rest exactly. Keeps speaker order, pacing, source provenance, and version history. | Range, speaker-order, offline-writer, quality-rejection, untouched-prefix/suffix, and concurrent-edit tests. |
| Tone and pacing | Existing editor offers humorous/serious dialogue transformations and faster/slower pauses, scoped to a range. Host and ad lines remain unchanged. Original authorship remains recorded alongside editorial adjustment metadata. | Dialogue/idempotency checks, actual synthesis-segment pause values, persisted versions and rollback, browser controls. |
| Engine statistics | Existing production metadata/results, episode detail, persisted job/status, and progress events carry actual engine usage. | Worker and endpoint tests cover Kokoro, Edge, Qwen, and split lines. Browser displays counts. |

Engine statistics distinguish `engine_stats` (number of synthesized chunks) from
`engine_line_stats` (distinct script lines served by each engine). A line split
across two engines appears in both engine line counts; their sum can exceed
`synthesized_line_count`. Intro/outro synthesis outside the dialogue segment
pipeline is not included in these counts.

The existing `POST /api/episodes/edit-script` contract gains `regenerate_section`,
`section_start`, `section_end`, and `instructions`. API ranges are zero-based with
an exclusive end; the UI uses inclusive line numbers starting at one.
`adjust_tone` accepts the same optional range and presets `more_humorous`,
`more_serious`, `faster_paced`, and `slower_paced`; direct emotion strings remain
supported for API compatibility.

`GET /api/episodes/{episode_id}/production-status` returns persisted state.
Production messages are `production_progress`, `production_complete`, or
`production_error`, broadcast on `/ws/{episode_id}`. Existing connection/echo
behavior remains available. Persisted status is recoverable after reconnect;
interrupted rendering itself does not automatically resume after a server crash.

The production orchestration now records failures rather than generating silent
placeholder audio and calling it success. A missing audio file or failed social
export prevents completion. Previously generated audio is not deleted by failure
handling. Each production job gets its own worker to avoid cross-episode
personality-setting leakage.

## Deliberately left behind

| Source | Decision and reason |
| --- | --- |
| `poel_system.py` | Excluded. It contains static pattern/configuration data and loaders, but the backend calls an undefined `analyze_episode_performance` method. Its CLI also calls an undefined `run_maintenance_cycle`. There is no implemented performance-analysis algorithm to preserve. Static, unvalidated effectiveness weights are not evidence of audience response. V3 already has script quality, repetition, provenance, and rhythm analysis. |
| `studio.html` | Reviewed, not imported. Its useful runtime/line telemetry, exports, voice controls, intro/outro settings, and segment reordering overlap V3 capabilities. The additional segment-planning timeline, music/NFT showcase fields, and expanded brief/run-sheet exports use a separate local segment model. They are deliberately excluded from this bounded consolidation because adopting them would introduce a new planning contract and interface scope. Their original source remains intact for later reference. |
| Standalone `app.tsx` and alternate React studio/dashboard | Excluded as competing application entry points. V3 keeps its existing five-tab interface. |
| Old storage/job implementation | Excluded. In-memory jobs are lost on restart; replacement writes can omit previously saved configuration/history. V3 keeps its existing file contracts. |
| Old API client/proxy and voice defaults | Excluded. Route-prefix mismatches and contradictory voice assignments would regress V3. V3's configured voices and API aliases remain authoritative. |
| Old SKG implementations, direct TTS wrappers, vendored Kokoro | Left as reference. V3 retains its established personality, LLM, WSL TTS, and fallback architecture; no duplicate engines or knowledge-graph systems were added. |
| Old episodes, test payloads, source, dependencies, and models | Not migrated or deleted. Feature consolidation does not silently convert or overwrite production data. Original files and Git history remain available in the older repository. |

## Job and data compatibility

Episode detail now exposes a valid existing `job_id`. The frontend reuses it
after a reload, rather than recreating a draft and resetting an active production
status. Generation reads the current saved episode configuration, falling back to
draft fields, and runs its heavy work outside the ASGI event loop. Duplicate
production of an episode already marked `producing` returns HTTP 409. Existing
word-count/provenance checks remain in force.

The pre-existing local changes to `episodes/.drafts/DANDY_EP_002.json` and
`episodes/.drafts/jobs/job_DANDY_EP_002_2d4a0114.json` were left outside the integration
commits. Integration tests use temporary storage; browser tests intercept all API
and WebSocket fixture traffic and perform no real episode writes.

`CONSOLIDATION_PRESERVATION.json` records SHA-256 hashes of 61 tracked original
source/data files, the older repository commit, its clean worktree status, and
the Kokoro submodule pointer. Dependency folders and bytecode are excluded from
that inventory. This is an integrity inventory, not a backup or a claim that
untracked/generated data has been migrated.

## Validation and checkpoints

- 20 isolated backend contract/regression tests: progress, WebSockets, failures,
  engine statistics, regeneration, editorial controls, versions/rollback,
  persisted jobs, saved config/script-feed, word gate, and legacy editing/exports.
- Frontend production build passes.
- Microsoft Edge browser fixture check passes for regeneration range mapping,
  tone/pacing submission, persisted-job reuse, live progress/statistics, failure,
  and reload recovery, without JavaScript page errors.
- Existing live smoke suite passes all 29 checks. OBS/mixer HTTP 503 responses
  are accepted optional-hardware results, not successful hardware integration.
- Older repository remains clean. Original inventoried source/data hashes are
  checked after the integration.

Feature checkpoints on the current branch:

1. `558e2a2` — persisted production progress and truthful failures.
2. `cb927ad` — selected-section regeneration.
3. `a8313d1` — dialogue tone and pacing controls.
4. `78039b1` — actual TTS engine statistics.
5. `d7237e4` — persisted-job reuse, current saved config, editor regression tests,
   and browser verification.

Named refs under `refs/dandy-checkpoints/` also retain these checkpoints. Follow-up
contract fixes, browser verification, and this report are committed separately.
Recover source through Git history or create a new branch at a checkpoint;
do not reset or discard local episode data to review an earlier implementation.

Reproduce backend checks from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Build from `frontend/` with `npm run build`. With Vite running, browser checks use
`.venv\Scripts\python.exe scripts/verify_consolidation_ui.py`. That optional check
requires the Python `playwright` package and installed Microsoft Edge. Neither is
a new production dependency.

## Completion boundary

Source consolidation and isolated contract verification are complete. No wholesale
merge, redesign, parallel app, data migration, or deletion was performed. V3 is
the development target; the older copy should receive no new development.

Full production acceptance remains pending: the configured LLM services on ports
5199/40343 are offline and FFmpeg is absent from the current runtime PATH. The
successful automated production tests substitute TTS/LLM/media outputs; they do
not prove a real narrated episode can currently render. Existing frontend
dependency conflicts, storage-path validation risks, and the missing `/renders`
Vite proxy are also outside this feature transfer.

The older VS Code window remains open. Final workspace closure is deferred until
the external production acceptance requirement is satisfied. Its folder and
GitHub repository remain preserved regardless; deletion is not authorized.
