# Endpoint Wiring Audit

Date: 2026-11-10
Scope: every `.js`/`.jsx` file under `frontend/src` against the live FastAPI app.

## Method
- Backend routes and methods come from the app's own OpenAPI table (`create_app().openapi()`), so router
  prefixes, `/api` aliases and decorator quoting style cannot cause false reports.
- Frontend calls are collected from `req(...)`, `fetch('/api/...')`, `mixerRequest(...)` and `obsRequest(...)`.
  The stated method (`{ method: 'POST' }`) is checked; calls without one are treated as GET.
- `${...}` in a frontend path matches one or more segments; `{param}` in a backend route matches one segment.

## Result
- Backend paths: `233`
- Frontend calls checked: `112`
- Calls with no route or the wrong method: `0`

The previous version of the script read only `api.js` and `StudioTab.jsx`, recognised double-quoted route
decorators only and normalised a fixed list of parameter names, so it reported 14 working routes as missing.

## Validation command
```powershell
.venv\Scripts\python.exe scripts\audit_endpoints.py
```
Exit code 1 lists each unmatched call with its file and line.
