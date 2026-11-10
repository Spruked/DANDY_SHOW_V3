# Advertising Slot Architecture — Post-First-Episode Handoff

Status: Design handoff only. Do not implement during the first episode build.

## Non-negotiable distinction

Dandy must model these as separate records:

1. An **advertising slot**: a reserved position in the episode timeline.
2. An **advertisement**: the commercial audio/script assigned to that position.

An episode must be buildable, editable, previewable, and renderable while one or more slots are empty. Publishing is the gate that requires every scheduled slot to contain an approved advertisement.

## Required seven-slot standard

Every published episode must contain these seven scheduled slots:

1. Pre-roll 1
2. Pre-roll 2
3. Mid-roll 1
4. Mid-roll 2
5. Mid-roll 3
6. Mid-roll 4
7. Post-roll 1

The four mid-rolls should be separate interruptions by default. Pre-roll and post-roll positions must be visible even when they are empty.

## Slot states

Each slot needs these states:

- **Empty / Reserved** — the slot exists in the episode plan, but no ad is assigned. The episode may continue through editorial work and rendering.
- **Generate Ad** — opens the ad-writing workflow for that slot.
- **Assigned / Replaceable** — an approved ad is assigned and can later be replaced without regenerating Phil and Jim’s dialogue.

The UI should make `RESERVE SLOT`, `GENERATE AD`, `ASSIGN EXISTING AD`, and `REPLACE AD` distinct actions.

## Where future ad information belongs

The Ads workspace should have a slot-first area for the active episode. Selecting a slot should expose:

- Sponsor / advertiser name
- Product or offer
- Campaign name and version
- Required claims and prohibited claims
- Call to action and destination
- Tone, announcer/host voice, and target duration
- Script brief or pasted copy
- Uploaded source files: PDF, DOCX, TXT/Markdown, image, audio, or approved finished ad audio
- Approval status and notes

The existing ad generator should remain available from the selected slot. It should consume the slot’s brief and source files, then save an advertisement record that can be assigned to the slot.

## Swap-safe episode architecture

The episode master must preserve host dialogue separately from advertising audio. A slot assignment should be replaceable without regenerating Phil or Jim.

The audio assembly layer must rebuild only the affected slot and final mix while preserving:

- Host dialogue and timing metadata
- Slot order and break boundaries
- Fades and host-to-ad transitions
- Loudness and peak normalization
- Captions or timing manifests that depend on the replaced ad

If an ad changes length, the assembler must update downstream timing rather than altering the host performance.

## Publishing gate

Publishing must fail clearly if any of the seven slots is empty, unapproved, missing audio, or has failed audio QC. Editorial rendering may proceed with reserved empty slots and must label those gaps in the preview/export metadata.

The publishing error should identify the exact slot, for example:

`Cannot publish: Mid-roll 3 is reserved but has no approved advertisement assigned.`

## Do not change during the first episode

Do not migrate the current episode, regenerate its script, insert automatic ads, or change its existing audio while this handoff is pending. Implement the slot model after the first episode is safely created and preserved.

## Suggested implementation order after the first episode

1. Add a persisted seven-slot schedule to each episode.
2. Add slot state and assignment APIs independent of advertisement records.
3. Add the slot-first Ads UI and source-file/context intake.
4. Add assign, unassign, and replace operations.
5. Separate host master audio from ad segments in the production manifest.
6. Add replacement-aware reassembly, fades, loudness, captions, and timing updates.
7. Add the publish gate requiring all seven approved ads.
8. Add tests proving that replacing an ad does not regenerate host dialogue.

## Acceptance criteria

- A new episode displays all seven slots before any ads exist.
- Empty slots do not block editorial work or preview rendering.
- A slot can receive generated, imported, or existing approved ad audio.
- An assigned ad can be replaced without changing Phil/Jim audio files.
- A replacement with a different duration updates the final mix and timing metadata.
- Publishing is blocked until all seven slots are filled, approved, and QC-passing.
- The current first-episode workflow remains unchanged until this feature is explicitly implemented.
