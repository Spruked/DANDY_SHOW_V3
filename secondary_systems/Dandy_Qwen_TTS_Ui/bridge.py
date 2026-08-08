from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from gradio_client import Client
from pydantic import BaseModel, Field


APP_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = APP_ROOT / "generated_audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SHOW_ROOT = APP_ROOT.parents[1]
SHOW_ROOT = Path(os.getenv("DANDY_SHOW_ROOT", str(DEFAULT_SHOW_ROOT)))
VOICES_CONFIG = SHOW_ROOT / "config" / "voices.json"
FFMPEG_BIN = (
    os.getenv("DANDY_FFMPEG")
    or str(SHOW_ROOT / "staging" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe")
)
FFPROBE_BIN = os.getenv("DANDY_FFPROBE") or str(Path(FFMPEG_BIN).with_name("ffprobe.exe"))

BACKEND_ORDER = [
    url.strip().rstrip("/")
    for url in os.getenv(
        "DANDY_QWEN_BACKENDS",
        "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033",
    ).split(",")
    if url.strip()
]

DEFAULT_CUSTOM_SPEAKERS = {
    "phil": "Ryan",
    "jim": "Eric",
    "announcer_male": "Ryan",
    "announcer_female": "Serena",
    "host": "Ryan",
    "guest": "Aiden",
}

MAX_CHUNK_CHARS = int(os.getenv("DANDY_QWEN_MAX_CHUNK_CHARS", "220"))
MAX_TEXT_CHARS = int(os.getenv("DANDY_QWEN_MAX_TEXT_CHARS", "2048"))
MAX_INSTRUCTION_CHARS = int(os.getenv("DANDY_QWEN_MAX_INSTRUCTION_CHARS", "1600"))
MAX_REFERENCE_AUDIO_SECONDS = float(os.getenv("DANDY_QWEN_MAX_REFERENCE_AUDIO_SECONDS", "30"))


class SynthesizeRequest(BaseModel):
    text: str
    speaker: str = "phil"
    voice: str | None = None
    emotion: str | None = None
    instruction: str | None = None
    language: str = "English"
    format: str = "mp3"
    sample_rate: int = 24000
    output_path: str | None = None
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_prompt: str | None = None
    use_xvec: bool = False
    speed: float | None = Field(default=None)


app = FastAPI(title="Dandy Qwen TTS Bridge")
_CLIENT_CACHE: dict[str, Client] = {}
_CLIENT_CACHE_LOCK = threading.RLock()


def _phase(event: str, **fields: Any) -> None:
    payload = {"event": event, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), **fields}
    try:
        print(f"[QWEN_BRIDGE_PHASE] {json.dumps(payload, ensure_ascii=False)}", flush=True)
    except Exception:
        print(f"[QWEN_BRIDGE_PHASE] {event} {fields}", flush=True)


def _normalize_url(url: str | None) -> str:
    return str(url or "").strip().rstrip("/")


def _backend_alive(url: str | None) -> bool:
    url = _normalize_url(url)
    if not url:
        return False
    try:
        with urlopen(f"{url}/config", timeout=0.45) as response:
            if response.status >= 500:
                return False
            payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
            return bool(payload.get("components") or payload.get("dependencies"))
    except (OSError, URLError, ValueError):
        return False


def _detect_backend() -> str:
    env_backend = _normalize_url(os.getenv("DANDY_QWEN_GRADIO_URL"))
    if env_backend and _backend_alive(env_backend):
        return env_backend

    for backend in BACKEND_ORDER:
        if _backend_alive(backend):
            return backend

    return env_backend or BACKEND_ORDER[0]


def _backend_mode(url: str) -> str:
    url = _normalize_url(url)
    if url.endswith(":8031"):
        return "custom"
    if url.endswith(":8032"):
        return "clone"
    if url.endswith(":8033"):
        return "design"
    return "unknown"


def _load_voices() -> dict[str, Any]:
    if not VOICES_CONFIG.exists():
        return {}
    return json.loads(VOICES_CONFIG.read_text(encoding="utf-8"))


def _voice_payload(speaker: str) -> dict[str, Any]:
    voices = _load_voices()
    return dict(voices.get(str(speaker or "").lower(), {}))


def _custom_speaker(payload: SynthesizeRequest) -> str:
    voice_payload = _voice_payload(payload.speaker)
    return str(
        voice_payload.get("qwen_custom_speaker")
        or DEFAULT_CUSTOM_SPEAKERS.get(payload.speaker.lower())
        or "Ryan"
    )


def _instruction(payload: SynthesizeRequest) -> str:
    voice_payload = _voice_payload(payload.speaker)
    instruction = str(
        payload.instruction
        or voice_payload.get("qwen_voice_instruction")
        or f"{payload.speaker}, {payload.emotion or 'natural'}, conversational studio voice"
    )
    return instruction[:MAX_INSTRUCTION_CHARS]


def _voice_prompt(payload: SynthesizeRequest) -> str:
    voice_payload = _voice_payload(payload.speaker)
    prompt = (
        payload.voice_prompt
        or voice_payload.get("qwen_voice_prompt")
        or os.getenv(f"DANDY_QWEN_PROMPT_{payload.speaker.upper()}")
        or ""
    )
    return str(prompt)


def _extract_audio_path(result: Any) -> str:
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
    else:
        first = result

    if isinstance(first, dict):
        path = first.get("path") or first.get("name")
    else:
        path = str(first) if first else ""

    if not path:
        raise RuntimeError(f"No audio path returned from Qwen backend: {result!r}")
    return path


def _clean_tts_text(text: str) -> str:
    cleaned = text.replace("\u2014", ", ").replace("\u2013", ", ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _split_long_piece(piece: str, max_chars: int) -> list[str]:
    if len(piece) <= max_chars:
        return [piece]

    chunks: list[str] = []
    current = ""
    for word in piece.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    text = _clean_tts_text(text)
    if len(text) <= max_chars:
        return [text]

    pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_piece(piece, max_chars))
            continue

        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks or [text]


def _audio_duration_seconds(path: str) -> float:
    result = subprocess.run(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip() or "0")


def _validate_reference_audio(path: str) -> None:
    ref_path = Path(path)
    if not ref_path.exists():
        raise HTTPException(status_code=400, detail=f"reference_audio does not exist: {ref_path}")
    duration = _audio_duration_seconds(str(ref_path))
    if duration > MAX_REFERENCE_AUDIO_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"reference_audio is {duration:.2f}s; maximum is {MAX_REFERENCE_AUDIO_SECONDS:.2f}s",
        )


def _target_path(payload: SynthesizeRequest, source_path: str) -> Path:
    if payload.output_path:
        target = Path(payload.output_path)
        return target if target.is_absolute() else (SHOW_ROOT / target).resolve()

    safe_speaker = "".join(ch.lower() if ch.isalnum() else "_" for ch in payload.speaker).strip("_") or "voice"
    suffix = ".mp3" if payload.format.lower() in {"mp3", "mpeg"} else Path(source_path).suffix or ".wav"
    return OUTPUT_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{safe_speaker}{suffix}"


def _copy_or_convert(source: str, target: Path, audio_format: str) -> None:
    source_path = Path(source)
    if not source_path.exists():
        raise RuntimeError(f"Qwen generated audio path missing: {source_path}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target_format = (audio_format or target.suffix.lstrip(".") or "mp3").lower()

    if source_path.suffix.lower() == target.suffix.lower():
        shutil.copyfile(source_path, target)
        return

    if target_format in {"mp3", "mpeg"}:
        subprocess.run(
            [FFMPEG_BIN, "-y", "-i", str(source_path), "-codec:a", "libmp3lame", "-q:a", "2", str(target)],
            check=True,
            capture_output=True,
        )
        return

    shutil.copyfile(source_path, target)


def _concat_audio(parts: list[Path], target: Path) -> None:
    if not parts:
        raise RuntimeError("No audio chunks to concatenate")
    if len(parts) == 1:
        shutil.copyfile(parts[0], target)
        return

    concat_file = target.with_suffix(".concat.txt")
    try:
        concat_file.write_text(
            "".join(f"file '{part.resolve().as_posix()}'\n" for part in parts),
            encoding="utf-8",
        )
        subprocess.run(
            [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-codec:a", "libmp3lame", "-q:a", "2", str(target)],
            check=True,
            capture_output=True,
        )
    finally:
        concat_file.unlink(missing_ok=True)


def _client(backend_url: str) -> Client:
    url = _normalize_url(backend_url)
    with _CLIENT_CACHE_LOCK:
        cached = _CLIENT_CACHE.get(url)
        if cached is not None:
            _phase("gradio_client_cache_hit", backend_url=url)
            return cached
        client = Client(url)
        _CLIENT_CACHE[url] = client
        return client


def _predict_audio_source(client: Client, mode: str, payload: SynthesizeRequest, text: str) -> Any:
    if mode == "custom":
        return client.predict(
            text=text,
            lang_disp=payload.language or "English",
            spk_disp=_custom_speaker(payload),
            instruct=_instruction(payload),
            api_name="/run_instruct",
        )

    if mode == "clone":
        prompt = _voice_prompt(payload)
        if prompt and Path(prompt).exists():
            return client.predict(
                file_obj=prompt,
                text=text,
                lang_disp=payload.language or "English",
                api_name="/load_prompt_and_gen",
            )
        if payload.reference_audio and payload.reference_text:
            _validate_reference_audio(payload.reference_audio)
            return client.predict(
                ref_aud=payload.reference_audio,
                ref_txt=payload.reference_text,
                use_xvec=payload.use_xvec,
                text=text,
                lang_disp=payload.language or "English",
                api_name="/run_voice_clone",
            )
        raise HTTPException(
            status_code=503,
            detail=(
                "VoiceClone/Base is live, but no qwen_voice_prompt or "
                "reference_audio/reference_text was supplied for this speaker."
            ),
        )

    raise HTTPException(status_code=503, detail=f"Backend mode {mode} is not production-routable")


@app.get("/health")
def health() -> dict[str, Any]:
    backend_url = _detect_backend()
    backend_ready = _backend_alive(backend_url)
    return {
        "status": "ok" if backend_ready else "degraded",
        "bridge": "dandy_qwen_tts",
        "backend_url": backend_url,
        "backend_mode": _backend_mode(backend_url),
        "backend_qwen_ready": backend_ready,
        "show_root": str(SHOW_ROOT),
        "limits": {
            "max_chunk_chars": MAX_CHUNK_CHARS,
            "max_text_chars": MAX_TEXT_CHARS,
            "max_instruction_chars": MAX_INSTRUCTION_CHARS,
            "max_reference_audio_seconds": MAX_REFERENCE_AUDIO_SECONDS,
        },
    }


@app.get("/voices")
def voices() -> dict[str, Any]:
    return {
        "backend_url": _detect_backend(),
        "voices": _load_voices(),
        "custom_speaker_defaults": DEFAULT_CUSTOM_SPEAKERS,
    }


@app.post("/synthesize")
def synthesize(payload: SynthesizeRequest) -> dict[str, Any]:
    _phase("request_received", speaker=payload.speaker, requested_format=payload.format, text_len=len(payload.text or ""))
    text = _clean_tts_text(payload.text)
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"text is {len(text)} characters; maximum request text is {MAX_TEXT_CHARS}. Split script lines before calling the bridge.",
        )

    backend_url = _detect_backend()
    _phase("backend_selected", backend_url=backend_url, backend_mode=_backend_mode(backend_url))
    if not _backend_alive(backend_url):
        raise HTTPException(status_code=503, detail=f"No live Qwen Gradio backend detected. Tried: {BACKEND_ORDER}")

    mode = _backend_mode(backend_url)
    _phase("gradio_client_create_start", backend_url=backend_url)
    client = _client(backend_url)
    _phase("gradio_client_created", backend_url=backend_url)

    try:
        text_chunks = _chunk_text(text)
        first_source = ""
        target_path: Path | None = None

        with tempfile.TemporaryDirectory(dir=str(OUTPUT_DIR)) as chunk_dir:
            chunk_paths: list[Path] = []
            for index, chunk in enumerate(text_chunks, start=1):
                predict_start = time.time()
                _phase("predict_started", chunk_index=index, chunk_count=len(text_chunks), chunk_len=len(chunk), mode=mode, api_name="/run_instruct" if mode == "custom" else ("/load_prompt_and_gen_or_run_voice_clone" if mode == "clone" else "unknown"))
                result = _predict_audio_source(client, mode, payload, chunk)
                _phase("predict_finished", chunk_index=index, elapsed_sec=round(time.time() - predict_start, 3))
                source_path = _extract_audio_path(result)
                _phase("source_audio_path", chunk_index=index, source_audio_path=source_path)
                first_source = first_source or source_path

                if len(text_chunks) == 1:
                    target_path = _target_path(payload, source_path)
                    _phase("copy_convert_started", chunk_index=index, source_audio_path=source_path, target_audio_path=str(target_path), target_format=payload.format)
                    _copy_or_convert(source_path, target_path, payload.format)
                    _phase("final_output_path", chunk_index=index, final_output_path=str(target_path))
                    break

                chunk_path = Path(chunk_dir) / f"chunk_{index:03d}.mp3"
                _phase("copy_convert_started", chunk_index=index, source_audio_path=source_path, target_audio_path=str(chunk_path), target_format="mp3")
                _copy_or_convert(source_path, chunk_path, "mp3")
                chunk_paths.append(chunk_path)

            if len(text_chunks) > 1:
                target_path = _target_path(payload, first_source or "output.mp3")
                _phase("copy_convert_started", chunk_index=0, source_audio_path="concat", target_audio_path=str(target_path), target_format="mp3")
                _concat_audio(chunk_paths, target_path)
                _phase("final_output_path", chunk_index=0, final_output_path=str(target_path))
    except HTTPException:
        raise
    except Exception as exc:
        _phase("synthesize_error", error_type=type(exc).__name__, error=str(exc))
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc

    _phase("response_returned", final_output_path=str(target_path), backend_url=backend_url, backend_mode=mode, chunks=len(_chunk_text(text)))
    return {
        "audio_file": str(target_path),
        "path": str(target_path),
        "format": target_path.suffix.lstrip(".") or payload.format,
        "engine": "qwen",
        "backend_url": backend_url,
        "backend_mode": mode,
        "speaker": payload.speaker,
        "voice": payload.voice or _custom_speaker(payload),
        "chunks": len(_chunk_text(text)),
    }
