# Orb Handoff Context (2026-04-05)

## Scope
This note is for the external Orb desktop codebase at:

- `R:\Orb_Assistant_Desktop`

Current app repo (Dandy show) is separate:

- `C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show`

## What was changed already

1. Enabled multi-monitor mode in local Orb profile:
- File: `R:\Orb_Assistant_Desktop\orb-instance.local.ps1`
- Change:
  - `ORB_PRIMARY_DISPLAY_ONLY="1"` -> `ORB_PRIMARY_DISPLAY_ONLY="0"`

2. Reworked cursor-to-window routing to use actual window bounds + nearest fallback:
- File: `R:\Orb_Assistant_Desktop\electron\main\main.js`
- Function changed: `broadcastCursorPosition(cursor)` (starts near line 322)
- Behavior:
  - Picks active window by cursor-in-bounds.
  - If cursor is between displays, chooses nearest Orb window.
  - Sends active/inactive position updates per window.

## Verified runtime shape

- Electron main process: 1
- Electron renderer processes: 3 (one per display)
- Electron GPU process: 1
- Python bridge: 1

This is one Orb instance with multiple display windows, not three separate full Orbs.

## Current user requirement (not yet implemented)

Dock behavior must be:

1. When `Dock Orb` is clicked:
- Orb desktop windows hide.
- Orb remains visible in Dock Station as a live preview/presence.
- Dock station controls must still update Orb state/skin.
- Orb remains bound in docked mode until manual undock.

2. When Orb is not docked:
- No Orb presence in Dock Station preview area.

## Relevant code locations

- Tray + dock toggle:
  - `R:\Orb_Assistant_Desktop\electron\main\main.js`
  - `updateTrayMenu()` near line 449
  - `openDockStationWindow()` near line 474
  - `showOrb()` near line 513
  - `hideOrb()` near line 531
  - verbal command route (`dock_orb`) near line 624

- Skin forwarding:
  - `forwardOrbSkin()` near line 632
  - includes dock station in targets when open

- Preload bridge:
  - `R:\Orb_Assistant_Desktop\electron\main\preload.js`
  - has `setOrbState`, `setOrbSkin`, `ingestOrbSkin`, and dock open APIs exposed

- Dock UI source:
  - `R:\Orb_Assistant_Desktop\electron\src\ui\orb-dock-station.jsx`
  - built file: `orb-dock-station.bundle.js`

## Next patch plan for new instance

1. Add explicit docked-state source of truth in main process:
- `let orbDocked = false;`
- Set `orbDocked=true` in dock action; `orbDocked=false` in launch/undock.
- Broadcast `orb:dock-state-changed` to dock window + orb windows.

2. Keep Dock Station preview alive while docked:
- In dock UI, render Orb preview only when `orbDocked=true`.
- Hide preview when `orbDocked=false`.

3. Keep settings/skin reactive in docked mode:
- Ensure dock UI subscribes to `orb:skin-updated` + state events.
- Ensure dock controls call `setOrbState` / `setOrbSkin` and refresh immediately.

4. Keep desktop Orb hidden during docked mode until manual undock.

## Quick relaunch commands (Orb repo shell)

```powershell
cd R:\Orb_Assistant_Desktop
.\stop_desktop_orb.ps1
.\launch_desktop_orb.ps1
```

## Ready-to-paste prompt for the other VS Code instance

```
Continue Orb desktop fixes in R:\Orb_Assistant_Desktop.
Current state:
- ORB_PRIMARY_DISPLAY_ONLY=0 in orb-instance.local.ps1
- broadcastCursorPosition() in electron/main/main.js uses window-bounds routing with nearest fallback
- Multi-monitor renderer topology is active

Implement dock UX contract:
1) Dock Orb => desktop orb hides, but Orb remains visibly present/live in Dock Station and stays bound there.
2) While docked, skin/state changes from Dock Station must apply live and be visible.
3) Undock manually => redeploy to desktop.
4) When not docked => no Orb presence in Dock Station preview.

Patch main.js + dock station UI (orb-dock-station.jsx) as needed, then rebuild bundle if required, restart Orb, and report exact files/lines changed.
```
