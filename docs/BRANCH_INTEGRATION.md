# GitHub branch integration — October 26, 2026

The integration target is `C:\Users\bryan\Desktop\DANDY_SHOW_V3`.
GitHub `main` and the local starting commit were `14755c4`.
Existing local, staged and untracked changes were preserved before integration.
No branch was merged wholesale and nothing was pushed to GitHub.

## Recovery

`archive/restore_points/branch-integration-20261026_182123/` contains:

- `workspace.zip`: 348 source, configuration, data and media files, verified against SHA-256 hashes.
- `manifest.json`: per-file integrity inventory.
- `repository.bundle`: all Git refs and reachable history, including a tracked-worktree checkpoint.
- `working-tree.patch`, `index.patch`, and `git-status.bin`: original unstaged/staged state.
- `merge-inventory.json` and `merge-preview/`: three-way comparison evidence.

Checkpoint branch: `checkpoint/pre-branch-integration-20261026_182123`.
The ZIP excludes installed environments, dependency/cache directories, previous
backup archives, and the held runtime advisory lock. Those were left untouched.
It includes untracked source and runtime records, unlike a Git-only checkpoint.
Restoration should first be verified in a separate directory, never by resetting
or overwriting the active workspace.

## Branch coverage and implementation decisions

| Branch | Head | Integration |
| --- | --- | --- |
| main | 14755c4 | Retain local storage safeguards, runtime/model pinning, progress, statistics, regeneration, tone/pacing and cleanup work. |
| fix/script-feed-authored-length | 39d190c | Already an ancestor of main; preserve authored script behavior. |
| pre-segment-duration-2026-08-17 | 39d190c | Same commit as the preceding branch. |
| segment-mode-1-15 | d2fc497 | Use the later segment worker implementation, support 1–45 minute targets, bypass the legacy long-show word floor for short or explicitly approved production. |
| dandy-live-snapshot-2026-09-05 | f5be6df | Use later asset, cancellation and studio implementations rather than older duplicate versions. |
| dandy-astra-repair-review-2026-09-06 | 9828ce3 | Restore Voice Forge source/adapter as optional tooling; preserve required Qwen rather than silently activating a different engine. |
| chatgpt-builder-hardening-2026-10-05 | 85049f6 | Restore hardened builders, visual ad composition and rendering through the later studio implementation. |
| feature/dandy-assembly-ui | 7b36f59 | Restore Assembly Board and Audacity, M3U and slide-manifest exports. |
| studio-qwen-console-v1 | 91d7a1f | Use the later integrated console; preserve current runtime launchers instead of obsolete machine paths. |
| studio-qwen-console-local | 391b60a | Restore Preview, Production Editor, canonical scripts, approvals, takes/manifests, single-line audio revisions, reusable assets/picker, diagnostics, cancellation, episode management and expanded social controls. |

Missing repository artwork, reference documents and reusable assets from the
studio branch were recovered without overwriting existing files. Old branch
episode records were not imported over operator records. Historical scripts
already archived under `archive/legacy-python` remain preserved there.

## Unified behavior

The normal UI workflow is Generate → Preview → Production Editor → Produce.
Preview notes refer to immutable canonical snapshots. Production drafts can be
edited without changing canonical dialogue. Approval pins the production copy,
Preview handoff, configuration, voice settings, ads and cue hashes. Changing
those inputs invalidates approval. The worker checks the approved data before
publishing a master.

Old episodes without an editor state can still call the compatible legacy API;
long legacy episodes retain the 5,000-word gate. Once an episode enters the editor
workflow, it cannot bypass approval by omitting an approval ID. Short approved
scripts are rendered as approved, without template expansion or invented ads.

Existing persisted production progress, WebSocket events, failure states,
per-engine statistics, section rewriting and tone/pacing controls remain active.
Workers are owned by individual production jobs. Full production and line
revisions share the studio production slot. Cancellation is cooperative between
synthesis chunks; an in-flight model call can finish before cancellation takes
effect. Failed mastering preserves the previously published audio. Failed
manifest publication restores the previous master. Existing mixer routes remain
registered alongside the restored console and diagnostics.

Production selects the required Qwen engine even when older configuration fields
still name Kokoro. Engine controls reject changes that violate required-engine
configuration. Switching/stopping Qwen is blocked while studio jobs are active.
Missing optional checkpoints are detected before stopping the current model.

## Runtime boundaries

- CustomVoice 1.7B and the pinned Qwen2.5 7B writer were reachable and used in real acceptance.
- Voice Clone/Base and VoiceDesign checkpoints are not installed locally. Their code and controls are restored; the UI reports their unavailability. No multi-gigabyte model download was performed.
- Branch clone-reference WAV files and Bryan's minted voice prompt are not present. Existing Phil/Jim voice assignments and references were not replaced with unavailable branch paths. Bryan cloning needs an actual approved voice profile.
- Voice Forge needs Coqui TTS and valid minted embeddings. Source recovery does not establish its runtime readiness, and required Qwen prevents substituting it into production.
- Existing machine-local writer/speech endpoints, external GPU launchers, and voice assignments were preserved. The missing theme path in `config/config.json` was repaired to the restored canonical `asset_library/sfx/introclip.mp3`; its intro/outro audio-library pointers were repaired as well. Original configuration remains in the recovery snapshot. Saved clip durations remain authoritative. Alternate Qwen launchers now resolve the configured interpreter and cached models instead of obsolete R-drive paths.
- Assembly Board exports are operator assembly plans; they do not prove an Audacity import or external editing session.
- OBS, mixer hardware, cameras, full-length duration acceptance and human voice approval remain hardware/operator acceptance tasks.

## Validation

- Backend regression and integration suite: 50 tests, including canonical version concurrency, immutable approved data, stale approvals, short approved production, cancellation, active-job guards, required Qwen and preserving previous audio.
- Restored ad contracts: 18 tests, including exact-copy/voice/asset contracts and real FFmpeg audio fixtures.
- Restored visual ad contracts: 3 tests, including actual rendered dimensions, timing, visual layers and sound.
- Backend Ruff checks, Python compilation, frontend ESLint and production Vite build.
- `scripts/verify_consolidation_ui.py`: intercepted browser checks preserve section rewrite, tone controls, progress, engine statistics, failure recovery and persisted-job reuse.
- `scripts/verify_branch_ui.py`: eight restored screens, zero JavaScript page errors; screenshots under `archive/testing/results/branch-ui/`.
- `scripts/verify_branch_runtime.py`: opt-in real pinned-writer → canonical script → Preview → approved production → Qwen takes → FFmpeg master → social exports. Uses isolated records under `archive/testing/results/`, never operator episodes.

Real sample: `archive/testing/results/branch-runtime-20261026_182928/`.
The writer generated 94 words in four turns. The master was 45.19 seconds,
with four Qwen takes, -16.00 LUFS, -3.31 dB true peak, and compliant mastering.
Audiogram, short video/audio clips, thumbnail and copy were generated.
A real single-line revision also passed: take 2 replaced only the chosen line,
all other take records and hashes remained unchanged, and QC passed. Evidence is
in `revision-acceptance.json` beside the sample.

The bounded sample disables intro/outro and optional SFX in its isolated fixture
configuration. A separate real wrapper check then added the saved intro/outro
with Qwen narration and the restored theme, and mastered the combined output to
-16.00 LUFS / -4.54 dB true peak. See `wrapper-acceptance.json` and
`wrapped-mastered-acceptance.mp3`. The worker now verifies loudness after wrapping
as well as before it. These checks do not claim acceptance of a complete long
show or human approval of the voices.

## Running this copy

The pre-existing studio at API port 8110 / UI port 5188 belongs to
`C:\Users\bryan\Desktop\Dandy`. It was left alone.
This folder's API uses 8112; its integrated frontend uses 15173.

```powershell
.\scripts\start_dandy_stack.ps1 -BackendPort 8112 -FrontendPort 15173 -NoQwen
```

Use `-Restart` to reload this folder's supported processes after code changes.
Process-ownership checks reject stopping services belonging to another folder.
`-NoQwen` reuses the existing shared speech service. No external shared service
restart is needed to load frontend/backend changes.

All integration changes remain local for review. The restoration ZIP and Git
bundle preserve the starting state independently of the working tree.
