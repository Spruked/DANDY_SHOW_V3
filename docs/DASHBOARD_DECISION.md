# Dashboard Decision

## Current decision
- Preserve the control-rich dashboard approach.
- The active implementation is the React/Vite `frontend/` app.

## Why this dashboard wins
- It has the richest studio control set.
- It keeps production controls in one operator-focused UI:
  - script lifecycle and episode production
  - ad generation and insertion controls
  - social export actions and retrieval
  - OBS-only live controls in Studio tab; episode, ads, and social tabs remain the primary production workflow

## Merge rule
- We should preserve this dashboard's workflow and control density as much as possible.
- We should not redesign it heavily unless a change is needed to fit the new merged data model or FastAPI endpoints.
- The app should feel cleaned, wired, and deterministic rather than simplified.

## Current canonical files
- `frontend/src/App.jsx`
- `frontend/src/components/EpisodeTab.jsx`
- `frontend/src/components/AdTab.jsx`
- `frontend/src/components/SocialTab.jsx`
- `frontend/src/components/StudioTab.jsx`
- `frontend/src/components/SystemTab.jsx`
