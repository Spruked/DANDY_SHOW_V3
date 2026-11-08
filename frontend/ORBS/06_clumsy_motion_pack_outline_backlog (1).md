# Clumsy Motion Pack — Implementation Outline (Backlog)

For later. Doctrine is settled in `03_clumsy_motion_pack.md` — this is
the build-ready checklist to work from when this gets picked up.

## 1. Scope for this pass

- [ ] Four named behaviors only, no more, for v1:
  - Soft Overshoot
  - Wrong-Side Peek
  - Early Brake
  - Point Correction
- [ ] No new behaviors added until these four are tuned by eye in a
      running build (per the "don't canonize numbers before seeing
      motion" lesson from Target Loss Recovery).

## 2. Hard gate (build first, before any behavior logic)

A clumsy behavior may only be *considered* when all of:

- [ ] `target_confidence == CONFIRMED`
- [ ] `geometry_confidence == HIGH`
- [ ] current stage is not in the suppression list
- [ ] action is not flagged precision-critical

Suppression list (stage IDs to exclude):
- [ ] Checkout
- [ ] Payment
- [ ] Signature
- [ ] Confirmation
- [ ] any destructive-control action

This gate should be a single shared check, reused by all four
behaviors — not reimplemented per-behavior.

## 3. Trigger model (per behavior)

Each behavior needs, at minimum:

```
{
  "behavior_id": "soft_overshoot",
  "rarity_weight": <float>,     // relative frequency vs. other behaviors
  "cooldown_ms": <int>,         // minimum gap since last clumsy event
  "session_cap": <int>          // max occurrences per visitor session
}
```

- [ ] Define starting weights (rough guess is fine — this is a tuning
      pass item, not a design decision)
- [ ] Enforce "no two clumsy events back-to-back" via the cooldown
- [ ] Enforce per-session cap

## 4. Motion-curve requirement

- [ ] Each behavior implemented as a **local perturbation of the
      existing slow-glide curve** — reuse the glide easing function,
      do not build a separate fast/sharp motion style
- [ ] Sanity check once built: does a clumsy moment still read as
      "slow and confident, briefly imperfect" rather than "different
      mood"? If not, the perturbation is too sharp — tune amplitude
      before tuning anything else.

## 5. Per-behavior build notes

**Soft Overshoot**
- [ ] Overshoot distance range: 8–18px (from doctrine — test this
      range in motion before treating it as fixed)
- [ ] Correction should read as "gentle," not a snap-back

**Wrong-Side Peek**
- [ ] Requires the direction-fallback logic from
      `01_pointer_geometry_and_stance_doctrine.md` to already be in
      place — this behavior is a *voluntary* version of that fallback,
      not a new mechanism
- [ ] Arc path around the target, not a straight cut across it

**Early Brake**
- [ ] Small second movement after the early brake should be clearly
      visible, not a micro-jitter that reads as a rendering glitch

**Point Correction**
- [ ] "Slightly wide" start position — needs a defined offset range,
      separate from the overshoot range above
- [ ] Correction onto exact Ping must be visible and deliberate, not
      instantaneous (an instant snap here would look like a bug, not
      a personality beat)

## 6. Test mode requirements

- [ ] Seeded/deterministic mode: given the same seed, the same
      behavior (or none) fires at the same point, every run
- [ ] Regression test: clumsy behaviors never fire when the hard gate
      (section 2) is false, for any combination of confidence/stage
      inputs
- [ ] Regression test: no clumsy event ends in a Ping-like gesture if
      it was actually a Target Loss Recovery event misclassified as
      clumsy (cross-check against `05_target_loss_recovery.md` —
      these two systems must never share a trigger path)

## 7. Marketplace packaging (later, after behaviors are tuned)

- [ ] Package as a single opt-in asset, not four separate toggles
- [ ] Default-off for stages/site types where precision reads as
      trust (flag at the site-config level, not hardcoded)
- [ ] Pricing follows the per-item Marketplace model already decided
      (not the flat $1.88 model)

## Open questions to resolve before/during build

- Does `rarity_weight` need to vary by *action type* (close point vs.
  wide gesture), or is a flat weight per behavior good enough for v1?
- Should the session cap reset per page/route, or persist for the
  whole visit?
- Does Wrong-Side Peek ever conflict with a legitimate direction
  fallback happening for a real functional reason (target near an
  edge)? If both can fire in the same approach, which takes priority?
