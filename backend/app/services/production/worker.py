"""Audio production from imported and explicitly approved episode scripts."""

import asyncio
from .engine_statistics import summarize_engines
from ...core.safety import atomic_json, contained_path, validate_id
import copy
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from uuid import uuid4
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydub import AudioSegment

# ── Hardened modules ──
from .context_builder import build_rich_context
from .quality_guard import QualityDecision, ScriptQualityGuard
from .rhythm import RhythmState
from .script_expander import ScriptExpander
from .script_seed import generate_seed_script
from .intro_outro import wrap_episode_audio
from .production_manifest import EDITOR_VERSION, checked_take_path, file_hash, load_manifest, save_manifest, validate_takes
from .sfx import apply_sfx_events

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    primary_engine: str
    fallback_engine: str
    device: str


class HardenedPodcastWorker:
    """Render saved scripts with Qwen takes, mastering, manifests and audio QC."""

    def __init__(self, base_path: Optional[Path] = None):
        # Import project-specific modules here to avoid hard deps
        try:
            from ...core.paths import PROJECT_ROOT
            from ...core.settings import load_project_config, load_qwen_tts_config, load_voices_config
            from .audio_post_processor import FFmpegPostProcessor
        except ImportError:
            # Fallback for standalone testing
            from backend.app.core.paths import PROJECT_ROOT
            from backend.app.core.settings import load_project_config, load_qwen_tts_config, load_voices_config
            from backend.app.services.production.audio_post_processor import FFmpegPostProcessor

        self.base_path = Path(base_path or PROJECT_ROOT).resolve()
        self.project_config = load_project_config()
        self.voices_config = load_voices_config()
        self.qwen_tts_config = load_qwen_tts_config()
        spoken_wpm = max(1, int(self.project_config.get("production", {}).get("spoken_wpm", 90)))
        self.runtime = WorkerRuntime(
            primary_engine=self.project_config.get("tts", {}).get("primary_engine", "kokoro"),
            fallback_engine=self.project_config.get("tts", {}).get("fallback_engine", "edge"),
            device=self.project_config.get("tts", {}).get("preferred_device", "cpu"),
        )
        self.post_processor = FFmpegPostProcessor(self.base_path, logger)
        self.quality_guard = ScriptQualityGuard(words_per_minute=spoken_wpm)



    # ═════════════════════════════════════════════════════════════════
    # STAGE 1: SCRIPT GENERATION (Hardened)
    # ═════════════════════════════════════════════════════════════════

    def generate_script(
        self,
        episode_config: Dict[str, Any],
        line_callback: Optional[Callable] = None,
        max_retries: int = 2,
    ) -> List[Dict[str, Any]]:
        raise RuntimeError("Episode writing is archived. Build a document context package and import an externally written script.")








    def _strip_spoken_speaker_prefix(self, text: str, speaker: str) -> str:
        cleaned = text.strip().strip('"').strip("'").strip()
        cleaned = re.sub(
            r"^(phil|jim|host|guest|narrator|both|speaker)\s*[:\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = re.sub(
            rf"^{re.escape(speaker)}\s*[:\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned

    # ═════════════════════════════════════════════════════════════════
    # STAGE 2: AUDIO PRODUCTION (Unchanged from original)
    # ═════════════════════════════════════════════════════════════════

    def produce_episode(
        self,
        episode_id: str,
        title: str,
        topic: str,
        script_lines: List[Dict[str, Any]],
        progress_callback: Optional[Callable] = None,
        approved_production: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Produce audio from script — unchanged logic, just called with validated script."""
        if approved_production is not None:
            return self._produce_approved_episode(episode_id, title, topic, script_lines,
                                                 approved_production, progress_callback)
        if not script_lines:
            raise ValueError("script_lines are required for production")

        episode_dir = contained_path(self.base_path / "episodes", validate_id(episode_id))
        episode_dir.mkdir(parents=True, exist_ok=True)
        published_audio_path = episode_dir / "audio.mp3"
        transcript_path = episode_dir / "transcript.json"
        metadata_path = episode_dir / "production_metadata.json"
        (self.base_path / "staging").mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(self.base_path / "staging")) as temp_dir:
            staging_dir = Path(temp_dir)
            final_audio_path = staging_dir / "audio.mp3"
            raw_segments_dir = staging_dir / "segments"
            raw_segments_dir.mkdir(parents=True, exist_ok=True)

            segment_payloads = self._synthesize_segments(script_lines, raw_segments_dir, episode_id, progress_callback)
            if progress_callback:
                progress_callback({"stage": "mixing", "progress": 0.9})
            raw_mix_path = staging_dir / f"{episode_id}_raw_mix.mp3"
            self._concatenate_segments(segment_payloads, raw_mix_path)

            # ── SFX injection ────────────────────────────────────────────
            sfx_cfg = self.project_config.get("sfx", {})
            if sfx_cfg.get("enabled", False) and raw_mix_path.exists():
                try:
                    sfx_dir = self.base_path / "audio" / "sfx"
                    episode_audio = AudioSegment.from_file(str(raw_mix_path))
                    episode_audio = apply_sfx_events(episode_audio, sfx_cfg, sfx_dir)
                    episode_audio.export(str(raw_mix_path), format="mp3", bitrate="192k")
                    logger.info("SFX applied to %s", episode_id)
                except Exception as exc:
                    logger.warning("SFX injection failed (continuing without): %s", exc)

            processing_result: Dict[str, Any]
            try:
                processing_result = self.post_processor.process_episode(
                    input_file=raw_mix_path,
                    output_file=final_audio_path,
                    voice_profile="phil_jim_mix",
                )
            except Exception as exc:
                raise RuntimeError("Audio post-processing failed; previous production was preserved") from exc
            if processing_result.get("compliant") is False:
                raise RuntimeError("Audio failed loudness/peak acceptance; previous production was preserved")

            # ── Intro / Outro wrap ──────────────────────────────────────
            io_cfg = self.project_config.get("intro_outro", {})
            if io_cfg.get("enabled", False) and final_audio_path.exists():
                try:
                    wrapped_path = staging_dir / "audio_wrapped.mp3"
                    wrap_episode_audio(
                        episode_audio_path=final_audio_path,
                        output_path=wrapped_path,
                        cfg=io_cfg,
                        base_path=self.base_path,
                        topic=topic,
                    )
                    final_audio_path.unlink()
                    wrapped_path.rename(final_audio_path)
                    processing_result = self._master_wrapped_audio(final_audio_path)
                    processing_result["intro_outro"] = "wrapped"
                    logger.info("Intro/outro applied to %s", episode_id)
                except Exception as exc:
                    if self.qwen_tts_config.get("production", {}).get("required_engine") == "qwen":
                        raise RuntimeError("Required Qwen intro/outro failed") from exc
                    logger.warning("Intro/outro wrap failed (episode audio kept clean): %s", exc)
                    processing_result["intro_outro"] = f"failed: {exc}"

            transcript_payload = {
                "episode_id": episode_id,
                "title": title,
                "topic": topic,
                "created_at": datetime.now().isoformat(),
                "script": script_lines,
                "segments": segment_payloads,
            }
            atomic_json(transcript_path, transcript_payload)

            metadata = {
                "episode_id": episode_id,
                "title": title,
                "topic": topic,
                "audio_file": str(published_audio_path),
                "segment_count": len(segment_payloads),
                **self.summarize_engines(segment_payloads),
                "generated_at": datetime.now().isoformat(),
                "processing": processing_result,
                "voice_assignments": {
                    "phil": {
                        "primary": self.voices_config.get("phil", {}).get("primary_voice"),
                        "fallback": self.voices_config.get("phil", {}).get("fallback_voice"),
                    },
                    "jim": {
                        "primary": self.voices_config.get("jim", {}).get("primary_voice"),
                        "fallback": self.voices_config.get("jim", {}).get("fallback_voice"),
                    },
                },
            }
            if not final_audio_path.is_file() or not final_audio_path.stat().st_size:
                raise RuntimeError("Production produced no nonempty final audio")
            self._check_cancelled()
            os.replace(final_audio_path, published_audio_path)
            if "output_file" in processing_result:
                processing_result["output_file"] = str(published_audio_path)
            atomic_json(metadata_path, metadata)

        return {
            "episode_id": episode_id,
            "audio_file": str(published_audio_path),
            "transcript": script_lines,
            "metadata": metadata,
        }

    def _produce_approved_episode(
        self,
        episode_id: str,
        title: str,
        topic: str,
        script_lines: List[Dict[str, Any]],
        approved_production: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Render only a frozen, explicitly approved production version."""
        if not script_lines:
            raise ValueError("script_lines are required for production")
        if not approved_production or not approved_production.get("approved_version_id"):
            raise ValueError("Production requires an approved production version")
        if approved_production.get("script") != script_lines:
            raise ValueError("Synthesis input differs from the approved production copy")
        stable_plan = json.dumps({"script": script_lines,
                                  "media_cues": approved_production.get("media_cues", [])},
                                 sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        approved_hash = hashlib.sha256(stable_plan.encode("utf-8")).hexdigest()
        if approved_hash != approved_production.get("production_copy_hash"):
            raise ValueError("Approved production copy hash does not match its contents")

        episode_dir = contained_path(self.base_path / "episodes", validate_id(episode_id))
        episode_dir.mkdir(parents=True, exist_ok=True)
        final_audio_path = episode_dir / "audio.mp3"
        transcript_path = episode_dir / "transcript.json"
        metadata_path = episode_dir / "production_metadata.json"
        (self.base_path / "staging").mkdir(parents=True, exist_ok=True)
        run_id = uuid4().hex
        source_hash = str(approved_production.get("canonical_source_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise RuntimeError("Approved production version has no canonical source hash")
        cue_hash = hashlib.sha256(json.dumps(approved_production.get("media_cues", []),
                                             sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
        takes_dir = episode_dir / "takes" / run_id
        takes_dir.mkdir(parents=True, exist_ok=False)

        with tempfile.TemporaryDirectory(dir=str(self.base_path / "staging")) as temp_dir:
            staging_dir = Path(temp_dir)
            candidate_audio_path = staging_dir / "audio.mp3"
            segment_payloads = self._synthesize_segments(script_lines, takes_dir, episode_id, progress_callback)
            raw_mix_path = staging_dir / f"{episode_id}_raw_mix.mp3"
            self._concatenate_segments(segment_payloads, raw_mix_path,
                                       media_cues_override=approved_production.get("media_cues", []))

            # ── SFX injection ────────────────────────────────────────────
            sfx_cfg = self.project_config.get("sfx", {})
            if sfx_cfg.get("enabled", False) and raw_mix_path.exists():
                try:
                    sfx_dir = self.base_path / "audio" / "sfx"
                    episode_audio = AudioSegment.from_file(str(raw_mix_path))
                    episode_audio = apply_sfx_events(episode_audio, sfx_cfg, sfx_dir)
                    episode_audio.export(str(raw_mix_path), format="mp3", bitrate="192k")
                    logger.info("SFX applied to %s", episode_id)
                except Exception as exc:
                    logger.warning("SFX injection failed (continuing without): %s", exc)

            processing_result: Dict[str, Any]
            try:
                processing_result = self.post_processor.process_episode(
                    input_file=raw_mix_path,
                    output_file=candidate_audio_path,
                    voice_profile="phil_jim_mix",
                )
            except Exception as exc:
                raise RuntimeError("Audio post-processing failed; previous production was preserved") from exc
            if processing_result.get("compliant") is False:
                raise RuntimeError("Audio failed loudness/peak acceptance; previous production was preserved")

            # ── Intro / Outro wrap ──────────────────────────────────────
            io_cfg = self.project_config.get("intro_outro", {})
            if io_cfg.get("enabled", False) and candidate_audio_path.exists():
                try:
                    wrapped_path = staging_dir / "audio_wrapped.mp3"
                    wrap_episode_audio(
                        episode_audio_path=candidate_audio_path,
                        output_path=wrapped_path,
                        cfg=io_cfg,
                        base_path=self.base_path,
                        topic=topic,
                    )
                    os.replace(wrapped_path, candidate_audio_path)
                    processing_result = self._master_wrapped_audio(candidate_audio_path)
                    processing_result["intro_outro"] = "wrapped"
                    logger.info("Intro/outro applied to %s", episode_id)
                except Exception as exc:
                    raise RuntimeError(f"Configured intro/outro failed: {exc}. Fix its assets/runtime or explicitly disable it before production.") from exc

            current_plan_hash = hashlib.sha256(json.dumps(
                {"script": approved_production.get("script"),
                 "media_cues": approved_production.get("media_cues", [])},
                sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            if current_plan_hash != approved_hash:
                raise RuntimeError("Approved production plan changed during production; existing master was preserved")
            from .production_lifecycle import current_approval
            live_approval, live_version_id = current_approval(episode_id)
            if (live_version_id != approved_production.get("approved_version_id")
                    or live_approval.get("production_copy_hash") != approved_hash):
                raise RuntimeError("Approval became stale during production; existing master was preserved")
            manifest = self._build_production_manifest(
                episode_id, episode_dir, script_lines, segment_payloads, run_id, source_hash, topic,
                approved_production,
            )
            manifest["media_cues_hash"] = cue_hash
            manifest["processing"] = copy.deepcopy(processing_result)
            validate_takes(episode_dir, manifest["segments"])
            if final_audio_path.is_file():
                previous_master = episode_dir / f"audio.before_{run_id}.mp3"
                shutil.copy2(final_audio_path, previous_master)
                previous_manifest = episode_dir / "production_manifest.json"
                if previous_manifest.is_file():
                    shutil.copy2(previous_manifest, episode_dir / f"production_manifest.before_{run_id}.json")
            self._check_cancelled()
            previous = staging_dir / "previous_master.mp3"
            if final_audio_path.is_file():
                shutil.copy2(final_audio_path, previous)
            try:
                os.replace(candidate_audio_path, final_audio_path)
                save_manifest(episode_dir, manifest)
            except Exception:
                if previous.is_file():
                    os.replace(previous, final_audio_path)
                else:
                    final_audio_path.unlink(missing_ok=True)
                raise

            transcript_payload = {
                "episode_id": episode_id,
                "title": title,
                "topic": topic,
                "created_at": datetime.now().isoformat(),
                "script": script_lines,
                "segments": segment_payloads,
            }
            transcript_path.write_text(json.dumps(transcript_payload, indent=2), encoding="utf-8")

            metadata = {
                "episode_id": episode_id,
                "title": title,
                "topic": topic,
                "audio_file": str(final_audio_path),
                "segment_count": len(segment_payloads),
                "generated_at": datetime.now().isoformat(),
                "processing": processing_result,
                "voice_assignments": {
                    "phil": {
                        "primary": self.voices_config.get("phil", {}).get("primary_voice"),
                        "fallback": self.voices_config.get("phil", {}).get("fallback_voice"),
                    },
                    "jim": {
                        "primary": self.voices_config.get("jim", {}).get("primary_voice"),
                        "fallback": self.voices_config.get("jim", {}).get("fallback_voice"),
                    },
                },
            }
            processing_result["output_file"] = str(final_audio_path)
            metadata.update(summarize_engines(segment_payloads))
            atomic_json(metadata_path, metadata)

        return {
            "episode_id": episode_id,
            "audio_file": str(final_audio_path),
            "transcript": script_lines,
            "metadata": metadata,
        }

    summarize_engines = staticmethod(summarize_engines)

    def _build_production_manifest(
        self, episode_id: str, episode_path: Path, script_lines: List[Dict[str, Any]],
        audio_segments: List[Dict[str, Any]], run_id: str, source_hash: str, topic: str,
        approved_production: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        lines = []
        for idx, line in enumerate(script_lines, start=1):
            chunks = [item for item in audio_segments if item["line_index"] == idx]
            if not chunks:
                continue
            speaker = self._normalize_speaker(str(line.get("speaker", "phil")))
            ad_id = line.get("ad_id")
            production_line_id = str(line.get("production_line_id") or f"production_line_{idx:04d}")
            source_text = str(line.get("original_text", line.get("text", "")))
            spoken_text = str(line.get("spoken_text") or line.get("text", ""))
            lines.append({
                "segment_id": production_line_id, "line_index": idx,
                "production_line_id": production_line_id,
                "source_canonical_line_id": line.get("source_canonical_line_id"),
                "canonical_version_id": (approved_production or {}).get("canonical_version_id"),
                "original_speaker": line.get("speaker"), "production_speaker": speaker,
                "original_text": source_text,
                "production_text": spoken_text, "dialogue_text": str(line.get("text", "")),
                "spoken_text": spoken_text, "pronunciation": line.get("pronunciation", ""),
                "editorial_action": "APPROVED_PRODUCTION_COPY",
                "before_after_diff": {"before": source_text, "after": line.get("text")}
                if source_text != line.get("text") else None,
                "delivery": {"emotion": line.get("emotion", "neutral"),
                             "producer_mode": line.get("producer_mode", ""),
                             "delivery_notes": line.get("delivery_notes", ""),
                             "pause_after": float(line.get("pause_after", 0.4))},
                "audio": {"take": 1, "chunks": [self._manifest_chunk(episode_path, item, 1) for item in chunks]},
                "music": None, "fx": line.get("production_cues", []), "visual": None, "ad": ad_id,
            })
        return {
            "episode_id": episode_id, "script_hash": source_hash,
            "canonical_version_id": (approved_production or {}).get("canonical_version_id"),
            "approved_version_id": (approved_production or {}).get("approved_version_id"),
            "production_copy_hash": (approved_production or {}).get("production_copy_hash"),
            "editor_run_id": (approved_production or {}).get("draft_id", run_id),
            "production_run_id": run_id, "editor_version": EDITOR_VERSION,
            "editor_status": "approved",
            "directives": copy.deepcopy((approved_production or {}).get("media_cues", [])),
            "created_at": datetime.now().isoformat(), "topic": topic,
            "segments": lines,
            "global_cues": {"intro_outro": copy.deepcopy(self.project_config.get("intro_outro", {})),
                            "sfx": copy.deepcopy(self.project_config.get("sfx", {}))},
        }

    @staticmethod
    def _manifest_chunk(episode_path: Path, item: Dict[str, Any], take: int) -> Dict[str, Any]:
        audio_path = Path(item["audio_file"]).resolve()
        chunk_index = int(item.get("chunk_index", 1))
        return {
            "asset_id": f"tts_line_{item['line_index']:03d}_chunk_{chunk_index:02d}_take_{take}",
            "chunk_index": chunk_index, "chunk_count": int(item.get("chunk_count", 1)),
            "text": item["text"], "path": audio_path.relative_to(episode_path.resolve()).as_posix(),
            "duration_ms": round(float(item["duration_seconds"]) * 1000),
            "hash": file_hash(audio_path), "engine": item["engine"],
            "voice_name": item.get("voice_name", ""), "pause_after": item["pause_after"],
        }

    def regenerate_production_line(
        self, episode_id: str, segment_id: str, reason: str,
        text_change: Optional[str] = None,
        revision_id: Optional[str] = None,
        approved_production: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Synthesize one line only, then rebuild the master from saved takes."""
        episode_path = self.base_path / "episodes" / episode_id
        manifest = load_manifest(episode_path)
        if not manifest:
            raise ValueError("This production has no saved line takes; produce it once with the new pipeline first")
        if not approved_production or manifest.get("approved_version_id") != approved_production.get("approved_version_id"):
            raise ValueError("Line regeneration requires the production's current approved version")
        if approved_production.get("production_copy_hash") != manifest.get("production_copy_hash"):
            raise ValueError("Approved production copy differs from the rendered master")
        if text_change is not None:
            raise ValueError("Dialogue changes require a new production editor draft and approval")
        segments = manifest["segments"]
        validate_takes(episode_path, segments)
        target = next((item for item in segments if item.get("segment_id") == segment_id), None)
        if target is None:
            raise ValueError(f"Unknown production segment: {segment_id}")
        if any(chunk.get("engine") != "qwen" for chunk in target["audio"]["chunks"]):
            raise ValueError("Only Qwen dialogue lines can be regenerated; saved ads use asset replacement")
        script_lines = approved_production.get("script", [])
        line_index = int(target["line_index"])
        saved_line = next((item for item in script_lines
                           if item.get("production_line_id") == target.get("production_line_id")), None)
        if saved_line is None:
            raise ValueError("Production segment is absent from the approved production copy")
        speaker = self._normalize_speaker(str(saved_line.get("speaker", "phil")))
        if speaker != self._normalize_speaker(str(target["original_speaker"])):
            raise ValueError("Production segment speaker no longer matches the saved script")

        previous_text = str(target["production_text"])
        new_text = previous_text
        if not new_text:
            raise ValueError("A production line cannot be empty")
        take = int(target["audio"]["take"]) + 1
        revision_id = revision_id or uuid4().hex
        take_dir = episode_path / "takes" / revision_id
        take_dir.mkdir(parents=True, exist_ok=False)
        line = {**saved_line, "text": new_text,
                "emotion": target["delivery"].get("emotion", "neutral"),
                "producer_mode": target["delivery"].get("producer_mode", ""),
                "pause_after": target["delivery"].get("pause_after", 0.4)}
        new_chunks = self._synthesize_segments([line], take_dir, episode_id)
        for chunk in new_chunks:
            chunk["line_index"] = line_index
        new_segment = copy.deepcopy(target)
        previous_audio = copy.deepcopy(target["audio"])
        history = previous_audio.pop("take_history", [])
        new_segment["audio"] = {
            "take": take,
            "chunks": [self._manifest_chunk(episode_path, item, take) for item in new_chunks],
            "take_history": [*history, previous_audio],
        }
        if new_text != previous_text:
            new_segment["production_text"] = new_text
            new_segment["editorial_action"] = "PERFORM"
            new_segment["before_after_diff"] = {"before": previous_text, "after": new_text}
        revised = copy.deepcopy(manifest)
        revised["segments"] = [new_segment if item["segment_id"] == segment_id else item for item in segments]
        revised["editor_run_id"] = revision_id
        revised["revised_at"] = datetime.now().isoformat()
        validate_takes(episode_path, revised["segments"])

        staging_root = self.base_path / "staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(staging_root)) as temp_dir:
            staging_dir = Path(temp_dir)
            audio_items = self._flatten_manifest_audio(episode_path, revised["segments"])
            candidate_path = staging_dir / "audio.mp3"
            processing = self._assemble_revision_audio(
                audio_items, candidate_path, staging_dir, episode_id,
                str(manifest.get("topic", "")), manifest.get("global_cues", {}),
                approved_production.get("media_cues", []),
            )
            from .production_lifecycle import current_approval
            current_approval(episode_id)
            processing["output_file"] = str(episode_path / "audio.mp3")
            revised["processing"] = copy.deepcopy(processing)
            final_path = episode_path / "audio.mp3"
            backup_path = staging_dir / "previous_master.mp3"
            if final_path.is_file():
                shutil.copy2(final_path, backup_path)
                shutil.copy2(backup_path, episode_path / f"audio.before_revision_{revision_id}.mp3")
            previous_manifest = episode_path / "production_manifest.json"
            if previous_manifest.is_file():
                shutil.copy2(previous_manifest, episode_path / f"production_manifest.before_revision_{revision_id}.json")
            try:
                os.replace(candidate_path, final_path)
                save_manifest(episode_path, revised)
            except Exception:
                if backup_path.is_file():
                    os.replace(backup_path, final_path)
                raise
        result = {"episode_id": episode_id, "segment_id": segment_id,
                  "revision_id": revision_id, "take": take, "audio_file": str(final_path),
                  "processing": processing}
        logger.info("Production line regenerated: episode=%s segment=%s take=%s", episode_id, segment_id, take)
        return result

    def _flatten_manifest_audio(self, episode_path: Path, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        audio_items = []
        for segment in segments:
            chunks = segment["audio"]["chunks"]
            for chunk in chunks:
                audio_items.append({
                    "audio_file": str(checked_take_path(episode_path, chunk["path"])),
                    "pause_after": float(chunk["pause_after"]),
                    "duration_seconds": float(chunk["duration_ms"]) / 1000,
                    "line_index": int(segment["line_index"]),
                })
        return audio_items

    def _assemble_revision_audio(
        self, audio_items: List[Dict[str, Any]], output_path: Path, staging_dir: Path,
        episode_id: str, topic: str, global_cues: Dict[str, Any],
        media_cues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raw_mix_path = staging_dir / f"{episode_id}_raw_mix.mp3"
        self._concatenate_segments(audio_items, raw_mix_path, media_cues_override=media_cues or [])
        sfx_cfg = global_cues.get("sfx", {})
        if sfx_cfg.get("enabled", False):
            try:
                audio = AudioSegment.from_file(str(raw_mix_path))
                audio = apply_sfx_events(audio, sfx_cfg, self.base_path / "audio" / "sfx")
                audio.export(str(raw_mix_path), format="mp3", bitrate="192k").close()
            except Exception as exc:
                logger.warning("SFX injection failed during line revision: %s", exc)
        try:
            processing = self.post_processor.process_episode(
                input_file=raw_mix_path, output_file=output_path, voice_profile="phil_jim_mix"
            )
        except Exception as exc:
            raise RuntimeError("Revision post-processing failed; previous production was preserved") from exc
        if processing.get("compliant") is False:
            raise RuntimeError("Revision failed loudness/peak acceptance; previous production was preserved")
        io_cfg = global_cues.get("intro_outro", {})
        if io_cfg.get("enabled", False):
            wrapped_path = staging_dir / "audio_wrapped.mp3"
            wrap_episode_audio(
                episode_audio_path=output_path, output_path=wrapped_path,
                cfg=io_cfg, base_path=self.base_path, topic=topic,
            )
            os.replace(wrapped_path, output_path)
            processing = self._master_wrapped_audio(output_path)
            processing["intro_outro"] = "wrapped"
        return processing

    # Maps non-canonical speaker keys → voices_config key
    _SPEAKER_NORM: Dict[str, str] = {
        "intro_male":       "announcer_male",
        "intro_female":     "announcer_female",
        "announcer":        "announcer_male",
        "announcer_m":      "announcer_male",
        "announcer_f":      "announcer_female",
        "host":             "host",
        "guest":            "guest",
    }

    def _normalize_speaker(self, raw: str) -> str:
        """Map any speaker label to a key that exists in voices_config."""
        s = raw.lower().strip()
        if s in self.voices_config:
            return s
        normalized = self._SPEAKER_NORM.get(s)
        if normalized and normalized in self.voices_config:
            return normalized
        raise RuntimeError(f"Unknown speaker '{raw}'; register its voice before production")

    _TTS_MAX_CHARS = 220

    @classmethod
    def _split_for_tts(cls, text: str, max_chars: int = _TTS_MAX_CHARS) -> List[str]:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return []
        if len(cleaned) <= max_chars:
            return [cleaned]

        pieces = re.split(r"(?<=[.!?;:])\s+", cleaned)
        chunks: List[str] = []
        current = ""

        def flush(part: str) -> None:
            part = part.strip()
            if part:
                chunks.append(part)

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) > max_chars:
                flush(current)
                current = ""
                chunks.extend(cls._split_long_phrase(piece, max_chars))
                continue
            candidate = f"{current} {piece}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                flush(current)
                current = piece

        flush(current)
        return chunks

    @staticmethod
    def _split_long_phrase(text: str, max_chars: int) -> List[str]:
        chunks: List[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = word
        if current:
            chunks.append(current)
        return chunks

    def _synthesize_segments(self, script_lines: List[Dict[str, Any]], output_dir: Path, episode_id: str, progress_callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        segment_index = 0
        for idx, line in enumerate(script_lines, start=1):
            speaker = self._normalize_speaker(str(line.get("speaker", "phil")))
            text = str(line.get("spoken_text") or line.get("text", "")).strip()
            if not line.get("is_ad"):
                text = self._strip_spoken_speaker_prefix(text=text, speaker=speaker)
            if not text:
                continue

            chunks = self._split_for_tts(text)
            for chunk_idx, chunk_text in enumerate(chunks, start=1):
                segment_index += 1
                output_path = output_dir / f"{episode_id}_{segment_index:03d}_{speaker}.mp3"
                self._check_cancelled()
                engine_used = self._synthesize_line(
                    text=chunk_text,
                    speaker=speaker,
                    emotion=str(line.get("emotion", "neutral")),
                    output_path=output_path,
                    producer_mode=str(line.get("producer_mode", "")),
                    delivery_instruction=str(line.get("delivery_notes", "")),
                )
                if not output_path.exists() or output_path.stat().st_size == 0:
                    raise RuntimeError(f"TTS produced no audio for line {idx}, chunk {chunk_idx}")
                duration_seconds = self._probe_duration_seconds(output_path) if output_path.exists() else 0.0
                pause_after = float(line.get("pause_after") if line.get("pause_after") is not None else 0.4)
                if len(chunks) > 1 and chunk_idx < len(chunks):
                    pause_after = max(pause_after, 0.55)
                segments.append({
                    "index": segment_index,
                    "line_index": idx,
                    "production_line_id": line.get("production_line_id"),
                    "production_cues": copy.deepcopy(line.get("production_cues", [])) if chunk_idx == len(chunks) else [],
                    "chunk_index": chunk_idx,
                    "chunk_count": len(chunks),
                    "speaker": speaker,
                    "text": chunk_text,
                    "source_text": text,
                    "emotion": line.get("emotion", "neutral"),
                    "audio_file": str(output_path),
                    "duration_seconds": duration_seconds,
                    "engine": engine_used,
                    "voice_name": self._resolve_voice_name(speaker, engine_used),
                    "pause_after": pause_after,
                    "generated_by": line.get("generated_by", "unknown"),
                })
                if progress_callback:
                    progress_callback({
                        "stage": "synthesizing", "line_number": idx,
                        "total_lines": len(script_lines), "chunk_number": chunk_idx,
                        "chunk_count": len(chunks), "engine": engine_used,
                        "progress": 0.85 * ((idx - 1 + chunk_idx / len(chunks)) / len(script_lines)),
                        **self.summarize_engines(segments),
                    })
        if not segments:
            raise RuntimeError("No audio segments were generated")
        return segments

    def _master_wrapped_audio(self, output_path):
        """Measure the final program including the theme and announcer."""
        self._check_cancelled()
        mastered = output_path.with_name(output_path.stem + "_mastered.mp3")
        result = self.post_processor.process_episode(output_path, mastered, "phil_jim_mix")
        if not result.get("compliant"):
            raise RuntimeError("Wrapped audio failed loudness/peak acceptance; previous production was preserved")
        os.replace(mastered, output_path)
        result["output_file"] = str(output_path)
        return result

    def _check_cancelled(self):
        event = getattr(self, "cancel_event", None)
        if event is not None and event.is_set():
            raise RuntimeError("Production cancelled by operator")

    def _synthesize_line(self, text: str, speaker: str, emotion: str, output_path: Path,
                         producer_mode: str = "", delivery_instruction: str = "") -> str:
        """Synthesize with the selected studio engine only.

        Dandy has no Edge or browser-voice production fallback. Kokoro is the
        default production engine; Qwen is available only when explicitly
        selected as the primary TTS engine. If the selected engine fails, the
        production fails visibly instead of changing voices behind the operator.
        """
        speaker = self._normalize_speaker(speaker)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        selected = str(
            self.project_config.get("tts", {}).get("primary_engine", "kokoro")
        ).strip().lower()

        if self.qwen_tts_config.get("production", {}).get("required_engine") == "qwen":
            selected = "qwen"

        if selected == "voicestudio":
            voice_payload = self.voices_config.get(speaker, {})
            voice_id = voice_payload.get("voicestudio_voice")
            base_url = self.project_config.get("tts", {}).get("voicestudio_base_url", "http://127.0.0.1:3900")
            if not voice_id:
                raise RuntimeError(f"No Voice Studio profile registered for '{speaker}'")
            try:
                from ..tts.voicestudio_wrapper import synthesize as synthesize_voicestudio
                synthesize_voicestudio(
                    base_url,
                    str(voice_id),
                    text,
                    output_path,
                    instructions=delivery_instruction or emotion,
                    speed=self._resolve_speed(speaker, emotion),
                )
                return "voicestudio"
            except Exception as exc:
                fallback = str(self.project_config.get("tts", {}).get("fallback_engine", "")).lower()
                if fallback != "qwen":
                    raise RuntimeError(f"Voice Studio production failed: {exc}") from exc
                logger.warning("Voice Studio failed for %s; using configured Qwen backup: %s", speaker, exc)
                selected = "qwen"

        if selected == "kokoro":
            try:
                if self._try_kokoro(text, speaker, emotion, output_path):
                    return "kokoro"
            except Exception as exc:
                raise RuntimeError(f"Kokoro TTS failed: {exc}") from exc
            raise RuntimeError("Kokoro TTS failed without producing audio")

        if selected == "qwen":
            if not self.qwen_tts_config.get("enabled"):
                raise RuntimeError("Qwen TTS is selected but disabled")
            if not self.qwen_tts_config.get("voices", {}).get(speaker):
                raise RuntimeError(f"No Qwen voice registered for '{speaker}'; no fallback voice substituted")
            try:
                if self._try_qwen_bridge(text, speaker, emotion, output_path,
                                         producer_mode=producer_mode,
                                         delivery_instruction=delivery_instruction):
                    self._apply_producer_mode(output_path, speaker, producer_mode)
                    return "qwen"
            except Exception as exc:
                raise RuntimeError(f"Required Qwen production failed; voice substitution is disabled: {exc}") from exc
            raise RuntimeError("Qwen TTS failed without producing audio")

        raise RuntimeError(
            f"Unsupported production TTS engine '{selected}'. Dandy allows only Kokoro or Qwen."
        )

    def _try_qwen_bridge(self, text: str, speaker: str, emotion: str, output_path: Path,
                         producer_mode: str = "", delivery_instruction: str = "") -> bool:
        bridge_url = str(self.qwen_tts_config.get("bridge_url") or "").rstrip("/")
        if not bridge_url:
            raise RuntimeError("Qwen bridge_url is not configured")

        voice_map = self.qwen_tts_config.get("voices", {})
        if not voice_map.get(speaker):
            raise RuntimeError(f"No Qwen voice configured for {speaker}")
        instruction_map = self.qwen_tts_config.get("instructions", {})
        timeout = float(self.qwen_tts_config.get("timeouts", {}).get("synthesis_seconds", 180))
        voice_payload = self.voices_config.get(speaker, {})
        mode_cfg = voice_payload.get("modes", {}).get(producer_mode or voice_payload.get("producer_mode_default", ""), {})
        voice_prompt = voice_payload.get("qwen_voice_prompt")
        if voice_prompt:
            prompt_path = Path(str(voice_prompt))
            if not prompt_path.is_absolute():
                prompt_path = (self.base_path / prompt_path).resolve()
            if not prompt_path.is_file():
                raise RuntimeError(f"Saved Qwen clone prompt for '{speaker}' is missing: {prompt_path}")
            voice_prompt = str(prompt_path)
        base_instruction = mode_cfg.get("instruction") or instruction_map.get(speaker)
        instruction = " ".join(part.strip() for part in (base_instruction, delivery_instruction) if part and part.strip())
        payload = {
            "text": text,
            "speaker": speaker,
            "voice": voice_map.get(speaker),
            "emotion": emotion,
            "instruction": instruction or None,
            "voice_prompt": voice_prompt,
            "reference_audio": self._resolve_voice_asset(voice_payload.get("qwen_reference_audio")),
            "reference_text": voice_payload.get("qwen_reference_text"),
            "language": "English",
            "format": output_path.suffix.lstrip(".") or "mp3",
            "output_path": str(output_path),
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{bridge_url}/synthesize",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Qwen bridge HTTP {exc.code}: {detail}") from exc

        if self.qwen_tts_config.get("production", {}).get("required_engine") == "qwen":
            if result.get("engine") != "qwen" or result.get("voice") != voice_map[speaker]:
                raise RuntimeError("Qwen bridge returned an unexpected engine or voice")
        produced_path = Path(result.get("audio_file") or result.get("path") or output_path)
        if produced_path.resolve() != output_path.resolve():
            if not produced_path.exists():
                raise RuntimeError(f"Qwen bridge returned missing file: {produced_path}")
            shutil.copyfile(produced_path, output_path)
        if not output_path.exists() or not output_path.stat().st_size:
            raise RuntimeError("Qwen bridge did not create a nonempty output file")
        return True

    def _resolve_voice_asset(self, value: Any) -> Optional[str]:
        if not value:
            return None
        path = Path(str(value))
        if not path.is_absolute():
            path = (self.base_path / path).resolve()
        return str(path)

    def _apply_producer_mode(self, output_path: Path, speaker: str, producer_mode: str) -> None:
        if speaker != "bryan" or not output_path.exists():
            return
        voice_payload = self.voices_config.get("bryan", {})
        mode = producer_mode or voice_payload.get("producer_mode_default", "producer_background")
        gain_db = float(voice_payload.get("modes", {}).get(mode, {}).get("gain_db", -8))
        if gain_db:
            AudioSegment.from_file(str(output_path)).apply_gain(gain_db).export(str(output_path), format=output_path.suffix.lstrip(".") or "mp3")

    # ── WSL path helpers ────────────────────────────────────────────────
    _WSL_PYTHON = "/home/bryan/.venvs/gpu/bin/python"
    _WSL_WORKER = "/home/bryan/wsl_tts_worker.py"
    _WSL_TIMEOUT = 120  # seconds per line

    @staticmethod
    def _win_to_wsl(path: Path) -> str:
        """Convert a Windows absolute path to a WSL /mnt/... path."""
        resolved = path.resolve()
        drive = resolved.drive.rstrip(":\\").lower()
        rest = resolved.as_posix().lstrip("/")
        rest = rest[len(drive) + 1:].lstrip("/")
        return f"/mnt/{drive}/{rest}"

    def _try_kokoro(self, text: str, speaker: str, emotion: str, output_path: Path) -> bool:
        """Synthesize via Kokoro running in the WSL GPU sidecar."""
        voice_payload = self.voices_config.get(speaker, {})
        voice_name = voice_payload.get("primary_voice")
        if not voice_name:
            raise RuntimeError(f"No Kokoro voice configured for speaker '{speaker}'")

        speed = self._resolve_speed(speaker, emotion)
        wav_path = output_path.with_suffix(".wav")
        wsl_out = self._win_to_wsl(wav_path)

        cmd = [
            "wsl", "--", self._WSL_PYTHON, self._WSL_WORKER,
            "--text",   text,
            "--voice",  voice_name,
            "--speed",  str(speed),
            "--output", wsl_out,
        ]

        logger.debug("WSL-TTS cmd: %s", " ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self._WSL_TIMEOUT,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"WSL Kokoro failed: {err}")

        if not wav_path.exists():
            raise RuntimeError("WSL Kokoro did not produce output file")

        convert_cmd = [
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-q:a", "2", str(output_path),
        ]
        subprocess.run(convert_cmd, check=True, capture_output=True, timeout=120)
        wav_path.unlink(missing_ok=True)

        logger.debug("WSL-TTS OK: %s → %s", speaker, output_path.name)
        return True

    def _synthesize_edge(self, text: str, speaker: str, output_path: Path) -> None:
        import edge_tts

        voice_payload = self.voices_config.get(speaker, {})
        voice_name = voice_payload.get("fallback_voice") or voice_payload.get("primary_voice") or "en-US-GuyNeural"

        async def _run():
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(str(output_path))

        error: list[Exception] = []

        def _runner() -> None:
            try:
                asyncio.run(_run())
            except Exception as exc:
                error.append(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        if not output_path.exists():
            raise RuntimeError("Edge TTS did not create an output file")

    def _resolve_speed(self, speaker: str, emotion: str) -> float:
        defaults = self.voices_config.get(speaker, {}).get("defaults", {})
        speed = float(defaults.get("speed", 1.0))
        if speaker == "phil" and emotion == "excited":
            return speed + 0.05
        if speaker == "jim" and emotion == "skeptical":
            return max(0.85, speed - 0.08)
        return speed

    def _resolve_voice_name(self, speaker: str, engine_used: str) -> str:
        voice_payload = self.voices_config.get(speaker, {})
        if engine_used == "kokoro":
            return str(voice_payload.get("primary_voice", ""))
        if engine_used == "edge":
            return str(voice_payload.get("fallback_voice") or voice_payload.get("primary_voice") or "")
        if engine_used == "qwen":
            return str(self.qwen_tts_config.get("voices", {}).get(speaker, ""))
        return ""

    def _concatenate_segments(
        self, segments: List[Dict[str, Any]], output_path: Path,
        media_cues_override: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        concat_list = output_path.with_suffix(".txt")
        generated_files: List[Path] = []
        try:
            with concat_list.open("w", encoding="utf-8") as handle:
                for idx, segment in enumerate(segments, start=1):
                    audio_file = Path(segment["audio_file"]).resolve()
                    escaped = audio_file.as_posix().replace("'", "'\\''")
                    handle.write(f"file '{escaped}'\n")

                    pause_ms = int(float(segment.get("pause_after", 0.4)) * 1000)
                    if pause_ms <= 0:
                        continue
                    silence_file = output_path.parent / f"pause_{idx:03d}.mp3"
                    # The concat demuxer requires pauses to match the dialogue
                    # stream; pydub's default silence is 11.025 kHz, while Qwen
                    # dialogue is 24 kHz. Avoid rate changes inside one stream.
                    source = AudioSegment.from_file(str(audio_file))
                    pause = AudioSegment.silent(duration=pause_ms, frame_rate=source.frame_rate)
                    pause = pause.set_channels(source.channels).set_sample_width(source.sample_width)
                    pause.export(silence_file, format="mp3").close()
                    generated_files.append(silence_file)
                    escaped = silence_file.resolve().as_posix().replace("'", "'\\''")
                    handle.write(f"file '{escaped}'\n")

            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(output_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        finally:
            if concat_list.exists():
                concat_list.unlink()
            for generated_file in generated_files:
                if generated_file.exists():
                    generated_file.unlink()

    def _probe_duration_seconds(self, audio_path: Path) -> float:
        cmd = ["ffmpeg", "-i", str(audio_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = f"{result.stdout}\n{result.stderr}"
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
            if not match:
                return 0.0
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = float(match.group(3))
            return round((hours * 3600) + (minutes * 60) + seconds, 2)
        except Exception:
            return 0.0

    def _export_direct_mp3(self, input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
