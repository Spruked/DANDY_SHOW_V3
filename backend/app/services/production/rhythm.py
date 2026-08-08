from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class RhythmState:
    # Observed
    human_load: float
    desync_risk: float
    turn_latency_ms: float
    # Commanded
    tempo: str
    intensity: str
    verbosity: str
    # Stability controls
    cooldown_until_ms: int
    version: int

    @property
    def interaction_tempo(self) -> str:
        return self.tempo

    @property
    def cognitive_intensity(self) -> str:
        return self.intensity

    @property
    def last_turn_ms(self) -> float:
        return self.turn_latency_ms

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        # Compatibility aliases for existing call sites.
        payload["interaction_tempo"] = self.tempo
        payload["cognitive_intensity"] = self.intensity
        payload["last_turn_ms"] = self.turn_latency_ms
        return payload

    @classmethod
    def from_context(
        cls,
        context: Optional[Dict[str, Any]],
        prev: Optional["RhythmState"] = None,
        now_ms: Optional[int] = None,
    ) -> "RhythmState":
        payload = dict(context or {})
        raw = dict(payload.get("rhythm") or {})

        if prev is None:
            prev = _state_from_payload(raw) or default_rhythm_state(now_ms=now_ms)
        return estimate_rhythm(payload, prev, now_ms=now_ms)


def default_rhythm_state(now_ms: Optional[int] = None) -> RhythmState:
    now = int(now_ms or time.time() * 1000)
    return RhythmState(
        human_load=0.45,
        desync_risk=0.25,
        turn_latency_ms=0.0,
        tempo="normal",
        intensity="medium",
        verbosity="medium",
        cooldown_until_ms=now,
        version=0,
    )


def estimate_rhythm(ctx: Dict[str, Any], prev: RhythmState, now_ms: Optional[int] = None) -> RhythmState:
    now = int(now_ms or time.time() * 1000)
    payload = dict(ctx or {})
    rhythm_raw = dict(payload.get("rhythm") or {})

    human_load = infer_human_load(payload, rhythm_raw)
    desync_risk = infer_desync_risk(payload, rhythm_raw, human_load)
    turn_latency = infer_turn_latency_ms(payload, rhythm_raw, now)

    # Hysteresis guard: preserve commanded outputs while in cooldown window.
    if now < int(prev.cooldown_until_ms):
        return RhythmState(
            human_load=human_load,
            desync_risk=desync_risk,
            turn_latency_ms=turn_latency,
            tempo=prev.tempo,
            intensity=prev.intensity,
            verbosity=prev.verbosity,
            cooldown_until_ms=prev.cooldown_until_ms,
            version=prev.version + 1,
        )

    next_tempo = bounded_tempo_shift(prev.tempo, human_load, desync_risk, turn_latency)
    next_intensity = bounded_intensity_shift(prev.intensity, human_load)
    next_verbosity = bounded_verbosity_shift(prev.verbosity, human_load)

    return RhythmState(
        human_load=human_load,
        desync_risk=desync_risk,
        turn_latency_ms=turn_latency,
        tempo=next_tempo,
        intensity=next_intensity,
        verbosity=next_verbosity,
        cooldown_until_ms=now + 1500,
        version=prev.version + 1,
    )


def infer_turn_latency_ms(payload: Dict[str, Any], rhythm_raw: Dict[str, Any], now_ms: int) -> float:
    last_turn = _coerce_float(
        rhythm_raw.get("turn_latency_ms"),
        _coerce_float(payload.get("turn_latency_ms"), -1.0),
    )
    if last_turn >= 0:
        return round(last_turn, 1)

    latency = _coerce_float(
        rhythm_raw.get("last_turn_ms"),
        _coerce_float(payload.get("response_latency_ms"), _coerce_float(payload.get("last_turn_ms"), -1.0)),
    )
    # If this value looks like an absolute timestamp, convert to delta.
    if latency > 1_000_000_000:
        latency = float(max(0.0, now_ms - int(latency)))
    if latency < 0:
        latency = _coerce_float(payload.get("response_latency_s"), 0.0) * 1000.0
    return round(max(0.0, latency), 1)


def infer_human_load(payload: Dict[str, Any], rhythm_raw: Dict[str, Any]) -> float:
    load = _coerce_float(
        rhythm_raw.get("human_load"),
        _coerce_float(payload.get("human_load"), _coerce_float(payload.get("load"), -1.0)),
    )
    if load >= 0:
        return round(_clamp(load), 3)

    turn_latency = _coerce_float(payload.get("response_latency_ms"), 0.0)
    dense_turns = _coerce_float(payload.get("dense_turns"), 0.0)
    recent_errors = _coerce_float(payload.get("recent_errors"), 0.0)
    inferred = 0.45
    if turn_latency >= 12000:
        inferred += 0.18
    if dense_turns >= 3:
        inferred += 0.10
    if recent_errors > 0:
        inferred += 0.12
    return round(_clamp(inferred), 3)


def infer_desync_risk(payload: Dict[str, Any], rhythm_raw: Dict[str, Any], human_load: float) -> float:
    risk = _coerce_float(
        rhythm_raw.get("desync_risk"),
        _coerce_float(payload.get("desync_risk"), -1.0),
    )
    if risk >= 0:
        return round(_clamp(risk), 3)
    tempo = str(payload.get("interaction_tempo") or payload.get("tempo") or "normal").strip().lower()
    inferred = 0.20 + (human_load * 0.55)
    if tempo == "fast" and human_load > 0.65:
        inferred += 0.10
    return round(_clamp(inferred), 3)


def bounded_tempo_shift(prev_tempo: str, human_load: float, desync_risk: float, turn_latency_ms: float) -> str:
    target = "normal"
    if human_load >= 0.72 or desync_risk >= 0.68 or turn_latency_ms >= 12000:
        target = "slow"
    elif human_load <= 0.35 and desync_risk <= 0.35 and 0 < turn_latency_ms <= 2200:
        target = "fast"
    return _bounded_step(prev_tempo, target, ["slow", "normal", "fast"])


def bounded_intensity_shift(prev_intensity: str, human_load: float) -> str:
    target = "medium"
    if human_load >= 0.74:
        target = "light"
    elif human_load <= 0.32:
        target = "deep"
    return _bounded_step(prev_intensity, target, ["light", "medium", "deep"])


def bounded_verbosity_shift(prev_verbosity: str, human_load: float) -> str:
    target = "medium"
    if human_load >= 0.72:
        target = "low"
    elif human_load <= 0.30:
        target = "high"
    return _bounded_step(prev_verbosity, target, ["low", "medium", "high"])


def _bounded_step(current: str, target: str, ordered: list[str]) -> str:
    if current not in ordered:
        return target if target in ordered else ordered[len(ordered) // 2]
    if target not in ordered:
        return current
    cur_idx = ordered.index(current)
    tgt_idx = ordered.index(target)
    if abs(cur_idx - tgt_idx) <= 1:
        return target
    return ordered[cur_idx + 1] if tgt_idx > cur_idx else ordered[cur_idx - 1]


def _state_from_payload(payload: Dict[str, Any]) -> Optional[RhythmState]:
    if not payload:
        return None
    if "tempo" not in payload and "interaction_tempo" in payload:
        payload = dict(payload)
        payload["tempo"] = payload.get("interaction_tempo")
    if "intensity" not in payload and "cognitive_intensity" in payload:
        payload = dict(payload)
        payload["intensity"] = payload.get("cognitive_intensity")
    if "turn_latency_ms" not in payload and "last_turn_ms" in payload:
        payload = dict(payload)
        payload["turn_latency_ms"] = payload.get("last_turn_ms")
    if "verbosity" not in payload:
        payload = dict(payload)
        payload["verbosity"] = "medium"
    required = {"human_load", "desync_risk", "turn_latency_ms", "tempo", "intensity", "verbosity", "cooldown_until_ms", "version"}
    if not required.issubset(set(payload.keys())):
        return None
    try:
        return RhythmState(
            human_load=round(_clamp(float(payload["human_load"])), 3),
            desync_risk=round(_clamp(float(payload["desync_risk"])), 3),
            turn_latency_ms=round(max(0.0, float(payload["turn_latency_ms"])), 1),
            tempo=str(payload["tempo"]).strip().lower(),
            intensity=str(payload["intensity"]).strip().lower(),
            verbosity=str(payload["verbosity"]).strip().lower(),
            cooldown_until_ms=int(payload["cooldown_until_ms"]),
            version=int(payload["version"]),
        )
    except Exception:
        return None


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default
