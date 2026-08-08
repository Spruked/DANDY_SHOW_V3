# Dandy Studio User Manual

## 1. Runtime and entry points
- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8010`
- Backend health: `http://127.0.0.1:8010/health`
- Frontend source of truth: `frontend/src/`
- Backend API routes: `backend/app/api/`

## 2. Startup sequence
1. Start the backend:
```powershell
cd backend
$env:PATH="C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show\staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin;$env:PATH"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```
2. Start the frontend:
```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```
3. Open `http://127.0.0.1:5173`.

## 3. Top navigation bar
The top bar is present on every page.

### Left side
- `D` mark: visual logo only.

### Center tab buttons
- `EPISODES`: opens episode creation, script editing, production, export, assets, and feedback.
- `ADS`: opens ad generation, ad audio production, ad insertion, and ad asset upload.
- `SOCIAL`: opens social exports plus slideshow and ad-card builders.
- `STUDIO`: opens live mixer, OBS, camera, and macro controls.
- `SYSTEM`: opens health, voice, proxy, and quick command diagnostics.

### Right side backend indicator
- `checking...`: startup state while health probe is running.
- `:8010 online`: backend is reachable.
- `:8010 offline`: backend probe failed.

## 4. EPISODES page
This page has three columns: episode list, script workspace, and right-side utilities.

### Left column: Episodes
- `NEW`: opens the Create Episode modal.
- Refresh icon: reloads the episode list from the backend.
- Episode row: selects that episode and loads its script and attached assets.

Each episode row shows:
- episode id
- title
- target minutes if present
- status badge

### Center header buttons
- `GENERATE`: requests script generation for the selected episode.
- `PRODUCE`: queues full episode production.
- `EXPORT`: opens export format choices.
- `VERSIONS`: opens saved script versions.
- `FEEDBACK`: opens the customer feedback modal.
- `ASSETS`: opens the episode asset manager.
- `WS` / `WS ON`: connects the episode WebSocket log.

### Center stats strip
Read-only counters:
- `Lines`
- `Phil`
- `Jim`
- `Host`
- `Ads`
- `Assets`
- `Runtime`

### Script line behavior
Click any line once to select it. When selected, the line exposes action buttons.

Buttons shown for a selected line:
- Edit pencil: switches that line into edit mode.
- `Move up`: moves the line one position earlier.
- `Move down`: moves the line one position later.
- `Add after`: inserts a new line after the selected line.
- Delete trash icon: deletes the line after confirmation.
- Mic icon: opens Add Media Cue for that line.

### Script line edit mode
When a line is in edit mode:
- speaker dropdown: changes the speaker
- text area: edits the line text
- check icon: saves the edit
- `X`: cancels the edit

### Empty script state
If the selected episode has no script, the page shows:
- `Generate Script`: same action as `GENERATE`

### Right column: Audio
- embedded audio player: plays the rendered episode MP3 if it exists
- `DOWNLOAD MP3`: opens the final episode audio file directly

### Right column: Quick Add Line
- `Speaker` dropdown: speaker for the new line
- `Line` text area: line text
- `ADD LINE`: appends a new line to the script

### Create Episode modal
Opened by `NEW`.

Fields:
- `Episode ID`
- `Title`
- `Main Topic`
- `Description`
- `Key Points (one per line)`
- `Custom Instructions`
- `Target Length` slider from `30m` to `45m`

Buttons:
- `CANCEL`: closes the modal without creating
- `CREATE`: creates the episode

### Script Versions modal
Opened by `VERSIONS`.

Per version entry:
- version label
- timestamp
- line count
- `ROLLBACK`: restores that version after confirmation

### Episode Feedback modal
Opened by `FEEDBACK`.

Controls:
- feedback text area
- `CANCEL`
- `SUBMIT`

### Episode Assets modal
Opened by `ASSETS`.

Upload section controls:
- `Label`
- `Role` dropdown: `sfx`, `music`, `voice`, `image`, `document`
- `Description`
- `CHOOSE FILE & UPLOAD`: opens file picker and uploads the selected file

Attached asset rows:
- asset name
- role and description
- `OPEN`: opens the stored file

### Export Script modal
Opened by `EXPORT`.

Buttons:
- `Export as .JSON`
- `Export as .TXT`
- `Export as .SRT`

### Add Media Cue modal
Opened from the mic button on a selected line.

Fields:
- `Line Index`
- `Cue Type`: `sfx`, `music`, `voice`, `transition`
- `Asset`
- `Note`

Buttons:
- `CANCEL`
- `ADD CUE`

### WebSocket log
After pressing `WS`, the bottom of the script panel shows a `WebSocket Log` block.
This is read-only and displays recent socket events.

## 5. ADS page
This page has three columns: episode list, ad list, and presets.

### Left column
- episode row: selects the episode and loads its ads

### Center header
- `GENERATE AD`: opens the ad generation modal
- Refresh icon: reloads ads for the selected episode

### Ad cards
Click an ad card to expand or collapse it.

Collapsed ad cards show:
- title or ad type
- ad type badge
- status badge
- voice, tone, duration
- script preview

Expanded ad cards show these buttons and controls:
- `PRODUCE AUDIO`: generates audio for that ad
- `DOWNLOAD`: opens the produced ad audio file when present
- embedded audio player: previews produced ad audio
- `Insert Before Line` number field: target insert point in the episode script
- `INSERT INTO EPISODE`: inserts the ad into the script
- `Ad Asset Label`: label for a file you are about to upload
- `Upload File`: file picker field
- `UPLOAD ASSET`: uploads the selected ad asset file

Expanded ad asset rows:
- asset label / original name
- `OPEN`: opens the asset file

### Empty ad state
If an episode has no ads:
- `Generate First Ad`: opens the same generation modal

### Right column: Presets
- preset card: opens the Generate Ad modal

The preset cards currently act as quick entry points into the modal; they do not pre-apply a visible preset payload in the UI.

### Generate Ad modal
Opened by `GENERATE AD` or a preset card.

Fields:
- `Ad Type`
- `Voice`
- `Tone`
- `Duration` slider
- `Product / Show Name`
- `Tagline`
- `Call to Action`
- `Custom Script (optional — overrides generated)`

Buttons:
- `CANCEL`
- `GENERATE`

## 6. SOCIAL page
The Social page has three sub-pages across the top:
- `EXPORTS`
- `SLIDESHOW`
- `AD CARDS`

### 6.1 EXPORTS sub-page
This sub-page uses the same three-column layout as Episodes and Ads.

#### Left column
- episode row: selects the episode and loads existing social exports

#### Center header
- `GENERATE`: opens the social export modal
- Refresh icon: reloads the export list

#### Export cards
Each card can show:
- export type
- platform badge
- status badge
- aspect ratio
- asset slot
- created time
- preview image when available
- `DOWNLOAD`: downloads the generated export file when present

#### Right column: Asset Slots
Read-only slot descriptions:
- `Thumbnail Base`
- `Waveform Base`
- `Alternate Cover`
- `Character Logo`
- `Tech Talk Card`
- `Logo Mark`

#### Right column: Presets
- preset card: toggles selection highlight only

The selected preset state is visual only in the current UI. The generate modal does not auto-fill from that selection.

#### Generate Social Export modal
Fields:
- `Export Type`
- `Platform`
- `Aspect Ratio`
- `Asset Slot`
- `Clip Start (seconds)`
- `Clip Duration (seconds)`
- `Quote Text`
- `Show waveform animation` checkbox

Buttons:
- `CANCEL`
- `GENERATE`

### 6.2 SLIDESHOW sub-page
When you switch to `SLIDESHOW`, an `EPISODE` dropdown appears above the builder.

#### Episode selector
- episode dropdown: selects which episode slideshow deck is loaded

#### Left panel: slide list
- `+`: adds a blank slide
- slide row: selects a slide
- `▲`: moves the slide up
- `▼`: moves the slide down
- `Duplicate`: duplicates the selected slide
- `Delete`: deletes the selected slide
- `Auto-generate from script`: asks the backend to build a slide deck from the episode script

#### Center panel: preview and editor
Preview behavior:
- live preview updates as you edit
- aspect ratio changes with the export selector on the right
- background image changes from the selected asset slot image

Editable fields:
- `Title`
- `Subtitle`
- `Body`
- `Background` dropdown
- `Font size`
- `Align`
- `Color`
- `Animation`

#### Right panel: timing
For the selected slide:
- `Start (s)`
- `End (s)`
- duration readout
- `Snap to script`: requests backend timing for the slide and updates start/end

#### Right panel: export
- `Aspect`: `16:9`, `1:1`, `9:16`
- `Format`: `MP4 Video` or `PNG Carousel`
- `Save`: saves the deck; changes to `Saved ✓` when there is no unsaved state
- `Render`: renders the slideshow and opens the download URL if returned

### 6.3 AD CARDS sub-page
When you switch to `AD CARDS`, the same `EPISODE` dropdown appears above the builder.

#### Episode selector
- episode dropdown: selects which episode ad-card set is loaded

#### Left panel: template gallery
Each template button creates a new card of that type:
- `Sponsor Card`
- `CTA Card`
- `Product Teaser`
- `Brought to you by...`
- `End-Roll`
- `QR Code`
- `TrueMark Mint Promo`
- `GOAT Promo`
- `ORB Promo`

#### Left panel: card list
- card row: selects an existing card

#### Center panel: preview and editor
Editable fields:
- `Sponsor`
- `CTA text`
- `URL`
- `Offer code`
- `Background` dropdown
- `Logo overlay` dropdown

The preview updates live from these fields.

#### Right panel: export
- `Aspect`: `1:1`, `9:16`, `16:9`
- `Format`: `PNG (static)` or `MP4 (animated)`
- `Save`: saves all current cards
- `Delete`: deletes the selected card
- `Render`: renders the selected card and opens the output if returned

## 7. STUDIO page
This page is a live control surface with a top status strip and four sub-views:
- `AUDIO MIX`
- `OBS LIVE`
- `CAMERAS`
- `MACROS / TOOLS`

### Top status strip
Read-only status pills:
- `VOICEMEETER ...`
- `OBS WS`
- `AUDIO I/O`
- `LIVE ...` or `OFF AIR`
- `REC` or `IDLE`

Buttons:
- `REFRESH MIXER`: refreshes mixer state from backend
- `REFRESH OBS`: refreshes OBS status and scene list
- `GO LIVE` / `END STREAM`: toggles OBS streaming
- `RECORD` / `STOP REC`: toggles OBS recording

Error text may appear inline for mixer, OBS, or macro failures.

### View buttons
- `AUDIO MIX`: opens the audio routing and monitoring view
- `OBS LIVE`: opens OBS scene and stream status view
- `CAMERAS`: opens simulated PTZ controls
- `MACROS / TOOLS`: opens macro triggers and copied health commands

### 7.1 AUDIO MIX view
This view contains three major sections.

#### Section header behavior
Every section title bar is a button.
- Clicking the section title toggles collapse/expand.

#### VOICEMEETER - CHANNEL MIXER
For each channel strip (`MIC 1 · PHIL`, `MIC 2 · JIM`, `GUEST MIC`, `MUSIC BED`, `SFX`, `VOICEMEETER`):
- vertical fader: sets gain
- `EQ` toggle
- `MUTE` button
- `SOLO` button
- route toggles `A1`, `A2`, `B1`, `B2`
- gate knob / value readout
- comp knob / value readout
- VU meter

Master strip controls:
- master fader
- master VU meter
- `LIM` toggle
- `MUTE ALL`

#### MONITORING & HEADPHONES
Monitor controls:
- `VOLUME` knob
- `REVERB` knob
- `DIM` toggle
- `MONO` toggle
- `TALKBACK` toggle
- `CLICK` toggle
- `CLICK LVL` slider, visible only when `CLICK` is on

Headphone controls:
- `PHIL HP` slider
- `JIM HP` slider

#### AUDACITY - RECORDING CHAIN
Knobs:
- `INPUT GAIN`
- `NOISE REDUC`
- `COMP`
- `EQ`
- `DE-ESS`
- `LIMIT`

Button:
- `RECORD` / `STOP`

The chain labels below the button are read-only notes.

### 7.2 OBS LIVE view
This view contains three sections.

#### OBS - SCENE SWITCHER
- scene button: makes that scene active
- transition buttons: `Cut`, `Fade`, `Swipe`, `Stinger`
- `VIRTUAL CAM (SIM)` toggle

#### OBS - AUDIO SOURCES
Read-only source meters:
- `MIC PHIL`
- `MIC JIM`
- `MUSIC BED`
- `SFX`
- `MASTER OUT`

#### STREAM STATUS
Read-only fields:
- `PLATFORM`
- `STATUS`
- `OBS WS`
- `DURATION`
- `BITRATE`
- `FPS`
- `RESOLUTION`

### 7.3 CAMERAS view
This view contains the `PTZ CAMERAS` section.

For each camera card (`MAIN`, `PHIL`, `JIM`, `SCRN`):
- camera toggle: makes that camera active
- `ZOOM` slider
- `FOCUS` slider
- `EXPOSURE` slider

If OBS is connected and a matching scene exists, activating a camera also attempts to switch the scene.

### 7.4 MACROS / TOOLS view
This view contains two sections.

#### MACRO BUTTONS
Buttons:
- `INTRO SEQUENCE`
- `AD BREAK`
- `MUSIC BED ON`
- `MUSIC BED OFF`
- `BRB SCREEN`
- `GO LIVE`
- `START RECORD`
- `OUTRO SEQUENCE`

These buttons trigger the mapped Voicemeeter macro index and, for some macros, additional OBS or music actions.

#### QUICK HEALTH COMMANDS
Each command tile copies a command to the clipboard when clicked.

Tiles:
- `Backend health`
- `Voice list`
- `OBS WebSocket check`
- `Voicemeeter API`
- `Audio device list`
- `ffprobe audio`
- `Produce offline`
- `Stream Deck check`

## 8. SYSTEM page
This page is a diagnostic dashboard.

### Top header
- Refresh icon: reruns backend health and voice discovery

### Backend Health card
Displays:
- online/offline state
- any additional backend health fields returned by the API
- backend error text if the probe fails

### Network / Proxies card
Read-only connection references:
- Backend API
- Vite Dev Server
- WebSocket

### TTS Voice Engines card
Read-only voice inventory blocks for:
- Phil
- Jim
- Announcer (Male)
- Announcer (Female)
- Edge Backup

Badges and text indicate engine, role, and whether the voice is currently registered.

### Hardware card
Read-only system notes:
- GPU label
- Kokoro runtime note
- checkpoint path
- ffmpeg path
- Edge TTS fallback note

### Production Notes card
Read-only operator notes:
- offline runner command
- log file path
- target duration note
- demo audio path
- Kokoro timing note

### Quick Health Check Commands card
Each command string is clickable and copies itself to the clipboard.

Commands:
- `curl http://127.0.0.1:8010/health`
- `curl http://127.0.0.1:8010/api/voices`
- `ffprobe episodes/demo_podcast_gen/audio.mp3`
- `python staging/produce_demo.py`

## 9. Recommended front-to-back operator flow
1. Start backend and frontend.
2. Confirm `:8010 online` in the top nav.
3. Open `SYSTEM` and verify backend health plus voice inventory.
4. Open `EPISODES`, create or select an episode.
5. Generate the script.
6. Edit lines, add cues, upload assets, and submit feedback if needed.
7. Open `ADS`, generate ad reads, produce ad audio, and insert ads into the episode.
8. Return to `EPISODES` and run `PRODUCE`.
9. Open `SOCIAL` and generate exports, slideshows, or ad cards.
10. Use `STUDIO` for live mixer, OBS, macro, and camera control.

## 10. Source references
- `frontend/src/App.jsx`
- `frontend/src/components/EpisodeTab.jsx`
- `frontend/src/components/AdTab.jsx`
- `frontend/src/components/SocialTab.jsx`
- `frontend/src/components/ExportsMode.jsx`
- `frontend/src/components/SlideshowBuilder.jsx`
- `frontend/src/components/AdCardsBuilder.jsx`
- `frontend/src/components/StudioTab.jsx`
- `frontend/src/components/SystemTab.jsx`
- `frontend/src/lib/api.js`
