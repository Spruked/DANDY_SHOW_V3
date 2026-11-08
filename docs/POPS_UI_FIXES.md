# POPS_UI_001 browser-test fixes

Read the original handoff at:
`C:\Users\bryan\Documents\Codex\2026-10-26\i-x20\outputs\dandy-ui-test\handoff.md`.

## Confirmed causes and changes

- The saved draft embedded the immutable Preview review without the API-only
  `saved` field. The editor preferred that object to the saved-review response,
  hid the handoff notes, and displayed Preview Required. `editor_state` now
  verifies the referenced review ID/hash and projects `saved: true` without
  changing the stored draft or review. Historical notes stay separate from
  delivery instructions; per-line notes also appear beside the production line.
- The model was constrained to a hard character grammar. This caused forced
  endings and decoding fragments. Dialogue requests now use a JSON schema with
  an exact line count and unrestricted natural text, followed by alternating
  speaker, sentence, fragment and token-limit checks. Invalid batches get bounded
  retries, and partial exchanges are never published as a finished script.
- Only opening/expansion stages were requested, and appended editorial/beat
  instructions were cut off by the persona excerpt limit. The compact prompt
  keeps the assignment separate from persona rules and explicitly schedules
  opening, development, reflection and closing. Exchange counts scale with the
  target word budget. Unsupported POPS mechanisms are rejected when absent from
  the supplied brief; conceptual examples remain distinct from product claims.
- Runtime estimates used 90, 155 and 160 words/minute in different places.
  Episodes and Production Editor now share a 160-WPM-plus-pauses estimator;
  storage metadata and default generation budgets use that same rate. Actual
  rendered duration still needs an audio probe. Approved production-copy pauses
  can legitimately differ from canonical pauses.
- Review panes now reserve their own sidebar space. At 958×903 the right sidebar
  moves below the main pane, the editor columns stack, and Preview marks/notes
  wrap into readable rows. The Send action is no longer covered.
- Approved is shown as an unfilled state until approval actually exists.
  Download MP3 is disabled and no audio player is loaded when audio is absent.
  Creation selects the new episode; the selected ID is remembered on reload.

## Preservation

Recovery snapshot:
`archive/restore_points/pops-ui-fixes-20261026_194144/before.zip`.

The original episode's JSON/script/review/draft files were hash-compared with
that snapshot and remain unchanged. `canonical_v0001`, `preview_v0001`, all 15
flagged line notes, the overall note, `draft_v0001` and all 40 pending
recommendations are preserved. No live approval, TTS rendering or export was
performed. The existing flawed dialogue has deliberately not been silently
rewritten.

## Validation and retest

- 59 backend tests pass, including saved-review projection, complete exchange
  validation, structured decoding, token-limit rejection and stage planning.
- Frontend production build and ESLint pass; backend Ruff and diff checks pass.
- `scripts/verify_pops_ui_fixes.py` uses the real browser UI at localhost:8112,
  checks the existing episode read-only, and verifies zero mutating requests.
  It confirms saved Preview, retained notes, enabled Open From Preview,
  still-gated approval, disabled MP3 download and responsive action placement.
  Screenshots are in `archive/testing/results/pops-ui-fixes/`.
- Isolated real-model generation passed with 36 alternating lines, 688 words,
  an explicit POPS/Proof of Presence show opening and a closing/sign-off.
  The existing quality guard returned ACCEPT. Evidence:
  `archive/testing/results/pops-generation-20261026_200300/script.json`.
  These QA scripts were never written into POPS_UI_001.

Refresh the browser and select POPS_UI_001. The existing draft can now display
its saved handoff, but it remains unapproved and its original dialogue remains
flawed. Regenerate into a new canonical version before continuing the audio
acceptance test; review that version in Preview and send its saved review into
a new editor draft. Review recommendations, save and approve only when the new
content is acceptable. Model output still requires operator editorial review.
