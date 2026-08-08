# Phil & Jim Dandy Show — Hardened Pipeline

## What This Fixes

Your system had 8 identified failure modes. This hardened pipeline fixes all of them:

| # | Problem | Severity | Fix |
|---|---------|----------|-----|
| 1 | `[unknown]` detector documented but not implemented | **CRITICAL** | `quality_guard.py` |
| 2 | Script is ~30 sec instead of 30-45 min | **CRITICAL** | `script_expander.py` |
| 3 | All template vars = topic (repetitive dialogue) | **HIGH** | `context_builder.py` |
| 4 | Seed fallback also only ~1 min | **HIGH** | Enhanced `script_seed.py` |
| 5 | No validation on generated scripts | **HIGH** | Quality gates in `worker.py` |
| 6 | Hardcoded nonsense injections | **MEDIUM** | Filtered in `worker.py` |
| 7 | `format_map` swallows all errors silently | **MEDIUM** | Detection + logging |
| 8 | `wait_what` fires too often | **LOW-MED** | Cooldown in SKG logic |

## Files Included

```
dandy_hardened/
├── quality_guard.py              ← NEW: [unknown] detection + quality scoring
├── context_builder.py            ← NEW: Rich template context from key_points
├── script_expander.py            ← NEW: Extend scripts to target duration
├── script_seed.py                ← REPLACEMENT: Full-length seed fallback
├── worker.py                     ← REPLACEMENT: Hardened pipeline
├── COMMUNICATION_LAYER_PATCH.md  ← PATCH: How to update communication_layer.py
└── README.md                     ← This file
```

## Installation

### Step 1: Copy new files to your project

```powershell
# From: C:\dev\Desktop\Dandy\ (your project root)
# Copy these to your backend services directory:

copy dandy_hardened\quality_guard.py       backend\app\services\production\
copy dandy_hardened\context_builder.py     backend\app\services\production\
copy dandy_hardened\script_expander.py     backend\app\services\production\
copy dandy_hardened\script_seed.py         backend\app\services\production\

# IMPORTANT: Backup your existing worker.py first!
copy backend\app\services\production\worker.py backend\app\services\production\worker.py.bak
copy dandy_hardened\worker.py              backend\app\services\production\
```

### Step 2: Patch your communication_layer.py

Follow the instructions in `COMMUNICATION_LAYER_PATCH.md` to update your
existing `communication_layer.py` with the rich context builder.

### Step 3: Update your API endpoint to use the new worker

In your FastAPI route (likely `backend/app/api/production.py`), change:

```python
# OLD:
from ..services.production.worker import MergedDandyPodcastWorker
worker = MergedDandyPodcastWorker()

# NEW:
from ..services.production.worker import HardenedPodcastWorker
worker = HardenedPodcastWorker()
```

### Step 4: Restart backend

```powershell
cd C:\dev\Desktop\Dandy\backend
# Restart your uvicorn server
```

## How It Works

### The New Pipeline

```
Episode Config
     │
     ▼
[context_builder]  ← Extracts rich varied values from key_points
     │
     ▼
[SKG Generation]   ← Phil & Jim banter (your existing system)
     │
     ▼
[quality_guard]    ← DETECTS [unknown], raw templates, nonsense
     │ (if ACCEPT)
     ▼
[script_expander]  ← Extends to target duration (30-45 min)
     │
     ▼
[quality_guard]    ← Validates expanded script
     │ (if ACCEPT)
     ▼
[Audio Production] ← TTS + mixing (unchanged)

Fallback chain if any stage fails:
  SKG fails → Retry with tweaked params → Enhanced seed script → Minimal emergency script
```

### Quality Gate Decisions

The `quality_guard.py` evaluates every script and returns one of:

- **`ACCEPT`** — Script passes all checks, proceed to production
- **`REJECT_RETRY`** — 1 critical issue (retry generation with different params)
- **`FALLBACK_SEED`** — Multiple critical issues, use enhanced seed script
- **`FALLBACK_MINIMAL`** — Everything failed, use emergency 4-line script

### Script Expansion

The `script_expander.py` takes your SKG's ~6 lines and extends them to 300-500+
lines by generating additional Phil/Jim exchanges that rotate through key_points.

Example:
- Input: 6 lines from SKG (~90 words, ~30 seconds)
- Target: 40 minutes @ 155 wpm = 6,200 words
- Output: ~420 lines (~6,300 words, ~41 minutes)

## Verification

### Test the quality guard directly:

```python
# In Python shell or add to scripts/test_quality.py
from backend.app.services.production.quality_guard import ScriptQualityGuard, quick_check

# Good script
good_script = [
    {"speaker": "phil", "text": "Welcome to the show! Today we're talking about AI."},
    {"speaker": "jim", "text": "Hold on... AI sounds good, but where's the proof?"},
]
print(quick_check(good_script, target_minutes=40))  # False (too short)

# Bad script with [unknown]
bad_script = [
    {"speaker": "phil", "text": "Welcome to the [unknown] show about [unknown]!"},
    {"speaker": "jim", "text": "That doesn't make [unknown] sense."},
]
guard = ScriptQualityGuard()
report = guard.evaluate(bad_script, target_minutes=40)
print(report.decision)  # FALLBACK_SEED
print(report.unknown_pct)  # 100.0
```

### Test the context builder:

```python
from backend.app.services.production.context_builder import build_rich_context

ctx = build_rich_context(
    topic="artificial intelligence",
    key_points=[
        "Machine learning is transforming healthcare diagnostics",
        "Privacy concerns around training data are growing",
        "Small language models can run on edge devices now",
    ],
    title="The Future of AI",
)

print(ctx["tech_gadget"])   # "diagnostic tool" (domain-aware!)
print(ctx["market"])        # "healthcare artificial intelligence"
print(ctx["trend"])         # "privacy concerns" (from key points!)
print(ctx["domain"])        # "healthcare" (auto-detected!)
```

### Test the script expander:

```python
from backend.app.services.production.script_expander import ScriptExpander

expander = ScriptExpander()
short_script = [
    {"speaker": "phil", "text": "Let's talk about AI!", "emotion": "excited", "pause_after": 0.35},
    {"speaker": "jim", "text": "Yeah but... does it actually work?", "emotion": "skeptical", "pause_after": 0.55},
]

full_script = expander.expand(
    base_lines=short_script,
    key_points=["Healthcare AI", "Privacy issues", "Edge deployment"],
    topic="artificial intelligence",
    target_minutes=5,  # Short for testing
)
print(f"Expanded from {len(short_script)} to {len(full_script)} lines")
```

## Logs to Watch

After installing, watch your backend logs for these entries:

```
# Good generation:
[Worker] Generating script: topic='AI' target=40min key_points=5
[ContextBuilder] Built context for 'The Future of AI' | domain=healthcare | key_points=5
[Worker] Script accepted on attempt 1 (score: 85.5)
[Worker] Expanding script: 89 → 6200 words
[ScriptExpander] Complete: 412 lines, 6312 words (target: 40 min = 6200 words, 101.8%)

# Fallback path:
[Worker] Script rejected on attempt 1 (score: 35.2), retrying...
[Worker] Script failed quality gate (score: 28.1), falling back to seed
[SeedScript] Generated 384 lines, 5890 words (target: 40 min = 6200 words)
```

## Rollback

If anything goes wrong, restore your original worker:

```powershell
copy backend\app\services\production\worker.py.bak backend\app\services\production\worker.py
```

## No Changes Needed For

These parts of your system work as-is and don't need changes:

- **Frontend** (`EpisodeTab.jsx`) — Calls the same API endpoints
- **Audio production** (TTS + mixing) — Unchanged in worker.py
- **Ad system** — Separate pipeline, unaffected
- **Social system** — Separate pipeline, unaffected
- **OBS/Studio controls** — Unrelated to script generation
- **Voice configs** (`config/voices.json`) — Still used by TTS
