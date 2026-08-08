# Dandy Studio — Dependency Map

_Generated: 2026-04-16 15:09_

## Python Packages

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.135.3 | Web framework — REST API |
| `uvicorn` | 0.44.0 | ASGI server — runs FastAPI |
| `pydantic` | 2.13.1 | Data validation and schemas |
| `python-multipart` | 0.0.26 | File upload support |
| `pillow` | 12.2.0 | Image rendering — slideshow frames, ad cards |
| `ffmpeg-python` | 0.2.0 | FFmpeg bindings — audio/video processing |
| `pydub` | 0.25.1 | Audio segment manipulation |
| `edge-tts` | 7.2.8 | Cloud TTS fallback (Microsoft Edge voices) |
| `torch` | 2.11.0 | PyTorch — Kokoro TTS inference engine |
| `torchaudio` | 2.11.0 | Audio tensor operations for Kokoro |
| `numpy` | 2.4.4 | Numerical operations — audio processing |
| `networkx` | 3.6.1 | Graph utilities — production dependency tracking |
| `sentence-transformers` | 5.4.1 | Semantic similarity — script analysis |
| `voicemeeter-api` | 2.7.2 | Voicemeeter real-time mixer integration |

## Node / Frontend Packages

| Package | Version | Purpose |
|---|---|---|
| `react` | 18.3.1 | UI framework |
| `react-dom` | 18.3.1 | React DOM renderer |
| `vite` | 8.0.3 | Frontend build tool / dev server |
| `@vitejs/plugin-react` | 4.7.0 | Vite React plugin |
| `tailwindcss` | 3.4.19 | Utility CSS framework |
| `lucide-react` | 0.383.0 | Icon library |

## External Services

| Service | Purpose | Status |
|---|---|---|
| FFmpeg | Audio/video encoding — must be on PATH | Required |
| OBS Studio | Live stream / recording control via WebSocket | Optional — Studio tab |
| Voicemeeter | Real-time audio mixer | Optional — Studio tab |
| Kokoro TTS | Local neural TTS engine (primary voice) | Required for TTS |
| CUDA / GPU | Accelerates Kokoro inference | Optional — falls back to CPU |

## Internal Module Map

| Module | Responsibility |
|---|---|
| `backend/app/api/production.py` ✓ | Episode produce endpoint |
| `backend/app/api/social.py` ✓ | Legacy social export endpoints |
| `backend/app/api/social_slideshow.py` ✓ | Slideshow CRUD + render endpoints |
| `backend/app/api/social_adcards.py` ✓ | Ad card CRUD + render endpoints |
| `backend/app/api/ads.py` ✓ | Ad script generation endpoints |
| `backend/app/api/assets.py` ✓ | Episode asset upload/management |
| `backend/app/api/mixer.py` ✓ | Voicemeeter mixer proxy |
| `backend/app/api/obs.py` ✓ | OBS WebSocket proxy |
| `backend/app/services/production/worker.py` ✓ | TTS synthesis + audio post-processing |
| `backend/app/services/production/dandy_harmonizer.py` ✓ | Script generation (Phil/Jim AI engine) |
| `backend/app/services/production/personality_loader.py` ✓ | Voice/personality config loader |
| `backend/app/services/social/slideshow_renderer.py` ✓ | Pillow + FFmpeg slide renderer |
| `backend/app/services/social/thumbnail_generator.py` ✓ | Thumbnail image generator |
| `backend/app/services/social/audiogram_generator.py` ✓ | Animated audiogram generator |
| `backend/app/schemas/social_visual.py` ✓ | Pydantic models: Slide, AdCard, Slideshow |
| `backend/app/core/paths.py` ✓ | Project path constants |

## Data Flow

```
Episode config + topic
    → dandy_harmonizer.py  (script generation)
    → worker.py            (TTS synthesis per line)
    → audio_post_processor (normalize, compress, encode)
    → audio.mp3            (final episode)
    → slideshow_renderer   (visual slides from script)
    → social exports       (audiogram, thumbnail, quote card)
```

## Audio Jingle Slots

| Slot | File | Status |
|---|---|---|
| `intro` | `audio/jingles/intro_outro.mp3` | present |
| `outro` | `audio/jingles/intro_outro.mp3` | present |
| `bumper_in` | `audio/jingles/bumper_in.mp3` | missing |
| `bumper_out` | `audio/jingles/bumper_out.mp3` | missing |
| `bed_loop` | `audio/jingles/bed_loop.mp3` | missing |
