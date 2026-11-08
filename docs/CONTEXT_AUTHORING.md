# Document context → external script → production

Episode authoring starts in the main **CONTEXT GENERATOR & EDITOR** tab (`/studio#context`).
Choose or create an episode on the left. The Context Generator & Editor has
separate Direction, Sources, Brief, Show Bible, Source Facts, Format, Ad Slots,
Build & Export, and Short Copy tabs. Only the selected section is shown; section
navigation stays visible while a long individual section scrolls. Input values
remain in place when switching sections. Upload sources, select the
documents to include, add an editorial brief, and build a context package. Download
Markdown for the external writer or JSON for tools. Packages include complete
extracted text, source identifiers, SHA256 hashes, page/paragraph references,
episode configuration, writer instructions and extraction limitations. They do
not generate dialogue or independently verify claims.

Give the package to your chosen external LLM. Return the finished script through
**Import Finished Script**, by pasting or loading a TXT/Markdown file. Use one
`PHIL: ...` or `JIM: ...` turn per line. Keep citations and producer notes outside
the dialogue. Import creates a canonical version. Continue through Preview,
Production Editor, explicit approval and audio production. Existing versions,
episodes, notes, approvals, takes and master audio are preserved.

## Manual Direction

The Direction tab records episode direction, angle/tone, must-include points,
must-avoid material and segment notes. Each file in Sources also has an owner-note field.
These are tagged `owner_direction` in the manifest and kept separate from source
evidence. They set editorial priority; factual conflicts must be disclosed to the
owner rather than silently rewriting evidence or inventing support.

Use **Save Owner Direction** even before adding files. Once a pack exists,
saving changed direction automatically creates a new pack version using that
pack's existing source evidence. It does not repeat extraction or modify an older
pack. Build Context Package applies new source selections or source changes.
Unsaved direction prevents export of a stale pack. Concurrent direction saves
are checked against the revision that was loaded and cannot silently overwrite
another saved revision.

Direction history lives in `context_packages/direction_versions/`, with its current
projection in `direction.json`. Each context manifest embeds the full direction
and revision. Direction versions and context versions are preserved in the Vault.

Pack order is owner direction → episode brief → show bible → source facts →
format contract → ad slots. The show bible reads static `CORE_PERSONALITY` values
from the configured Phil/Jim SKG source files using Python AST/literal parsing;
it does not execute the personality engines. File hashes and line locations are
included. Ad slots reflect the episode's configured ads/settings. No configured
slots means no invented breaks. The transcript contract keeps ads, scene notes
and other production directives outside spoken dialogue for separate Studio setup.

## Sources

- TXT, Markdown, READMEs, RST, CSV, JSON and text logs: full text with encoding checks.
- Code/configuration: Python, JavaScript/JSX/TypeScript, shell, SQL, C/C++/C#,
  Java, Go, Rust, HTML/CSS, YAML/TOML/XML/INI. Files are read, never executed.
  Python definitions and docstring locations use AST parsing; JavaScript symbol
  annotations are explicitly heuristic. Other code formats retain full text.
- PDF: text extraction with page references; no OCR. Check reading order and diagrams.
- DOCX: body paragraphs and table text; no images, headers, comments or footnotes.
- Images (PNG, JPEG, WEBP, TIFF, BMP, GIF): local Tesseract OCR with frame/pixel
  references, recognition confidence and machine-transcription labels. No visual
  descriptions; review recognition errors. English language data is installed.
- Google Docs: download DOCX/TXT or paste the text and original URL. URLs are recorded
  as references; the app does not fetch private Google documents. Direct account
  import is not implemented.
- Legacy DOC/RTF and other formats: export to a supported format. Unreadable sources
  produce visible warnings; a package with no readable sources is rejected.

Limits: 20 MiB per extraction input, one million extracted characters per document,
two million characters per context package. Image OCR also limits each input to
20 frames and 30 million pixels per frame, with a 90-second timeout per frame. Sources and versioned packages remain
local. Context generation does not call an LLM. Downloaded packages can be large;
select fewer sources to fit the external writer's context window.

Packages are saved under `episodes/<id>/context_packages/context_<timestamp>.json`.
`latest.json` identifies the latest package. Changing a source selection or brief
does not change an existing package; rebuild to create another version.

## Internal writer

The pinned local Qwen writer is available under **Local writer: ads and short posts**
in Context. Supply facts, generate a draft, edit and download it. Ads are capped
at 180 words; posts at 120. Copy is not automatically published or inserted into
an episode. Existing ad production and social export tools remain available.

Episode generation and section rewriting are retired. Their old HTTP endpoints
return 410 with migration guidance. Worker compatibility methods reject long-form
writing. Episode-generation implementations were removed from the production
worker; rendering no longer initializes the personality/script-generation systems.

The pre-rebuild writer, mixed production modules and UI are preserved in
`archive/legacy-episode-writer/20261027_045253/` with an original-file hash manifest.
Retired generation tests are also archived there. Shared production and compatibility
modules remain where imports require them; archive files are not on the runtime path.

## Checks

Run `python scripts/test.py`, `npm --prefix frontend run lint`, and
`npm --prefix frontend run build`. With the app running, run
`python scripts/verify_context_ui.py` using the studio environment with Playwright.
The browser check intercepts API calls and does not modify actual episodes.

## Local OCR setup

Tesseract 5.4.0.20240606 is installed at
`C:/Program Files/Tesseract-OCR/tesseract.exe` with English (`eng`) and orientation
(`osd`) data. The extractor uses English. The path is pinned in the ignored
`config/runtime.local.json`; `DANDY_TESSERACT_PATH` overrides it. Installation:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact --source winget
```

The context screen and `GET /api/authoring/ocr/status` report engine readiness.
OCR uses a local subprocess, temporary image preparation and no cloud calls.
Blank images fail with a readable message rather than an invented description.
Scanned PDF rasterization and automatic OCR of PDF pages are not implemented;
export scanned pages as images for this extractor.

## Source records, curation and sizing

Extractors are registered in `services/authoring/extractors.py`. Each emits
version-1 source records with stable record IDs, source name/hash, text, locator,
extraction method and evidence type. Context packs retain the existing grouped
`sources[].sections[]` layout for compatibility; every new section is a normalized
record. Text/Markdown/code have exact line ranges, with Markdown headings and
Python symbol/docstring locations. Text is split into non-overlapping chunks;
no lines are removed to create the preview. Existing archived packs remain intact.

In Sources, use **Analyze Selected Sources** to inspect extraction before building
a pack. Source Facts has a separate read-only preview panel. Model/window settings,
generation and downloads are in Build & Export.
Locations/excerpts preview the first 20 records, with at most 200 characters per
excerpt. Counts and estimates use complete extracted text, and the exported pack
keeps all selected readable evidence. Errors are shown explicitly. An unreadable
selected file must be deselected before the saved pack can be exported.

Mark a source **Priority** to place it first among source evidence. Priority does
not change factual confidence or override owner direction. Source selections,
priorities, model name, context-window size and output reservation are versioned
under `curation` in the manifest. Changing these or the brief requires a rebuild
before downloading the current pack.

Set the external model's context window and reserve space for its script output.
Live planning counts analyzed source text and current direction/brief; it excludes
the show bible and other instructions until building. The saved Markdown estimate
includes the complete rendered pack, with a separate 15% + 256-token margin and
the output reservation. A separate estimate covers the larger JSON trace manifest.
The heuristic is UTF-8 bytes divided by three, rounded up. It is **not** an exact
external-model tokenizer and cannot guarantee a fit. Over-budget packs show a
warning; no evidence is silently trimmed. Reduce sources or increase the declared
window as appropriate for the external model you actually use.

## Episode planning and the next Source Library decision

NEW creates an episode, never a segment. The server assigns an ID when none is
supplied. Create Episode and Episode Planning use title, main topic, episode brief
and a target episode duration; they do not create dialogue. Duplicate explicit
IDs are rejected rather than overwriting an existing episode. Imported script
estimates and rendered audio determine actual runtime. The old internal generation
plan, key-point and custom-instruction controls are removed from these dialogs;
Manual Direction owns editorial instructions. Segments will be child planning
records within an episode, not episode records with a segment label.

The next agreed UI separation is Create Episode → Source Library → Context
Generator. The Source Library is a planned dedicated workspace for document intake,
management and reusable immutable source versions. Episode-specific links will
pin versions, selections, priority and source notes. Context Generator will own
Manual Direction and the curation/assembly/export process. This dedicated Source
Library and cross-episode document reuse are not implemented yet; current uploads
remain in the episode's Sources tab until that work is explicitly started.
