# Production hardening repair record — 2026-10-26

Status: initial security/recovery repairs implemented; NOT production accepted.

## Repository and preservation

Verified origin fetch/push: https://github.com/Spruked/DANDY_SHOW_V3.git.
Checkpoint branch: checkpoint/pre-production-hardening-20261026 (7813208).
Existing episode draft changes were preserved. No commits pushed and no source
consolidation or database migration performed.

Media backup: archive/backups/backup_20261026_143454_532540_media-checkpoint.zip.
Restored into a temporary directory; all 81 ZIP members matched SHA-256 hashes.
This backup contains local configs, episode data, media and relevant package/docs
files. It is not a complete source checkout. Git provides the code checkpoint.
External voice prompts/model files outside the repository are not covered.
Backups must run while production/editing is idle for application-level consistency.
Separate-device/offsite backup and a scheduled backup policy remain operational work.

## Changes

- Restricted IDs, resolved-path containment for episode/job storage, social config,
  image references and media downloads. Invalid paths return client errors.
- JSON writes use a temporary file, flush/fsync and atomic replacement. Advisory
  locks protect storage writes, version allocation and selected episode updates.
  Multiple-file saves are not transactions; disk failure between related saves can
  still leave records requiring reconciliation.
- Default startup binds localhost. No network-user authentication was added;
  do not expose this studio through a public listener or proxy.
- One backend owns an OS runtime lock. Use one Uvicorn worker. Restart converts
  unfinished production into interrupted records, requiring explicit retry.
- One active episode production slot prevents simultaneous GPU episode jobs.
  This is not a durable queue or a global limiter for every preview/render/ad job.
- Required Qwen config fails closed if unavailable. Dialogue checks returned engine
  and configured voice and rejects empty output; Kokoro/Edge substitution is blocked.
  Intro/outro uses Qwen under the same requirement and propagates failures.
- Slideshow/ad-card render downloads are proxied through /renders.
- Asset uploads have a 100 MiB application limit; slideshow FFmpeg calls have deadlines.
- Backup includes media; new restore mode only restores into an empty destination,
  validates archive paths and integrity, and refuses symlinks. Legacy restore paths
  also receive containment checks.
- /api/ready reports dependency readiness separately from /health liveness.

## Validation

26 backend unit/contract tests pass (20 existing + 6 safety/backup tests).
Frontend production build passes, with existing plugin deprecation warnings.
Python compile checks and git diff --check pass.
Full actual backup restore verified independently in an empty temporary directory.
Tests use fake TTS/media for production orchestration; these are not voice acceptance.

## Remaining work before production acceptance

1. Reproducible environment: this venv runs Python 3.11.9 with system packages,
   while the earlier README specifies 3.12. Pin and validate a clean supported
   Windows environment and separate Qwen service environment. Direct requirements
   edge-tts, sentence-transformers, ffmpeg-python and voicemeeter-api have no installed
   distribution metadata here, despite pip check passing for installed packages.
   Do not copy this environment into a supposed validated lock file.
2. FFmpeg/FFprobe are absent from the current process PATH. Qwen bridge 8020 and
   writer services 5199/40343 have no local listeners at verification time.
   Restore/configure these dependencies before running a real production job.
3. Verify operator-approved Phil/Jim identity by listening to real Qwen output.
   Current config maps Phil=Ryan, Jim=Eric; this repair preserves those mappings.
   Returned voice labels are necessary bookkeeping, not proof of audible identity.
4. Run generate -> edit -> narrate -> mix -> export -> frontend download -> replay.
   Check transcript completeness, voice identity, timing, clipping/loudness and
   slideshow/ad-card files. Test an actual process interruption and explicit retry.
5. Add clean-install CI, production frontend hosting/supervision, resource limits
   for all expensive operations, and an off-disk scheduled backup/restore drill.
6. Atomic writes protect individual files; review remaining multi-record consistency
   and concurrent read-modify-write workflows before unattended operation.

No real narrated episode or hardware integration has been certified by this pass.


## Runtime restoration update — 2026-10-26

FFmpeg and FFprobe 9.0.2 are now installed in
`staging/ffmpeg/ffmpeg-9.0.2-essentials_build/bin`. The release archive came from
https://www.gyan.dev/ffmpeg/builds/ (linked by https://ffmpeg.org/download.html).
Its SHA-256 matched the provider checksum; source/hash/bin are recorded in
`staging/ffmpeg/installation.json`.

Both binaries run. A real one-second MP3 encoding, FFprobe inspection and complete
decode passed. The bin directory is saved in the Windows user PATH (open a new
terminal to inherit it). Dandy startup also reads the verified bin location from
ignored `config/runtime.local.json`.

The existing writer on http://127.0.0.1:16520/v1 answered a real inference request.
Dandy startup now reuses it through local runtime configuration; no writer was
installed or moved. The old ports in the initial record describe the prior check.

Qwen packages exist in the existing Python 3.11 installation. The complete cached
model is Qwen3-TTS-12Hz-0.6B-CustomVoice; the 1.7B model weights referenced by the
old launcher are absent. Model selection is awaiting the operator's answer; no
Qwen substitution or new model download has been performed. Voice and complete
production acceptance remain outstanding.

A source/data checkpoint before runtime changes is preserved at
`archive/restore_points/runtime-restoration-20261026/snapshot.zip` with a manifest.
No GitHub push was performed.

### System-wide FFmpeg installation

At the operator's request, FFmpeg/FFprobe/FFplay 9.0.2 are now installed under
`C:\Program Files\FFmpeg\9.0.2\bin`. Installed executable SHA-256 hashes matched
the previously verified archive extraction. The bin directory was added to the
Windows machine PATH; the earlier repository-specific user PATH entry was removed.
Dandy local runtime configuration now points to the system installation.
A fresh MP3 encode, probe and decode using the system binaries passed.
Restart terminals/IDE processes to inherit the updated machine environment.
