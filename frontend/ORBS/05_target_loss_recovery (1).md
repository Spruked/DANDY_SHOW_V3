# Target Loss Recovery

Part of the `orbs-tamp-runtime` repo. A third, independent motion
doctrine alongside Natural Stance and the Clumsy Motion Pack — this one
is a genuine runtime fault state, not a personality behavior.

## Why this is a separate system

```
NATURAL STANCE           Nothing is wrong. ±X variation only.
CLUMSY MOTION PACK       Intentional, harmless imperfection.
                         Target confidence = CONFIRMED throughout.
TARGET LOSS RECOVERY     Actual geometry/confidence failure.
                         Target must be reacquired or abandoned.
```

The Clumsy Motion Pack is explicitly gated to only fire when target
confidence is CONFIRMED and geometry confidence is HIGH — the exact
opposite of the condition that triggers this doctrine. These systems
must never share a code path or a confidence gate; conflating "a real
pointer problem" with "she's charmingly imperfect on purpose" would
let genuine failures get silently absorbed as personality instead of
escalating through the pointer confidence pipeline (Pointer Recovery
Pass, CONFIRMED/TRANSIENT/DYNAMIC/CONFLICT/UNVERIFIED taxonomy) where
they belong.

## Trigger

Enter Target Loss Recovery when a previously-valid target becomes
unavailable during:

```
ACQUIRE
APPROACH
STANCE
POINT preparation
```

Example causes:

```
DOM element disappeared
route changed
target moved beyond tolerance
visibility dropped
selector/anchor broke
confidence fell below threshold
```

## Recovery destination

The ORB continues toward the **last confirmed Ping coordinate** —
not the canonical/static location:

```
LAST_CONFIRMED_PING = (Xlc, Ylc)
```

This gives the runtime a short, moving search window rather than
having the ORB abruptly stop.

## Recovery sequence

```
TARGET LOST
    ↓
preserve last confirmed Ping
    ↓
continue slow glide
    ↓
SEARCH / refresh live geometry
    ↓
 ┌───────────────┴───────────────┐
 ↓                               ↓
TARGET FOUND                  TARGET ABSENT
 ↓                               ↓
RE-ACQUIRE                    BOW-OUT
 ↓
recompute N + stance
 ↓
approach
 ↓
point
 ↓
PING
```

### Exit 1 — Re-acquire

When the target reappears or its new location is resolved:

```
new Ping X,Y
→ recompute stance
→ recompute N
→ redirect glide
→ decelerate
→ point
→ Ping
```

The correction must remain smooth. No snapping.

### Exit 2 — Bow-out

When the target cannot be recovered within the search budget:

```
slow release from approach
→ abandon pointing posture
→ small neutral retreat/arc
→ no Ping
→ report failure / recovery option
```

**Key rule: a failed target can never end with a Ping-like gesture.**
Ping means verified target. This is the one place a botched approach
could otherwise violate the core cross-doctrine rule — see below.

Re-acquire and bow-out must not share a tail animation. A successful
re-acquire ends in a real Ping; a bow-out needs its own distinct
release motion so it never visually resembles a completed Ping when
nothing was actually pointed at.

## Recovery time budget

Target-loss recovery has its **own short, bounded** search-window
budget. It does not inherit the variable, potentially-long budget used
for normal glide/tool/voice latency cover (see
`02_glide_speed_and_latency_doctrine.md`):

```
normal glide latency cover  = variable (sized to slowest of tool/voice/geometry)
target-loss search window   = short and bounded
```

A range of roughly 500-1500ms is worth testing experimentally — not
yet canonized as a fixed number; the right value should come from
observing actual motion, not from being decided in the abstract.

The visitor should perceive: *"she noticed something moved and
corrected herself."* Not: *"she got lost."*

## Cross-doctrine rule

> She is allowed to be imperfect in motion. She is never allowed to
> fake certainty at the destination.

This is the same rule that governs the Clumsy Motion Pack (a mistake
in the journey, never in the answer) — Target Loss Recovery is where
it matters most, because here the "mistake" is real rather than
performed, which makes the no-fake-Ping rule a hard safety property of
the runtime rather than a stylistic choice.
