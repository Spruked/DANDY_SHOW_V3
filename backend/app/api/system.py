from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

from fastapi import APIRouter, Body, HTTPException

from ..core.paths import PROJECT_ROOT, CONFIG_ROOT
from ..core.settings import load_project_config, load_qwen_tts_config, load_voices_config
from ..services.production import llm_writer
from ..services.storage.asset_library import library_summary
from ..services.tts.kokoro_wrapper import get_tts_runtime
from ..services.tts.voice_forge_wrapper import voice_forge_status


router = APIRouter(tags=["system"])
_ALLOWED_TTS_ENGINES = {"kokoro", "qwen", "voice_forge"}


def _qwen_bridge_status() -> Dict[str, Any]:
    cfg = load_qwen_tts_config()
    bridge_url = str(cfg.get("bridge_url") or "").rstrip("/")
    if not cfg.get("enabled") or not bridge_url:
        return {"enabled": bool(cfg.get("enabled")), "status": "disabled"}
    try:
        timeout = float(cfg.get("timeouts", {}).get("health_seconds", 3))
        with urlopen(f"{bridge_url}/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"enabled": True, "status": "ok", **payload}
    except (OSError, URLError, ValueError) as exc:
        return {"enabled": True, "status": "unreachable", "bridge_url": bridge_url, "error": str(exc)}


@router.get("/health")
async def health() -> Dict:
    config = load_project_config()
    return {
        "status": "healthy",
        "project_root": str(PROJECT_ROOT),
        "mode": config.get("project", {}).get("mode", "unknown"),
        "dashboard_reference": config.get("dashboard", {}).get("ui_reference_source"),
        "script_writer": llm_writer.writer_status(),
        "tts_runtime": get_tts_runtime(),
        "qwen_tts_bridge": _qwen_bridge_status(),
        "voice_forge": voice_forge_status(),
        "asset_library": library_summary(),
    }


@router.post("/qwen-tts/probe")
async def qwen_tts_probe(payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    cfg = load_qwen_tts_config()
    bridge_url = str(cfg.get("bridge_url") or "").rstrip("/")
    if not cfg.get("enabled") or not bridge_url:
        raise HTTPException(status_code=503, detail="Qwen TTS bridge is not enabled or configured")

    speaker = str(payload.get("speaker") or "phil")
    voice_map = cfg.get("voices", {})
    instruction_map = cfg.get("instructions", {})
    text = str(payload.get("text") or "Qwen CUDA studio probe is online.").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    output_dir = PROJECT_ROOT / "staging" / "qwen_studio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "qwen_studio_probe.mp3"
    request_payload = {
        "text": text,
        "speaker": speaker,
        "voice": payload.get("voice") or voice_map.get(speaker),
        "emotion": payload.get("emotion") or "warm",
        "instruction": payload.get("instruction") or instruction_map.get(speaker),
        "language": payload.get("language") or "English",
        "format": "mp3",
        "output_path": str(output_path),
    }
    request = Request(
        f"{bridge_url}/synthesize",
        data=json.dumps(request_payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        timeout = float(cfg.get("timeouts", {}).get("synthesis_seconds", 180))
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except (OSError, URLError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    produced = Path(result.get("audio_file") or result.get("path") or output_path)
    return {
        "ok": output_path.exists() or produced.exists(),
        "output_path": str(output_path if output_path.exists() else produced),
        "bytes": (output_path if output_path.exists() else produced).stat().st_size if (output_path.exists() or produced.exists()) else 0,
        "bridge": result,
    }


@router.get("/system/config-summary")
async def config_summary() -> Dict:
    config = load_project_config()
    voices = load_voices_config()
    return {
        "project": config.get("project", {}),
        "dashboard": config.get("dashboard", {}),
        "tts": config.get("tts", {}),
        "voice_keys": sorted(list(voices.keys())),
        "script_writer": llm_writer.writer_status(),
        "asset_library": library_summary(),
    }


@router.get("/tts-engine")
async def get_tts_engine() -> Dict[str, Any]:
    config = load_project_config()
    selected = str(config.get("tts", {}).get("primary_engine", "kokoro")).lower()
    return {
        "selected_engine": selected,
        "allowed_engines": sorted(_ALLOWED_TTS_ENGINES),
        "fallback_engine": None,
    }


@router.post("/tts-engine")
async def set_tts_engine(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    selected = str(payload.get("engine") or "").strip().lower()
    if selected not in _ALLOWED_TTS_ENGINES:
        raise HTTPException(
            status_code=400,
            detail="Dandy production TTS must be 'kokoro', 'qwen', or 'voice_forge'. No fallback engine is permitted.",
        )

    cfg_path = CONFIG_ROOT / "config.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    tts = dict(data.get("tts", {}))
    tts["primary_engine"] = selected
    tts["fallback_engine"] = "none"
    tts["allowed_engines"] = ["kokoro", "qwen", "voice_forge"]
    data["tts"] = tts
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    load_project_config.cache_clear()

    return {
        "saved": True,
        "selected_engine": selected,
        "allowed_engines": ["kokoro", "qwen", "voice_forge"],
        "fallback_engine": None,
    }


@router.get("/voices")
async def voices() -> Dict:
    voices_config = load_voices_config()
    kokoro = []
    for speaker, info in voices_config.items():
        primary_engine = str(info.get("primary_engine") or "").lower()
        primary_voice = info.get("primary_voice")
        if primary_engine == "kokoro" and primary_voice:
            kokoro.append({"id": primary_voice, "speaker": speaker, "path": primary_voice})

    return {
        "kokoro": kokoro,
        "allowed_engines": ["kokoro", "qwen", "voice_forge"],
        "fallback_engine": None,
        "source": "config/voices.json",
    }


# ── Intro/Outro config ────────────────────────────────────────────────────────

def _load_intro_outro_cfg() -> Dict[str, Any]:
    cfg_path = CONFIG_ROOT / "config.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    from ..services.production.intro_outro import DEFAULT_CONFIG
    io = data.get("intro_outro", {})

    def merge(base, override):
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = merge(result[k], v)
            else:
                result[k] = v
        return result

    return merge(DEFAULT_CONFIG, io)


@router.get("/intro-outro-config")
async def get_intro_outro_config() -> Dict:
    return _load_intro_outro_cfg()


@router.post("/intro-outro-config")
async def save_intro_outro_config(payload: Dict[str, Any] = Body(...)) -> Dict:
    cfg_path = CONFIG_ROOT / "config.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    incoming = {k: v for k, v in payload.items() if k not in ("_meta",)}
    data["intro_outro"] = incoming
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    load_project_config.cache_clear()
    return {"saved": True, "intro_outro": data["intro_outro"]}


@router.post("/intro-outro-preview")
async def preview_intro_outro(payload: Dict[str, Any] = Body(...)) -> Any:
    import tempfile
    from fastapi.responses import Response
    from ..services.production.intro_outro import build_intro, build_outro, DEFAULT_CONFIG

    section = str(payload.get("section", "intro")).lower()
    topic = str(payload.get("topic", "the show"))

    def merge(base, override):
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = merge(result[k], v)
            else:
                result[k] = v
        return result

    cfg = merge(DEFAULT_CONFIG, _load_intro_outro_cfg())

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"{section}_preview.mp3"
        try:
            if section == "intro":
                build_intro(cfg, PROJECT_ROOT, out)
            else:
                build_outro(cfg, PROJECT_ROOT, out, topic=topic)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        audio_bytes = out.read_bytes()

    return Response(content=audio_bytes, media_type="audio/mpeg")
