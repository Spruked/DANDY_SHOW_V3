# Endpoint Wiring Audit

Date: 2026-04-04
Scope: `frontend/src/lib/api.js` + `frontend/src/components/StudioTab.jsx` against `backend/app/api/*.py`

## Method
- Enumerate backend route decorators (`@router.get/post/put/patch/delete`)
- Expand backend compatibility routes (`/` and `/api` prefixes)
- Enumerate frontend request paths from `req(...)` and direct StudioTab `fetch('/api/mixer...')` / `fetch('/api/obs...')`
- Match dynamic URL segments by shape (`{episode_id}`, `{ad_id}`, etc.)

## Result
- Frontend routes checked: `31`
- Backend routes discovered (including `/api` aliases): `90`
- Unmatched frontend routes: `0`

## Validation command
```powershell
python scripts/audit_endpoints.py
```
