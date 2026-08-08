import os
import threading
import logging
from typing import Any, Callable, Dict, Tuple

try:
    import voicemeeterlib
    from voicemeeterlib.error import CAPIError, VMError
except Exception as exc:
    voicemeeterlib = None
    CAPIError = VMError = Exception
    VOICEMEETER_IMPORT_ERROR = exc
else:
    VOICEMEETER_IMPORT_ERROR = None

from ...core.settings import load_project_config


class VoiceMeeterError(Exception):
    pass


class VoiceMeeterConnectionError(VoiceMeeterError):
    pass


class VoiceMeeterRequestError(VoiceMeeterError):
    pass


class VoiceMeeterService:
    CHANNEL_MAP = (
        ("mic1", 0, "MIC 1 · PHIL"),
        ("mic2", 1, "MIC 2 · JIM"),
        ("guest", 2, "GUEST MIC"),
        ("music", 3, "MUSIC BED"),
        ("sfx", 4, "SFX"),
        ("vm", 5, "VOICEMEETER"),
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._preferred: Tuple[str, int] | None = None
        logging.getLogger("voicemeeterlib").setLevel(logging.CRITICAL)

    def status(self) -> Dict[str, Any]:
        return self.state()

    def state(self) -> Dict[str, Any]:
        def _read(vm: Any, kind: str, bits: int) -> Dict[str, Any]:
            channels: Dict[str, Any] = {}
            strip_count = len(vm.strip)

            for channel_id, strip_index, fallback_label in self.CHANNEL_MAP:
                if strip_index >= strip_count:
                    channels[channel_id] = {
                        "id": channel_id,
                        "index": strip_index,
                        "available": False,
                        "label": fallback_label,
                    }
                    continue
                strip = vm.strip[strip_index]
                channels[channel_id] = self._serialize_strip(channel_id, strip_index, strip)

            master = self._serialize_master(vm)
            return {
                "connected": True,
                "kind": kind,
                "bits": bits,
                "strip_count": strip_count,
                "bus_count": len(vm.bus),
                "channels": channels,
                "master": master,
            }

        return self._with_vm(_read)

    def levels(self) -> Dict[str, Any]:
        state = self.state()
        return {
            "connected": state.get("connected", False),
            "kind": state.get("kind", ""),
            "bits": state.get("bits", 0),
            "channels": {
                key: {
                    "available": bool(value.get("available", False)),
                    "vu": float(value.get("vu", 0.0)),
                    "vu_db": float(value.get("vu_db", -200.0)),
                }
                for key, value in state.get("channels", {}).items()
            },
            "master": {
                "available": bool(state.get("master", {}).get("available", False)),
                "vu": float(state.get("master", {}).get("vu", 0.0)),
                "vu_db": float(state.get("master", {}).get("vu_db", -200.0)),
            },
        }

    def set_channel(self, channel_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = str(channel_id or "").strip().lower()
        mapping = {row[0]: row for row in self.CHANNEL_MAP}
        if channel_id not in mapping:
            raise VoiceMeeterRequestError(f"Unknown channel_id '{channel_id}'")

        _, strip_index, _ = mapping[channel_id]
        return self.set_strip(strip_index, patch, channel_id=channel_id)

    def set_strip(
        self, strip_index: int, patch: Dict[str, Any], channel_id: str | None = None
    ) -> Dict[str, Any]:
        strip_index = int(strip_index)
        if strip_index < 0:
            raise VoiceMeeterRequestError("strip index must be >= 0")

        def _apply(vm: Any, kind: str, bits: int) -> Dict[str, Any]:
            if strip_index >= len(vm.strip):
                raise VoiceMeeterRequestError(
                    f"Strip index {strip_index} is not available for {kind}"
                )

            strip = vm.strip[strip_index]
            self._apply_strip_patch(strip, patch)
            response_id = channel_id or f"strip_{strip_index}"
            return {
                "connected": True,
                "kind": kind,
                "bits": bits,
                "channel": self._serialize_strip(response_id, strip_index, strip),
            }

        return self._with_vm(_apply)

    def set_master(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        def _apply(vm: Any, kind: str, bits: int) -> Dict[str, Any]:
            if not len(vm.bus):
                raise VoiceMeeterRequestError("No Voicemeeter bus is available")
            bus = vm.bus[0]
            if "gain" in patch and patch["gain"] is not None:
                bus.gain = self._clamp(float(patch["gain"]), -60.0, 12.0)
            if "mute" in patch and patch["mute"] is not None:
                bus.mute = bool(patch["mute"])
            return {
                "connected": True,
                "kind": kind,
                "bits": bits,
                "master": self._serialize_master(vm),
            }

        return self._with_vm(_apply)

    def set_bus(self, bus_index: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        bus_index = int(bus_index)
        if bus_index < 0:
            raise VoiceMeeterRequestError("bus index must be >= 0")

        def _apply(vm: Any, kind: str, bits: int) -> Dict[str, Any]:
            if bus_index >= len(vm.bus):
                raise VoiceMeeterRequestError(
                    f"Bus index {bus_index} is not available for {kind}"
                )
            bus = vm.bus[bus_index]
            if "gain" in patch and patch["gain"] is not None:
                bus.gain = self._clamp(float(patch["gain"]), -60.0, 12.0)
            if "mute" in patch and patch["mute"] is not None:
                bus.mute = bool(patch["mute"])
            if "mono" in patch and patch["mono"] is not None:
                bus.mono = 1 if bool(patch["mono"]) else 0
            return {
                "connected": True,
                "kind": kind,
                "bits": bits,
                "bus": {
                    "index": bus_index,
                    "gain": float(self._safe_get(bus, "gain", fallback=0.0)),
                    "mute": bool(self._safe_get(bus, "mute", fallback=False)),
                    "mono": bool(self._safe_get(bus, "mono", fallback=0)),
                },
            }

        return self._with_vm(_apply)

    def trigger_macro(self, button_index: int, state: bool | None = None) -> Dict[str, Any]:
        button_index = int(button_index)
        if button_index < 0:
            raise VoiceMeeterRequestError("macro index must be >= 0")

        def _apply(vm: Any, kind: str, bits: int) -> Dict[str, Any]:
            if button_index >= len(vm.button):
                raise VoiceMeeterRequestError(
                    f"Macro index {button_index} is not available for {kind}"
                )
            button = vm.button[button_index]
            if state is None:
                button.trigger = True
            else:
                button.state = bool(state)
            return {
                "connected": True,
                "kind": kind,
                "bits": bits,
                "macro": {
                    "index": button_index,
                    "state": bool(button.state),
                    "trigger": bool(button.trigger),
                },
            }

        return self._with_vm(_apply)

    def _with_vm(self, fn: Callable[[Any, str, int], Dict[str, Any]]) -> Dict[str, Any]:
        if voicemeeterlib is None:
            raise VoiceMeeterConnectionError(
                "Voicemeeter Remote API is unavailable"
                + (
                    f" ({VOICEMEETER_IMPORT_ERROR})"
                    if VOICEMEETER_IMPORT_ERROR
                    else ""
                )
            )

        last_error: str | None = None
        with self._lock:
            for kind, bits in self._candidate_pairs():
                vm = None
                try:
                    vm = voicemeeterlib.api(kind, bits=bits, timeout=1)
                    vm.login()
                    self._preferred = (kind, bits)
                    return fn(vm, kind, bits)
                except (CAPIError, VMError, TimeoutError, OSError, ValueError) as exc:
                    last_error = f"{kind}/{bits}: {exc}"
                except Exception as exc:
                    last_error = f"{kind}/{bits}: {exc}"
                finally:
                    if vm is not None:
                        try:
                            vm.logout()
                        except Exception:
                            pass
        raise VoiceMeeterConnectionError(
            "Could not connect to Voicemeeter Remote API"
            + (f" ({last_error})" if last_error else "")
        )

    def _candidate_pairs(self) -> Tuple[Tuple[str, int], ...]:
        pairs = [(kind, bits) for kind in self._kind_candidates() for bits in self._bits_candidates()]
        if self._preferred and self._preferred in pairs:
            pairs.remove(self._preferred)
            pairs.insert(0, self._preferred)
        return tuple(pairs)

    def _kind_candidates(self) -> Tuple[str, ...]:
        config = load_project_config().get("voicemeeter", {})
        env_kind = os.getenv("VOICEMEETER_KIND")
        config_kind = config.get("kind")
        ordered = [env_kind, config_kind, "banana", "potato", "basic"]
        seen = []
        for value in ordered:
            if not value:
                continue
            candidate = str(value).strip().lower()
            if candidate in ("potato", "banana", "basic") and candidate not in seen:
                seen.append(candidate)
        return tuple(seen) if seen else ("banana", "potato", "basic")

    def _bits_candidates(self) -> Tuple[int, ...]:
        config = load_project_config().get("voicemeeter", {})
        env_bits = os.getenv("VOICEMEETER_BITS")
        config_bits = config.get("bits")
        ordered = [env_bits, config_bits, 64, 32]
        seen: list[int] = []
        for value in ordered:
            if value is None:
                continue
            try:
                bits = int(value)
            except (TypeError, ValueError):
                continue
            if bits in (64, 32) and bits not in seen:
                seen.append(bits)
        return tuple(seen) if seen else (64, 32)

    def _serialize_strip(self, channel_id: str, index: int, strip: Any) -> Dict[str, Any]:
        vu_db = self._read_strip_db(strip)
        return {
            "id": channel_id,
            "index": index,
            "available": True,
            "label": self._safe_get(strip, "label", fallback=f"Strip {index + 1}"),
            "gain": float(self._safe_get(strip, "gain", fallback=0.0)),
            "mute": bool(self._safe_get(strip, "mute", fallback=False)),
            "solo": bool(self._safe_get(strip, "solo", fallback=False)),
            "eq": bool(self._safe_nested_get(strip, ("eq", "on"), fallback=False)),
            "gate": float(self._safe_nested_get(strip, ("gate", "knob"), fallback=0.0)) * 10.0,
            "comp": float(self._safe_nested_get(strip, ("comp", "knob"), fallback=0.0)) * 10.0,
            "a1": bool(self._safe_get(strip, "A1", fallback=False)),
            "a2": bool(self._safe_get(strip, "A2", fallback=False)),
            "b1": bool(self._safe_get(strip, "B1", fallback=False)),
            "b2": bool(self._safe_get(strip, "B2", fallback=False)),
            "vu_db": vu_db,
            "vu": self._db_to_percent(vu_db),
        }

    def _serialize_master(self, vm: Any) -> Dict[str, Any]:
        if not len(vm.bus):
            return {
                "available": False,
                "gain": 0.0,
                "mute": False,
                "mono": False,
                "vu_db": -200.0,
                "vu": 0.0,
            }
        bus = vm.bus[0]
        level = -200.0
        try:
            all_levels = bus.levels.all
            if all_levels:
                level = float(all_levels[0])
        except Exception:
            level = -200.0
        return {
            "available": True,
            "gain": float(self._safe_get(bus, "gain", fallback=0.0)),
            "mute": bool(self._safe_get(bus, "mute", fallback=False)),
            "mono": bool(self._safe_get(bus, "mono", fallback=0)),
            "vu_db": level,
            "vu": self._db_to_percent(level),
        }

    def _apply_strip_patch(self, strip: Any, patch: Dict[str, Any]) -> None:
        if "gain" in patch and patch["gain"] is not None:
            strip.gain = self._clamp(float(patch["gain"]), -60.0, 12.0)
        if "mute" in patch and patch["mute"] is not None:
            strip.mute = bool(patch["mute"])
        if "solo" in patch and patch["solo"] is not None:
            strip.solo = bool(patch["solo"])
        if "eq" in patch and patch["eq"] is not None and hasattr(strip, "eq"):
            strip.eq.on = bool(patch["eq"])
        if "gate" in patch and patch["gate"] is not None and hasattr(strip, "gate"):
            strip.gate.knob = self._clamp(float(patch["gate"]) / 10.0, 0.0, 10.0)
        if "comp" in patch and patch["comp"] is not None and hasattr(strip, "comp"):
            strip.comp.knob = self._clamp(float(patch["comp"]) / 10.0, 0.0, 10.0)
        if "a1" in patch and patch["a1"] is not None and hasattr(strip, "A1"):
            strip.A1 = bool(patch["a1"])
        if "a2" in patch and patch["a2"] is not None and hasattr(strip, "A2"):
            strip.A2 = bool(patch["a2"])
        if "b1" in patch and patch["b1"] is not None and hasattr(strip, "B1"):
            strip.B1 = bool(patch["b1"])
        if "b2" in patch and patch["b2"] is not None and hasattr(strip, "B2"):
            strip.B2 = bool(patch["b2"])

    def _read_strip_db(self, strip: Any) -> float:
        try:
            vals = strip.levels.postfader
            if vals:
                return float(vals[0])
        except Exception:
            pass
        return -200.0

    @staticmethod
    def _db_to_percent(db_value: float) -> float:
        db = float(db_value)
        if db <= -60.0:
            return 0.0
        if db >= 0.0:
            return 100.0
        return round(((db + 60.0) / 60.0) * 100.0, 1)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(value)))

    @staticmethod
    def _safe_get(target: Any, attr: str, fallback: Any) -> Any:
        try:
            return getattr(target, attr)
        except Exception:
            return fallback

    @staticmethod
    def _safe_nested_get(target: Any, attrs: Tuple[str, ...], fallback: Any) -> Any:
        cur = target
        for attr in attrs:
            try:
                cur = getattr(cur, attr)
            except Exception:
                return fallback
        return cur
