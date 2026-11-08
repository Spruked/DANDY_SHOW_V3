from fastapi import APIRouter, HTTPException
from ..services.storage.vault_store import DandyVault

router = APIRouter(tags=['vault'])


@router.get('/vault/status')
def vault_status():
    vault = DandyVault()
    return {**vault.status(), 'enabled': vault.config.get('enabled', True),
            'sync_interval_seconds': vault.config.get('sync_interval_seconds', 30),
            'vault_root': str(vault.root), 'aims_store': str(vault.aims),
            'aims_release': '0.2.0 functional prototype', 'security_mode': 'visual'}


@router.post('/vault/snapshot')
def vault_snapshot():
    vault = DandyVault()
    try:
        return vault.capture(reason='operator requested project snapshot')
    except Exception as exc:
        vault.record_error(exc)
        raise HTTPException(503, str(exc)) from exc


@router.post('/vault/verify')
def vault_verify():
    vault = DandyVault()
    try:
        return vault.verify()
    except Exception as exc:
        vault.record_error(exc)
        raise HTTPException(503, str(exc)) from exc
