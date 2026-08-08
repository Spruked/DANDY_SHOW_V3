# Social Export Plan

## Purpose
Generate local social packages from produced episodes without external SaaS dependencies.

## Goals
- Export platform-ready images and videos from episode audio.
- Reuse one consistent Phil and Jim visual identity.
- Generate post copy, hashtags, CTA text, and sponsor disclosures automatically.
- Support fast recurring promo workflows for the Dandy studio.

## Current Structure

```text
social/
├── templates/
└── generated/                 # runtime output (git-ignored)

backend/app/services/social/
├── thumbnail_generator.py
├── audiogram_generator.py
├── post_copy_generator.py
└── package_builder.py

backend/app/api/social.py
├── POST /episodes/{episode_id}/social-package
├── POST /social/generate
├── GET  /social/presets
├── GET  /episodes/{episode_id}/social
└── GET  /social/{export_id}/download
```

## Outputs
- YouTube thumbnails
- Vertical audiograms for Shorts, Reels, and TikTok
- Square or landscape post assets
- Post copy text files
- Hashtag text files
- Final social package zip per episode

## Merge Rule
- Keep this as a layer on top of the audio-first studio.
- Do not let social export distort the core episode production pipeline.
- Keep exports deterministic from finished episode metadata/audio.

## Brand Default
- Social export now defaults to the locked `gold city sign` master brand.
- The `blue countryside title` art is the alternate scenic brand.
- The `vintage cream double-headphones` art is the main character/logo asset.
- `TECH TALK AND STUFF` is reserved for a segment override, not the main show identity.
