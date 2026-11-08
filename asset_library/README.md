# Dandy Reusable Asset Library

Drop reusable production assets anywhere under this folder. Dandy indexes the files dynamically and exposes them through the Episodes **ASSETS** button and Media Cue selector.

Recommended folders:

- `asset_library/sfx/` — sound effects
- `asset_library/jingles/` — bumpers, stings, transitions
- `asset_library/ads/` — reusable ad audio
- `asset_library/music/` — music beds and themes
- `asset_library/voice/` — prerecorded voice clips
- `asset_library/images/` — reusable images
- `asset_library/documents/` — reusable source/reference documents
- `asset_library/misc/` — anything else

Existing canonical repo folders are indexed too: `audio/sfx/`, `audio/jingles/`, `audio/ads/`, `social/assets/`, and `social/templates/`.

The catalog stores no duplicate media. Asset IDs are derived from repo-relative paths, so files remain callable from the UI without copying them into each episode.
