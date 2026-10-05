from pathlib import Path
from typing import Any, Dict
from urllib.error import URLError
from urllib.request import urlopen
import json
import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException

from ..core.paths import PROJECT_ROOT, CONFIG_ROOT, EPISODES_ROOT
from ..core.settings import load_project_config, load_qwen_tts_config, load_voices_config
from ..services.production import llm_writer
from ..services.storage.asset_library import library_summary
from ..services.tts.kokoro_wrapper import get_tts_runtime


router = APIRouter(tags=["system"])
_ALLOWED_TTS_ENGINES = {"kokoro", "qwen"}


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
def health() -> Dict:
    config = load_project_config()
    return {
        "status": "healthy",
        "status_scope": "API liveness; see /system/diagnostics for readiness",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "mode": config.get("project", {}).get("mode", "unknown"),
        "dashboard_reference": config.get("dashboard", {}).get("ui_reference_source"),
        "script_writer": llm_writer.writer_status(),
        "tts_runtime": get_tts_runtime(),
        "qwen_tts_bridge": _qwen_bridge_status(),
        "asset_library": library_summary(),
    }


def _now():
    return datetime.now(timezone.utc).isoformat()


def _http_probe(url, json_response=True):
    with urlopen(url, timeout=3) as response:
        body = response.read(262144)
        data = json.loads(body.decode("utf-8")) if json_response else {}
        if url.endswith("/config"):
            data = {"framework": "Gradio", "version": data.get("version"), "queue_enabled": data.get("enable_queue"),
                    "api_names": [item.get("api_name") for item in data.get("dependencies", [])], "synthesis": "unverified"}
        return {"status": "reachable", "url": url, "http_status": response.status, "data": data}


def _writer_probe():
    result = llm_writer.writer_status()
    return {"status": "reachable" if result["bridge_reachable"] else "unavailable",
            "data": result, "inference": "unverified", "source": "live llama.cpp /v1/models"}


_wsl_cache = None
_wsl_lock = threading.Lock()


def _kokoro_probe():
    global _wsl_cache
    with _wsl_lock:
        if _wsl_cache and time.monotonic() - _wsl_cache[0] < 60:
            return {**_wsl_cache[1], "cached": True, "cache_seconds": 60}
        from ..services.production.worker import HardenedPodcastWorker
        code = (
            "import json,importlib.util,os,torch; "
            "print(json.dumps({'cuda_available':torch.cuda.is_available(),"
            "'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu',"
            "'kokoro_installed':importlib.util.find_spec('kokoro') is not None,"
            f"'worker_exists':os.path.isfile({HardenedPodcastWorker._WSL_WORKER!r}),"
            "'torch_version':torch.__version__}))"
        )
        completed = subprocess.run(["wsl", "--", HardenedPodcastWorker._WSL_PYTHON, "-c", code],
                                   capture_output=True, text=True, timeout=12)
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip()[-500:] or "WSL runtime check failed")
        data = json.loads(completed.stdout.strip().splitlines()[-1])
        result = {"status": "ready" if data["kokoro_installed"] and data["worker_exists"] else "unavailable",
                  "data": data, "source": "production WSL Python runtime (read-only)",
                  "checked_at": _now(), "synthesis": "unverified", "cached": False}
        _wsl_cache = (time.monotonic(), result)
        return result


def _gpu_probe():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"status": "unavailable", "error": "nvidia-smi not found", "source": "nvidia-smi"}
    completed = subprocess.run([executable, "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,driver_version",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3, check=True)
    devices = []
    for row in completed.stdout.strip().splitlines():
        values = [value.strip() for value in row.split(",")]
        devices.append(dict(zip(["index", "name", "memory_used_mib", "memory_total_mib", "utilization_percent", "temperature_c", "driver_version"], values)))
    return {"status": "ready" if devices else "unavailable", "data": {"devices": devices}, "source": "live nvidia-smi"}


def _resources_probe():
    data = {"python": sys.version.split()[0], "platform": platform.platform(), "backend_pid": os.getpid(), "cpu_count": os.cpu_count()}
    try:
        import psutil
        memory = psutil.virtual_memory()
        process = psutil.Process()
        data.update(cpu_percent=psutil.cpu_percent(interval=0.15), ram_total_bytes=memory.total,
                    ram_available_bytes=memory.available, ram_used_percent=memory.percent,
                    backend_rss_bytes=process.memory_info().rss, backend_threads=process.num_threads(),
                    backend_uptime_seconds=round(time.time() - process.create_time(), 1))
    except ImportError:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [(key, ctypes.c_ulonglong) for key in ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]
            memory = MemoryStatus(); memory.length = ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                raise ctypes.WinError()
            def cpu_times():
                idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
                if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                    raise ctypes.WinError()
                number = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
                return number(idle), number(kernel) + number(user)
            previous = cpu_times(); time.sleep(.15); current = cpu_times()
            elapsed, idle = current[1] - previous[1], current[0] - previous[0]
            data.update(cpu_percent=round(100 * (1 - idle / elapsed), 1) if elapsed else None,
                        ram_total_bytes=memory.total_phys, ram_available_bytes=memory.avail_phys, ram_used_percent=memory.load)
            class ProcessMemory(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD)] + [(key, ctypes.c_size_t) for key in ("peak_working", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
            counters = ProcessMemory(); counters.cb = ctypes.sizeof(counters)
            ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                data["backend_rss_bytes"] = counters.working
            data["resource_metrics"] = "Win32 GlobalMemoryStatusEx / GetSystemTimes / GetProcessMemoryInfo"
        else:
            data["resource_metrics"] = "unverified: psutil is not installed"
    return {"status": "ready", "data": data, "source": "live OS/process counters"}


def _tools_probe():
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        executable = os.getenv(f"DANDY_{name.upper()}") or shutil.which(name)
        if executable and Path(executable).is_file():
            result = subprocess.run([executable, "-version"], capture_output=True, text=True, timeout=3, check=True)
            tools[name] = {"status": "ready", "path": executable, "version": result.stdout.splitlines()[0]}
        else:
            tools[name] = {"status": "unavailable", "path": executable}
    return {"status": "ready" if all(t["status"] == "ready" for t in tools.values()) else "unavailable", "data": tools, "source": "resolved executables + -version"}


def _storage_probe():
    from .social import brand_assets_status
    disk = shutil.disk_usage(PROJECT_ROOT)
    config = load_project_config()
    music = Path(config.get("intro_outro", {}).get("music_file", "./audio/jingles/phil_jim_theme.mp3"))
    if not music.is_absolute():
        music = PROJECT_ROOT / music
    music_required = bool(config.get("intro_outro", {}).get("enabled"))
    return {"status": "ready" if os.access(PROJECT_ROOT, os.W_OK) and disk.free > 1024**3 and (not music_required or music.is_file()) else "degraded",
            "source": "filesystem stat / disk_usage / access",
            "data": {"project_root": str(PROJECT_ROOT), "disk_total_bytes": disk.total, "disk_free_bytes": disk.free,
                     "writable": os.access(PROJECT_ROOT, os.W_OK), "intro_outro_music": str(music),
                     "music_exists": music.is_file(), "brand_assets": brand_assets_status()["assets"]}}


def _production_probe():
    from . import production
    rows = []
    for path in EPISODES_ROOT.glob("*/status.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append({"episode_id": path.parent.name, **{k: payload.get(k) for k in ("status", "updated_at", "error", "production_mode", "audio_file")}})
        except (OSError, ValueError) as exc:
            rows.append({"episode_id": path.parent.name, "status": "unavailable", "error": str(exc)})
    jobs = []
    for path in (EPISODES_ROOT / ".drafts" / "jobs").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            jobs.append({k: data.get(k) for k in ("job_id", "episode_id", "status", "updated_at", "error")})
        except (OSError, ValueError):
            pass
    return {"status": "ready", "source": "live generation ownership + persisted job/production records",
            "data": {"episodes": rows, "jobs": jobs[-20:], "active_generation_job": production._ACTIVE_GENERATION,
                     "progress_telemetry": "recorded section progress; audio task progress unverified"}}


async def _obs_probe():
    from ..services.obs.client import OBSClient
    client = OBSClient.from_runtime_config()
    result = await asyncio.wait_for(client.status(), timeout=4)
    return {"status": "ready", "data": result, "source": "authenticated OBS WebSocket read requests",
            "cameras": "unverified: OBS scene state does not prove camera frames"}


def _mixer_probe():
    from ..services.mixer import voicemeeter
    if voicemeeter.voicemeeterlib is None:
        return {"status": "unavailable", "error": str(voicemeeter.VOICEMEETER_IMPORT_ERROR), "source": "Voicemeeter Remote API import"}
    # Read-only Remote API; never change levels or routing from monitoring.
    return {"status": "ready", "data": voicemeeter.VoiceMeeterService().status(), "source": "live Voicemeeter Remote API"}


async def _measured(name, callback, asynchronous=False):
    started = time.monotonic()
    try:
        result = await callback() if asynchronous else await asyncio.to_thread(callback)
    except Exception as exc:
        result = {"status": "unavailable", "error": str(exc)[:600]}
    return name, {"checked_at": _now(), "source": name, **result, "latency_ms": round((time.monotonic() - started) * 1000)}


@router.get("/system/diagnostics")
async def diagnostics():
    cfg = load_qwen_tts_config()
    probes = [
        _measured("writer", _writer_probe), _measured("kokoro", _kokoro_probe),
        _measured("gpu", _gpu_probe), _measured("resources", _resources_probe),
        _measured("media_tools", _tools_probe), _measured("storage", _storage_probe),
        _measured("production", _production_probe), _measured("obs", _obs_probe, True),
        _measured("mixer", _mixer_probe),
    ]
    for name, key, suffix, is_json in [("qwen_bridge", "bridge_url", "/health", True),
                                      ("qwen_custom_voice", "custom_voice_url", "/config", True),
                                      ("qwen_operator_ui", "operator_ui_url", "/", False)]:
        url = str(cfg.get(key) or "").rstrip("/")
        if url:
            probes.append(_measured(name, lambda url=url, suffix=suffix, is_json=is_json: _http_probe(url + suffix, is_json)))
    checks = dict(await asyncio.gather(*probes))
    selected = str(load_project_config().get("tts", {}).get("primary_engine", "kokoro")).lower()
    required = ["writer", "kokoro" if selected == "kokoro" else "qwen_bridge", "media_tools", "storage"]
    ready = all(checks.get(key, {}).get("status") in ("ready", "reachable") for key in required)
    return {"checked_at": _now(), "status": "ready" if ready else "degraded", "selected_tts": selected,
            "readiness_scope": "dependencies; inference/synthesis and camera frames require output verification",
            "required_checks": required, "checks": checks,
            "voice_registry": load_voices_config(), "qwen_voice_registry": cfg.get("voices", {})}


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
            detail="Dandy production TTS must be either 'kokoro' or 'qwen'. No fallback engine is permitted.",
        )

    cfg_path = CONFIG_ROOT / "config.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    tts = dict(data.get("tts", {}))
    tts["primary_engine"] = selected
    tts["fallback_engine"] = "none"
    tts["allowed_engines"] = ["kokoro", "qwen"]
    data["tts"] = tts
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    load_project_config.cache_clear()

    return {
        "saved": True,
        "selected_engine": selected,
        "allowed_engines": ["kokoro", "qwen"],
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
        "allowed_engines": ["kokoro", "qwen"],
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
def preview_intro_outro(payload: Dict[str, Any] = Body(...)) -> Any:
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
