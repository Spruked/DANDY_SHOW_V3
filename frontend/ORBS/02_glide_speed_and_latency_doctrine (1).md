# ORB Glide, Speed & Latency Doctrine

Part of the `orbs-tamp-runtime` repo. Governs the `L` (latency/timing)
field of Sorb and its influence over `G` (live geometry), and the
APPROACH / RECOVER states in the TAMP state vocabulary.

## Core idea

Movement is not decoration layered on top of async work. Movement
**owns** the latency. The travel time of the glide is the buffer that
absorbs tool calls, geometry refresh, Ping prep, and voice generation —
it is not idle animation running in parallel with "real" work happening
elsewhere.

## Full choreography

```
ACQUIRE TARGET
      ↓
RESOLVE STANCE
      ↓
BEGIN SLOW GLIDE
      ↓
 tools + voice + geometry run concurrently
      ↓
GRADUAL DECELERATION
      ↓
final live target check
      ↓
ARRIVE IN ±X STANCE
      ↓
POINT
      ↓
PING
      ↓
VOICE LANDS WITH THE GESTURE
      ↓
OUT
```

During the glide, in parallel:

```
tool call / action preparation
live target geometry refresh
Ping preparation
voice generation
TTS first-audio preparation
final stance verification
```

The intended visitor experience: it feels like the ORB knew where she
was going the instant she heard the question, even though the system
was doing real work during the trip.

## Travel-time sizing

Glide duration is **not a fixed duration**. It is sized by the slowest
of:

```
tool-call latency
ping-action time
voice latency
```

- Longer physical distance to the target gives the system more free
  processing time "for free."
- Short physical distance means the hot path (tool call, voice gen)
  has to finish almost immediately, since there's little travel time
  to hide behind.

### Minimum-glide-time floor

Because distance and required latency-cover don't always agree (a
*close* target with *long* expected latency), the motion planner needs
an explicit **minimum glide-time floor**, derived from expected latency
and checked **before** the glide starts — not adjusted reactively
mid-flight. Committing to a short, fast glide and then awkwardly
slowing down partway through recreates the "stalled" look this whole
doctrine exists to avoid.

## Target loss during approach

If the target becomes unavailable mid-approach (moved, vanished, DOM
change, confidence drop), this is a real fault condition, not a glide
variant — it is governed by its own doctrine, `05_target_loss_recovery.md`,
with its own bounded search-window budget separate from the variable
latency-cover budget above.

The **final live target check** (right before Point, in the
choreography above) is the hook into that doctrine: if the check finds
the target moved or vanished, it redirects into Target Loss Recovery's
re-acquire/bow-out branches rather than pointing at a stale coordinate
because the glide already committed.

## Core doctrine line

> The Ping itself must remain correct. She may make a mistake getting
> there. She does not knowingly give the visitor the wrong answer.
>
> Precision belongs to the target. Personality belongs to the journey.

## Voice/gesture sync

"She glides while voice synthesizes" only pays off if the audio's
first frame is timed to land within some tolerance of Point/Ping —
otherwise the result is a silent point-and-wait, or a gesture followed
by catching-up audio, both of which recreate the stalled feeling this
doctrine eliminates everywhere else. Implementation should define a
named tolerance window (e.g. TTS first-audio ready within ±150ms of
arrival), with the deceleration curve able to stretch slightly to
cover a shortfall rather than the arrival simply happening early.

## ORB Speed Doctrine

Default state is always a slow, confident, decelerating glide. Speed
is never used merely because the computer *can* move faster.

```
NORMAL
Target Lock → Stance Lock → Slow Glide → Decelerate
→ ±X Stance → Point → Ping → Out
```

### Speed Governor

The motion planner has only three meaningful speed classes:

```
GLIDE   = normal behavior (default, always)
BRISK   = visitor explicitly signals impatience ("hurry", "show me quickly")
URGENT  = genuine runtime/site failure requiring immediate response
          (critical workflow broke, target disappeared mid-action,
           navigation failure threatens current task, site state
           suddenly invalidated)
```

Otherwise: **fast movement is forbidden.** Fast movement is exceptional,
not a convenience.

## No LOITER state

A LOITER state was proposed and explicitly rejected — it conflicts with
the ORB's physical character. If processing runs longer than the glide
after arrival, the ORB should use **purposeful micro-motion**, not stop
and wait:

```
small stance adjustment
gentle arc
subtle orientation correction
slight N adjustment
re-check target
```

Never: arrive, stop, wait, stare.

> She moves slowly because she owns the space — not because she is
> slow. She moves fast only when the situation gives her a reason to
> hurry.

### Latency compensation priority order

```
1. Use the journey first  (stretch/shape the glide itself)
2. Use small purposeful movement second  (micro-motion after arrival)
3. Never freeze
```
