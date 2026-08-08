# Dandy Studio — Asset Drop Guide

Where to put everything. Drop files in the right folder and the system picks them up automatically.

---

## Brand Images → `social/templates/`

These are the show's visual identity. Used by the Slideshow Builder, Ad Cards Builder,
thumbnail generator, and audiogram generator.

| Filename | What it is | Used for |
|---|---|---|
| `thumbnail_base.png` | Gold city sign art | Default background for all social exports |
| `waveform_base.png` | Gold city sign (audiogram variant) | Audiogram background |
| `alternate_cover.png` | Blue countryside art | Alternate social rotation |
| `character_logo.png` | Vintage cream Phil/Jim headphones illustration | Promo cards, character moments |
| `segment_tech_talk.png` | Blue TECH TALK AND STUFF card | Tech segment overrides |
| `logo.png` | Simplified show mark | Overlay on slides and ad cards |
| `legacy_alt.png` | Beige two-face alternate | Archive/retro style |

### Current assigned files
- `social/templates/logo.png` <- `social/assets/phil_jim_podcast_logo_1.png`
- `social/templates/character_logo.png` <- `social/assets/phil_jim_podcast_logo_2.png`
- `social/templates/legacy_alt.png` <- `social/assets/phil_jim_podcast_logo_4.png`

**Recommended size:** 1920×1080 (16:9) for landscape, 1080×1920 for vertical (9:16), 1080×1080 for square.
**Format:** PNG with transparency where needed. JPG fine for solid backgrounds.

---

## Extra Social Images → `social/assets/`

Additional background images, sponsor logos, custom graphics for one-off slideshows
or ad cards. Not part of the locked brand system — drop anything here.

Examples: sponsor brand art, event graphics, seasonal covers, episode-specific backgrounds.

Current local image inventory includes:
- `phil_jim_podcast_logo_1.png`
- `phil_jim_podcast_logo_2.png`
- `phil_jim_podcast_logo_4.png`
- `Copilot_20251124_164628.png`
- `goat7logo.jpg`

---

## Audio Jingles → `audio/jingles/`

| Filename | Slot | Length |
|---|---|---|
| `intro_outro.mp3` | Intro + Outro (shared for now) | 15–30s |
| `bumper_in.mp3` | Going to break | 3–5s |
| `bumper_out.mp3` | Coming back from break | 3–5s |
| `bed_loop.mp3` | Background music under dialogue | 60–90s, must loop cleanly |
| `cold_open.mp3` | Single hit before first voice line | 1–2s |

---

## Sound Effects → `audio/sfx/`

Dropped here and then attached to script lines via the Media Cues panel in the Episodes tab.

Examples: `paper_rustle.mp3`, `phone_ring_distant.mp3`, `coffee_cup.mp3`,
`chair_creak.mp3`, `keyboard_click.mp3`, `studio_ambience.mp3`, `applause_short.mp3`

---

## Ad Beds → `audio/ads/`

Music loops that play under spoken ad reads.

Examples: `ad_bed_upbeat.mp3`, `ad_bed_soft.mp3`

---

## Fonts → `assets/fonts/`

Custom fonts for slide and ad card text rendering.
The renderer looks for `Inter-Bold.ttf` first, then falls back to system fonts.

Drop any `.ttf` or `.otf` file here and reference it by filename in the renderer config.

---

## Episode-Specific Assets → `episodes/{episode_id}/assets/`

Images, documents, source material that belongs to ONE episode.
Upload via the **Assets** panel in the Episodes tab — do not drop files here manually.

Examples: guest headshot, product image, source article PDF, sponsor logo for that episode.

---

## Quick Reference

```
social/
├── templates/        ← BRAND IMAGES (logo, backgrounds, character art)
├── assets/           ← OTHER IMAGES (sponsors, extras, one-offs)
└── renders/          ← OUTPUT ONLY — do not drop files here

audio/
├── jingles/          ← SHOW MUSIC (intro, outro, bumpers, bed)
├── sfx/              ← SOUND EFFECTS (cued to script lines)
└── ads/              ← AD BED MUSIC (loops under ad reads)

assets/
├── fonts/            ← CUSTOM FONTS (.ttf, .otf)
└── images/           ← MISC IMAGES (not brand, not episode-specific)

episodes/{id}/assets/ ← EPISODE ASSETS (upload via Episodes tab)
```
