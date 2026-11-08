# Dandy Vault and AIMS safekeeping

The studio preserves artifacts in two local locations:

- `Dandy_Vault_System/storage/dandy/objects`: content-addressed copies of files.
- `Dandy_Vault_System/AIMS/data/dandy/dandy_artifacts.ledger`: append-only AIMS
  receipts containing file paths, sizes and hashes for each snapshot.

Working copies remain at their existing paths. Previous snapshots are retained;
changing or deleting a working file does not delete its preserved versions.
Restore copies a selected snapshot to a **new directory** and refuses to overwrite
an existing directory. Corrupt objects or ledger records stop verification/restore.

`config/vault.json` declares the snapshot scope and storage locations. It covers
episodes (sources, context, scripts, previews, drafts, approvals, takes and audio),
the shared asset library, audio and social folders, configuration, project source
and documentation, the quarantined writer, Vault/AIMS source, and `frontend/ORBS`.
It excludes repository metadata, dependencies, caches, environment/key files,
build output, temporary locks, and the vault's own generated data. Old restore
archives, external services and model installations are not project snapshots.

On normal studio startup a background watcher captures a project snapshot, then
checks for changes every 30 seconds. Source uploads, context packages, canonical
scripts, production review/approval files, and completed episode audio/exports
also receive immediate preservation. A failed immediate preservation leaves the
working file intact, reports an error, and does not claim vault success. Ad/social
edits and other project changes enter the next automatic snapshot. Automatic
capture runs only while the studio backend is running; use Snapshot Now before
shutdown when immediate capture is needed. Snapshots verify each file's stability
during copying; they are not a transactional filesystem freeze of all files.

The global **VAULT / AIMS** strip shows status and provides Snapshot Now and Verify.
`status.json` is only a UI projection; AIMS ledger receipts are the authority.

## Commands

From the project root, using the studio environment:

```powershell
.\.venv\Scripts\python.exe scripts/dandy_vault.py snapshot
.\.venv\Scripts\python.exe scripts/dandy_vault.py verify
.\.venv\Scripts\python.exe scripts/dandy_vault.py status
.\.venv\Scripts\python.exe scripts/dandy_vault.py restore --snapshot-id RECEIPT_ID --destination C:\Dandy-Restored-New
```

The host imports the supplied AIMS package locally (`pip install -e
./Dandy_Vault_System/AIMS`); it does not run a second web service or change ports.
The existing three copied component folders belong to the main repository, with
no nested `.git` directories. No Git metadata recovery copies are retained.

This uses AIMS v0.2.0's local `visual` SHA256-chain mode, not authenticated mode or
a claimed production-grade memory system. No secret keys or external services
are required. These are local preservation copies on the same drive. Independent
backup of both the objects and AIMS data directories is still needed to survive
drive loss. Full-history verification checks all referenced objects; it does not
claim protection against an attacker replacing an entire unauthenticated chain.
