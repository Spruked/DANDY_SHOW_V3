# Context rebuild: current implementation and next stages

The producer-approved direction is source records → curation → exported context
→ external LLM → script import → Preview → approval → existing audio production.
The local writer is reserved for ads and short posts.

## Implemented

- Episode-generation routes retired and original writing code quarantined.
- Local TXT/Markdown/README, CSV/JSON/RST, body DOCX and text PDF extraction.
- Extractor registry and normalized source records; line ranges and Markdown
  headings; code reading with Python AST symbols and docstring locations.
- Google Docs intake through exported files or pasted text with original URL.
- Source hashes, page/paragraph references and versioned Markdown/JSON context.
- Source selection, producer brief, external-writer instructions and script import.
- Source analysis/excerpts, priority ordering, external-model context-window and
  output-reserve settings, live size planning and full-pack token estimates.
- Versioned owner direction, per-source owner notes, automatic new pack versions
  after saved direction changes, and protection against stale direction exports.
- Static SKG show-bible profiles with file/line/hash references, a plain-dialogue
  format contract and existing ad-slot settings, in the required pack order.
- Local image OCR with Tesseract: frame/pixel locations, confidence and machine
  transcription labels. No cloud calls or visual-description model.
- Vault artifact copies and AIMS receipts; automatic project snapshots and
  immediate preservation of key authoring/production artifacts.

## Remaining from the detailed design

1. Add exact tokenizer adapters if a specific external model is selected; current
   estimates are labelled heuristics. Add curated cross-source topic groupings
   and a structured import sidecar for scene/ad directives. The current contract
   supports plain speaker-labelled dialogue; scene/ad directives stay outside the
   spoken transcript and are configured separately in Studio.
2. Add scanned-PDF rasterization and OCR. Until then, export scanned pages to
   images. PDF table layouts require human checking; structured table extraction
   is not implemented.
3. Add local whisper.cpp transcription for audio and video speech with timestamps.
4. Add optional local vision descriptions, explicitly tagged machine-described.

OCR text is machine-transcribed evidence, not verified fact. Vision descriptions
must not be presented as extracted factual text. No future-stage capability is
claimed complete merely because its planned name appears here.
