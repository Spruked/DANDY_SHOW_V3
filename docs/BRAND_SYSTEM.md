# Brand System

## Locked Roles
- `Primary Master Brand`: gold city sign logo art
- `Alternate Cover`: blue countryside title art
- `Character Logo`: vintage cream double-headphones illustration
- `Segment Card`: blue `TECH TALK AND STUFF` card
- `Optional Legacy Alternate`: beige two-face podcast illustration

## Current Brand Decision
The project now has one main official look and a few controlled alternates.

### 1. Main Official Brand
- Use the `gold city sign` art as the main show identity.
- This is the best fit for:
  - dashboard header branding
  - show cover
  - promo overlays
  - social export identity
  - thumbnail style direction

### 2. Alternate Scenic Brand
- Use the `blue countryside title` art as the alternate scenic version.
- Best for:
  - occasional social rotation
  - softer episode artwork
  - scenic promos

### 3. Character / Illustration Brand
- Use the `vintage cream double-headphones` art as the main illustrated Phil/Jim mark.
- Best for:
  - promo cards
  - profile graphics
  - merch-style visuals
  - brand personality moments
  - active speaker indicators in the dashboard

### 4. Segment Brand
- Use the `TECH TALK AND STUFF` blue card only for a segment or recurring content lane.
- Do not use it as the main show cover.

### 5. Lower Priority Alternate
- The beige two-face illustration is kept as optional backup art only.
- It is not the primary illustrated identity.
- It works better as a retro or archival mood layer than as the main show mark.

## Implementation Rule
- Keep one official master brand for the show.
- Rotate alternates intentionally, not randomly.
- Social exports should default to the master brand unless a segment preset overrides it.
- The dashboard should visually lean toward the master brand first.
- Persona art should support the hosts, not replace the master brand.

## Automation Lanes
- `main_machine_hud`
  - default dashboard and command mode
  - uses the gold city master brand
- `market_updates`
  - sheep, sales, Katahdin, market, and product spotlight content
  - uses the blue countryside alternate
- `tech_dev_sessions`
  - RTX, 3050, Python, Merge, React, FastAPI, and coding topics
  - uses the blue `TECH TALK AND STUFF` segment card
- `character_banter`
  - Phil/Jim personality-led clips and speaker moments
  - uses the illustrated character/logo assets
- `deep_dive_archive`
  - long-form, compilation, best-of, or archival content
  - uses the warmer retro cream style

## Asset Slot Mapping
- `social/templates/logo.png`
  - main brand mark derived from the primary master brand
- `social/templates/thumbnail_base.png`
  - primary thumbnail background using the gold city sign style
- `social/templates/waveform_base.png`
  - primary audiogram background using the gold city sign style
- `social/templates/alternate_cover.png`
  - blue countryside alternate
- `social/templates/character_logo.png`
  - vintage cream double-headphones illustration
- `social/templates/segment_tech_talk.png`
  - tech segment card
- `social/templates/legacy_alt.png`
  - beige two-face backup illustration

## Design Direction
- Primary palette: dark charcoal, gold, warm amber
- Secondary palette: blue and countryside scenic tones
- Character palette: cream, muted green, warm gold
- Segment palette: strong blue, white, gold
