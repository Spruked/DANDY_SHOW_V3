from __future__ import annotations

import socket
import subprocess
import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..core.paths import PROJECT_ROOT


router = APIRouter(prefix="/qwen-studio", tags=["qwen-studio"])

_QWEN_ROOT = PROJECT_ROOT / "secondary_systems" / "Dandy_Qwen_TTS_Ui"
_QWEN_SCRIPT = _QWEN_ROOT / "scripts" / "Start-QwenTTSMode.ps1"
_QWEN_STOP_SCRIPT = _QWEN_ROOT / "scripts" / "Stop-QwenTTSModels.ps1"

_MODE_CONFIG: Dict[str, Dict[str, Any]] = {
    "custom": {
        "label": "CustomVoice",
        "port": 8031,
        "url": "http://127.0.0.1:8031",
        "checkpoint": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "description": "Built-in Qwen speakers and instruction-driven delivery.",
    },
    "clone": {
        "label": "Voice Clone",
        "port": 8032,
        "url": "http://127.0.0.1:8032",
        "checkpoint": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "description": "Reference-audio voice cloning and reusable voice prompts.",
    },
    "design": {
        "label": "VoiceDesign",
        "port": 8033,
        "url": "http://127.0.0.1:8033",
        "checkpoint": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "description": "Natural-language voice design.",
    },
}

_launch_lock = threading.Lock()
_launch_process: subprocess.Popen | None = None
_launch_mode: str | None = None
_launch_error: str | None = None


def _port_open(port: int, timeout: float = 0.20) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _validate_scripts() -> None:
    if not _QWEN_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Qwen mode launcher not found: {_QWEN_SCRIPT}")
    if not _QWEN_STOP_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Qwen stop launcher not found: {_QWEN_STOP_SCRIPT}")


def _launch_busy() -> bool:
    if _launch_process is None:
        return False
    return _launch_process.poll() is None


def _stop_existing_locked() -> None:
    """Stop any active/loading Qwen model before switching checkpoints.

    The PowerShell launcher stays alive while it waits for the selected Gradio
    listener to bind. Terminating only that launcher is not enough because the
    Python child may still be loading CUDA weights. Stop-QwenTTSModels.ps1
    kills both bound listeners and in-flight qwen_tts.cli.demo children.
    """
    global _launch_process, _launch_mode, _launch_error

    if _launch_process is not None and _launch_process.poll() is None:
        try:
            _launch_process.terminate()
            _launch_process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                _launch_process.kill()
            except OSError:
                pass

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_QWEN_STOP_SCRIPT),
        ],
        cwd=str(_QWEN_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creation_flags(),
        timeout=15,
        check=False,
    )
    if completed.returncode not in (0, None):
        raise RuntimeError(f"Qwen stop script exited with code {completed.returncode}")

    _launch_process = None
    _launch_mode = None
    _launch_error = None


def _status_payload() -> Dict[str, Any]:
    modes: Dict[str, Any] = {}
    active_modes = []

    for mode, cfg in _MODE_CONFIG.items():
        ready = _port_open(int(cfg["port"]))
        if ready:
            active_modes.append(mode)
        modes[mode] = {
            **cfg,
            "ready": ready,
        }

    launcher_busy = _launch_busy()
    launcher_mode = _launch_mode if launcher_busy else None

    return {
        "available": _QWEN_SCRIPT.exists() and _QWEN_STOP_SCRIPT.exists(),
        "root": str(_QWEN_ROOT),
        "modes": modes,
        "active_modes": active_modes,
        "active_mode": active_modes[0] if len(active_modes) == 1 else None,
        "multiple_modes_active": len(active_modes) > 1,
        "launcher": {
            "busy": launcher_busy,
            "mode": launcher_mode,
            "error": _launch_error,
        },
        "gpu_policy": "one_qwen_model_at_a_time",
    }


@router.get("/status")
def qwen_studio_status() -> Dict[str, Any]:
    return _status_payload()


@router.post("/mode/{mode}/start")
def qwen_studio_start(mode: str) -> Dict[str, Any]:
    global _launch_process, _launch_mode, _launch_error

    mode = str(mode or "").strip().lower()
    if mode not in _MODE_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown Qwen mode: {mode}")

    _validate_scripts()

    selected = _MODE_CONFIG[mode]
    if _port_open(int(selected["port"])):
        return {
            "launch_requested": False,
            "already_ready": True,
            "mode": mode,
            "url": selected["url"],
            "status": _status_payload(),
        }

    with _launch_lock:
        if _launch_busy() and _launch_mode == mode:
            return {
                "launch_requested": False,
                "already_starting": True,
                "mode": mode,
                "status": _status_payload(),
            }

        try:
            # Switching modes is an explicit request to unload the current
            # checkpoint, even if it is still loading and has not bound a port.
            active_other_mode = any(
                name != mode and _port_open(int(cfg["port"]))
                for name, cfg in _MODE_CONFIG.items()
            )
            if _launch_busy() or active_other_mode:
                _stop_existing_locked()

            _launch_error = None
            _launch_mode = mode
            _launch_process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(_QWEN_SCRIPT),
                    "-Mode",
                    mode,
                ],
                cwd=str(_QWEN_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creation_flags(),
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            _launch_process = None
            _launch_mode = None
            _launch_error = str(exc)
            raise HTTPException(status_code=500, detail=f"Could not start Qwen {mode}: {exc}") from exc

    return {
        "launch_requested": True,
        "mode": mode,
        "port": selected["port"],
        "url": selected["url"],
        "status": _status_payload(),
    }


@router.post("/stop")
def qwen_studio_stop() -> Dict[str, Any]:
    _validate_scripts()

    with _launch_lock:
        try:
            _stop_existing_locked()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(status_code=500, detail=f"Could not stop Qwen models: {exc}") from exc

    return {
        "stop_requested": True,
        "status": _status_payload(),
    }
