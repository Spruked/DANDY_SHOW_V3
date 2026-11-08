"""Local vault snapshot, verification and restore-to-new-directory commands."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.storage.vault_store import DandyVault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'verify', 'status', 'restore'])
    parser.add_argument('--snapshot-id')
    parser.add_argument('--destination')
    args = parser.parse_args()
    vault = DandyVault()
    try:
        if args.action == 'snapshot':
            result = vault.capture(reason='operator command')
        elif args.action == 'verify':
            result = vault.verify()
        elif args.action == 'restore':
            if not args.snapshot_id or not args.destination:
                parser.error('restore requires --snapshot-id and --destination (a new directory)')
            result = vault.restore(args.snapshot_id, args.destination)
        else:
            result = vault.status()
        print(json.dumps(result, indent=2))
        return 1 if result.get('valid') is False else 0
    except Exception as exc:
        vault.record_error(exc)
        print(json.dumps({'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
