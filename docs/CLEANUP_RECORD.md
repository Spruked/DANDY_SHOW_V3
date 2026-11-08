# Repository cleanup — 2026-10-26

## Preservation and file decisions

Before changes, checkpoint branch `checkpoint/pre-cleanup-20261026` records the
starting commit. A verified source snapshot is in
`archive/restore_points/repo-cleanup-20261026/`; its manifest records every tracked
file hash and local episode file hashes. The media archive labeled
`before-repo-cleanup` was restored and compared in an empty temporary directory.

| Files | Decision |
| --- | --- |
| Root worker/context/quality/expander/seed modules | Preserve originals in archive/legacy-python; retain root import compatibility wrappers delegating to backend implementations. |
| worker_original.py.bak | Move out of active backend into archive/legacy-python. |
| scripts/_regen_ep002.py | Move historical fixed-job script into archive/legacy-python. |
| introclip.mp3 | Keep canonical tracked intro. |
| introclipdandy222.mp3 | Identical hash; stop tracking while preserving the local file. |
| episodes/** | Preserve all local records; stop tracking runtime jobs/scripts/transcripts. Git history and verified backups retain earlier records. |
| Phil/Jim character modules, WSL helpers, clone/design tooling | Preserve; no unverified deletion of character or compatibility functionality. |

