# Project Structure

Current layout after the 2026-11-10 cleanup. Runtime episode data is local and git-ignored.

## Repository root (active files only)
| File | Why it is at the root |
|---|---|
| `phil_dandy_skg.py`, `Jim_dandy_skg.py` | Active SKG modules; `config/voices.json` and the vault load them by root path |
| `shared_encoder.py` | Imported by both SKGs as a top-level module |
| `persona_canon.py` | Canonical persona loader; `authoring/pack.py` loads it from the project root |
| `worker.py`, `context_builder.py`, `quality_guard.py`, `script_expander.py`, `script_seed.py` | Two-line compatibility shims for `backend/app/services/production/*` (covered by `test_cleanup.py`) |
| `produce_direct.py` | Compatibility CLI for direct episode production |
| `README.md`, `CHANGELOG.md`, `pyproject.toml`, `requirements.txt`, `Dandy.code-workspace` | Project metadata |

Local, untracked runtime files also stay at the root: the voice samples `PHIL17SAMPLE.wav` and
`jimsample18.wav` (backed up by the vault by root path).

## Folders
```text
DANDY_SHOW_V3/
├── backend/app/
│   ├── api/                    # FastAPI routers (segments.py = three-segment authoring)
│   ├── core/  models/  schemas/  websockets/
│   └── services/
│       ├── authoring/          # context pack, owner direction, segment plan/drafts, review notes
│       ├── production/         # writer, duration budgets, worker, ads, intro/outro, editor
│       ├── ads/  audio/  mixer/  obs/  planning/  social/  storage/  tts/
├── backend/tests/              # unittest suite (scripts/test.py runs it)
├── frontend/src/               # React/Vite studio (components/SegmentsView.jsx = Segments tab)
├── config/                     # project, writer, voices, vault config; characters/ = canonical personas
├── episodes/                   # runtime episode data (git-ignored)
├── data/debug/                 # provider evidence (git-ignored; private editorial context)
├── docs/
│   ├── canon/                  # Phil/Jim character bibles (.docx, .pdf)
│   └── operations/
├── scripts/                    # start/stop, tests, UI verification, endpoint audit, probes
├── asset_library/  assets/  audio/  social/  brands/  campaigns/
├── Dandy_Vault_System/         # vault, AIMS ledger, memory archives
├── secondary_systems/          # Qwen TTS UI
├── voice_forge_2.0/            # standalone voice tooling
├── requirements/               # pinned dependency sets
└── archive/                    # nothing is deleted; superseded material lands here
    ├── root_cleanup_20261110/            # stale tree.txt, duplicate intro clip, old WSL worker variant
    ├── persona_skg_install_package_20261110/  # install package identical to the installed SKGs
    ├── legacy-python/  legacy-episode-writer/  cleanup/  testing/
```

## Checks
- `scripts/test.py` — backend test suite
- `scripts/audit_endpoints.py` — every frontend API call against live backend routes and methods
- `scripts/verify_context_ui.py` — Context Generator and Segments walkthrough with intercepted API calls
- `npm run lint` and `npm run build` in `frontend/`
