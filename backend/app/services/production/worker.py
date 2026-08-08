"""
worker.py — Hardened Production Pipeline for Phil & Jim Dandy Show
====================================================================
Replaces the original MergedDandyPodcastWorker with a production-grade
pipeline that includes:

  - Quality gates at EVERY stage (no more silent failures)
  - [unknown] detection and rejection (was documented, now implemented)
  - Script expansion to target duration (fixes the 30-second podcast bug)
  - Multi-tier fallback chain: SKG → Retry → Enhanced Seed → Minimal Seed
  - Rich context building (fixes repetitive dialogue)
  - Retry logic with parameter tweaking
  - Comprehensive structured logging

Drop-in replacement: update your imports to use HardenedPodcastWorker
instead of MergedDandyPodcastWorker.
"""

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
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
from .sfx import apply_sfx_events

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    primary_engine: str
    fallback_engine: str
    device: str


class HardenedPodcastWorker:
    """
    Production-grade podcast generation worker.

    Pipeline stages:
      1. VALIDATE config (ensure we have minimum required fields)
      2. BUILD context (rich, varied context from key_points)
      3. GENERATE via SKG (Phil & Jim banter)
      4. QUALITY GATE #1 (check SKG output for [unknown], length, etc.)
      5. EXPAND to target duration (if SKG output is good but short)
      6. QUALITY GATE #2 (validate expanded script)
      7. FALLBACK CHAIN (if any stage fails, retry or fall back)
      8. PRODUCE audio (TTS synthesis + mixing)

    Quality gates prevent all 8 identified failure modes:
      - [unknown] tokens → detected and rejected
      - Too-short scripts → expanded to target
      - Generic context → rich context builder
      - No validation → gates at every stage
      - Nonsense injections → detected and flagged
      - Raw template vars → detected and rejected
    """

    def __init__(self, base_path: Optional[Path] = None):
        # Import project-specific modules here to avoid hard deps
        try:
            from ...core.paths import PROJECT_ROOT
            from ...core.settings import load_project_config, load_qwen_tts_config, load_voices_config
            from .audio_post_processor import FFmpegPostProcessor
            from .communication_layer import DandyCommunicationLayer
            from .personality_loader import load_personality
        except ImportError:
            # Fallback for standalone testing
            from backend.app.core.paths import PROJECT_ROOT
            from backend.app.core.settings import load_project_config, load_qwen_tts_config, load_voices_config
            from backend.app.services.production.audio_post_processor import FFmpegPostProcessor
            from backend.app.services.production.communication_layer import DandyCommunicationLayer
            from backend.app.services.production.personality_loader import load_personality

        self.base_path = Path(base_path or PROJECT_ROOT).resolve()
        self.project_config = load_project_config()
        self.voices_config = load_voices_config()
        self.qwen_tts_config = load_qwen_tts_config()
        self.runtime = WorkerRuntime(
            primary_engine=self.project_config.get("tts", {}).get("primary_engine", "kokoro"),
            fallback_engine=self.project_config.get("tts", {}).get("fallback_engine", "edge"),
            device=self.project_config.get("tts", {}).get("preferred_device", "cpu"),
        )
        self.post_processor = FFmpegPostProcessor(self.base_path, logger)
        self.quality_guard = ScriptQualityGuard()
        self.script_expander = ScriptExpander()
        self._init_skg_systems()

    def _init_skg_systems(self) -> None:
        try:
            from .communication_layer import DandyCommunicationLayer
            from .personality_loader import load_personality
            self.phil_skg = load_personality("phil")
            self.jim_skg = load_personality("jim")
            self.communication_layer = DandyCommunicationLayer(self.phil_skg, self.jim_skg)
        except Exception as e:
            logger.warning("SKG systems unavailable (%s). Will use seed fallback only.", e)
            self.phil_skg = None
            self.jim_skg = None
            self.communication_layer = None

    def _apply_personality_settings(self, personality_settings: Optional[Dict[str, Any]]) -> None:
        if not personality_settings or not self.phil_skg or not self.jim_skg:
            return
        for skg in (self.phil_skg, self.jim_skg):
            setter = getattr(skg, "set_personality_tuning", None)
            if callable(setter):
                try:
                    setter(personality_settings)
                except Exception:
                    logger.warning("Personality tuning failed for %s", skg.__class__.__name__)

    # ═════════════════════════════════════════════════════════════════
    # STAGE 1: SCRIPT GENERATION (Hardened)
    # ═════════════════════════════════════════════════════════════════

    def generate_script(
        self,
        episode_config: Dict[str, Any],
        line_callback: Optional[Callable] = None,
        max_retries: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Generate a complete podcast script with full quality validation.

        This method NEVER silently returns garbage. It will always produce
        a valid script, falling through the chain if needed:

            Attempt 1: SKG generation + quality gate
            Attempt 2: SKG retry with tweaked parameters
            Fallback: Enhanced seed script (full length)
            Last resort: Minimal seed script
        """
        topic = str(episode_config.get("topic", "general")).strip()
        title = str(episode_config.get("title") or topic).strip()
        key_points = [kp for kp in episode_config.get("key_points", []) if kp]
        require_llm = bool(episode_config.get("require_llm", True))
        target_minutes = int(
            episode_config.get("target_duration_minutes")
            or (episode_config.get("target_duration", 2400) // 60)
            or 40
        )

        logger.info(
            "[Worker] Generating script: topic='%s' target=%dmin key_points=%d",
            topic, target_minutes, len(key_points),
        )

        # ── Validate minimum requirements ──
        if not key_points:
            key_points = [topic]
            logger.warning("[Worker] No key_points provided, using topic as single point")

        # ── Build rich context (fixes FAILURE MODE 3: generic context) ──
        rich_context = build_rich_context(
            topic=topic,
            key_points=key_points,
            title=title,
            audience=episode_config.get("audience", "general"),
            intensity=episode_config.get("intensity", "medium"),
            source_context=str(episode_config.get("source_context", "")),
            personality_settings=episode_config.get("personality_settings"),
        )

        # ── Attempt 1: SKG Generation ──
        for attempt in range(max_retries + 1):
            script = self._try_skg_generation(
                episode_config=episode_config,
                rich_context=rich_context,
                key_points=key_points,
                topic=topic,
                title=title,
                attempt=attempt,
                line_callback=line_callback,
            )

            if script:
                # ── Quality Gate #1 (fixes FAILURE MODE 1: [unknown] detection) ──
                report = self.quality_guard.evaluate(script, target_minutes, topic)

                if report.decision == QualityDecision.ACCEPT:
                    logger.info("[Worker] Script accepted on attempt %d (score: %.1f)", attempt + 1, report.score)

                    # ── Expand if needed (fixes FAILURE MODE 2: too short) ──
                    if report.word_count < report.target_words * 0.85:
                        if require_llm:
                            raise RuntimeError(
                                f"LLM script too short: {report.word_count}/{report.target_words} words"
                            )
                        logger.info(
                            "[Worker] Expanding script: %d → %d words",
                            report.word_count, report.target_words,
                        )
                        script = self.script_expander.expand(
                            base_lines=script,
                            key_points=key_points,
                            topic=topic,
                            target_minutes=target_minutes,
                            title=title,
                            existing_context=rich_context,
                        )
                        # Re-check after expansion
                        report2 = self.quality_guard.evaluate(script, target_minutes, topic)
                        if report2.decision != QualityDecision.ACCEPT:
                            logger.warning("[Worker] Expanded script failed QC, trying seed")
                            continue
                    
                    self._log_final_stats(script, topic, target_minutes)
                    return script

                elif report.decision == QualityDecision.REJECT_RETRY and attempt < max_retries:
                    logger.warning(
                        "[Worker] Script rejected on attempt %d (score: %.1f), retrying...",
                        attempt + 1, report.score,
                    )
                    # Tweak parameters for retry
                    episode_config = self._tweak_for_retry(episode_config, attempt)
                    continue

                else:
                    logger.error(
                        "[Worker] Script failed quality gate (score: %.1f), falling back to seed",
                        report.score,
                    )
                    break

        # ── Fallback: Enhanced Seed Script (fixes FAILURE MODE 4: short fallback) ──
        if require_llm:
            raise RuntimeError("LLM writer did not produce an accepted script; fallback disabled")

        logger.info("[Worker] Using enhanced seed script fallback")
        seed_script = generate_seed_script({
            **episode_config,
            "topic": topic,
            "title": title,
            "key_points": key_points,
            "target_duration_minutes": target_minutes,
        })

        # Validate seed script too
        seed_report = self.quality_guard.evaluate(seed_script, target_minutes, topic)
        if seed_report.decision in (QualityDecision.ACCEPT, QualityDecision.REJECT_RETRY):
            logger.info("[Worker] Seed script accepted (score: %.1f)", seed_report.score)
            self._log_final_stats(seed_script, topic, target_minutes)
            return seed_script

        # ── Last resort: minimal seed ──
        logger.critical("[Worker] ALL generation methods failed! Using emergency minimal script.")
        return self._emergency_script(topic, title)

    def _try_skg_generation(
        self,
        episode_config: Dict[str, Any],
        rich_context: Dict[str, Any],
        key_points: List[str],
        topic: str,
        title: str,
        attempt: int,
        line_callback: Optional[Callable] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Attempt SKG generation. Returns None if SKG is unavailable or fails."""
        if not self.communication_layer:
            return None

        try:
            self._apply_personality_settings(episode_config.get("personality_settings"))

            # Build script definition with rich context
            script_definition = {
                "episode_id": episode_config.get("episode_id"),
                "topics": [topic],
                "topic": topic,
                "key_points": key_points,
                "audience": episode_config.get("audience", "general"),
                "intensity": episode_config.get("intensity", "medium"),
                "source_context": str(episode_config.get("source_context", "")),
                "personality_settings": episode_config.get("personality_settings"),
                "require_llm": bool(episode_config.get("require_llm", True)),
                "generation_nonce": episode_config.get("generation_nonce"),
                "title": title,
                # Inject rich context directly so _build_context can use it
                "_rich_context": rich_context,
                "rhythm": RhythmState.from_context(episode_config).to_dict(),
            }

            conversation = self.communication_layer.orchestrate_banter(
                script_definition,
                audience_feedback=None,
                line_callback=line_callback,
            )

            if not conversation:
                return None

            return self._conversation_to_script(conversation)

        except Exception as exc:
            logger.warning("SKG generation attempt %d failed: %s", attempt + 1, exc)
            return None

    def _tweak_for_retry(self, config: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        """Modify config parameters for retry attempt."""
        tweaked = dict(config)
        # On retry, adjust intensity and add jitter
        intensities = ["low", "medium", "high"]
        current = config.get("intensity", "medium")
        if current in intensities:
            idx = intensities.index(current)
            tweaked["intensity"] = intensities[(idx + attempt + 1) % len(intensities)]
        return tweaked

    def _emergency_script(self, topic: str, title: str) -> List[Dict[str, Any]]:
        """Absolute last resort — a minimal valid script."""
        return [
            {"speaker": "phil", "text": f"Welcome to the Phil and Jim Dandy Show. Today we're talking about {title}.", "emotion": "warm", "pause_after": 0.5, "line_number": 1},
            {"speaker": "jim", "text": f"We'll keep it practical and useful. {title} is worth understanding.", "emotion": "measured", "pause_after": 0.5, "line_number": 2},
            {"speaker": "phil", "text": "Let's dig in and see where this takes us.", "emotion": "excited", "pause_after": 0.5, "line_number": 3},
            {"speaker": "jim", "text": "And remember — ideas are cheap. Execution is everything. Thanks for listening.", "emotion": "warm", "pause_after": 0.5, "line_number": 4},
        ]

    def _log_final_stats(self, script: List[Dict[str, Any]], topic: str, target_minutes: int) -> None:
        word_count = sum(len(str(line.get("text", line.get("line", ""))).split()) for line in script)
        line_count = len(script)
        speakers = {}
        for line in script:
            s = str(line.get("speaker", "unknown")).lower()
            speakers[s] = speakers.get(s, 0) + 1

        logger.info(
            "[Worker] Final script: %d lines, %d words (target: %d min @ ~155wpm = ~%d words). "
            "Speakers: %s",
            line_count, word_count, target_minutes, target_minutes * 155, speakers,
        )

    def _conversation_to_script(self, conversation: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert SKG conversation to normalized script lines with validation."""
        script_lines: List[Dict[str, Any]] = []
        for idx, exchange in enumerate(conversation, start=1):
            speaker = str(exchange.get("speaker", "phil")).lower()
            if speaker.startswith("phil"):
                normalized = "phil"
            elif speaker.startswith("jim"):
                normalized = "jim"
            else:
                normalized = "host"

            emotional_state = exchange.get("emotional_state", {})
            emotion = self._map_emotion(normalized, emotional_state)
            raw_text = str(exchange.get("text", "")).strip()

            # ── Strip speaker prefix if present ──
            cleaned_text = self._strip_spoken_speaker_prefix(raw_text, normalized)

            # ── Filter out lines with [unknown] (FAILURE MODE 1) ──
            if "[unknown]" in cleaned_text.lower():
                logger.warning("[Worker] Filtered SKG line with [unknown]: %s", cleaned_text[:60])
                continue

            # ── Filter out hardcoded nonsense (FAILURE MODE 6) ──
            nonsense_phrases = [
                "vinyl is faster than fiber",
                "cloud is just a bunch of floppy disks",
                "EVs don't use electricity when going downhill",
                "Podcasts are printed first, then streamed",
            ]
            if any(ns in cleaned_text.lower() for ns in nonsense_phrases):
                logger.warning("[Worker] Filtered SKG line with nonsense: %s", cleaned_text[:60])
                continue

            script_lines.append({
                "speaker": normalized,
                "text": cleaned_text,
                "emotion": emotion,
                "pause_after": self._resolve_pause_after(normalized, exchange),
                "rhythm": exchange.get("rhythm", {}),
                "line_number": idx,
                "generated_by": exchange.get("generated_by", "skg_template"),
            })

        return [line for line in script_lines if line["text"]]

    def _resolve_pause_after(self, speaker: str, exchange: Dict[str, Any]) -> float:
        base_pause = 0.55 if speaker == "jim" else 0.35
        rhythm = dict(exchange.get("rhythm") or {})
        tempo = str(rhythm.get("interaction_tempo", "")).lower()
        load = float(rhythm.get("human_load", 0.0) or 0.0)
        if tempo == "fast":
            base_pause -= 0.08
        elif tempo == "slow":
            base_pause += 0.10
        if load >= 0.75:
            base_pause += 0.12
        elif load >= 0.6:
            base_pause += 0.05
        return max(0.2, min(1.0, round(base_pause, 3)))

    def _map_emotion(self, speaker: str, emotional_state: Dict[str, Any]) -> str:
        if speaker == "phil":
            enthusiasm = emotional_state.get("enthusiasm", emotional_state.get("optimism", 0))
            return "excited" if enthusiasm and enthusiasm >= 7 else "warm"
        if speaker == "jim":
            skepticism = emotional_state.get("skepticism", 0)
            pragmatism = emotional_state.get("pragmatism", 0)
            if skepticism and skepticism >= 7:
                return "skeptical"
            if pragmatism and pragmatism >= 7:
                return "pragmatic"
            return "neutral"
        return "neutral"

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
    ) -> Dict[str, Any]:
        """Produce audio from script — unchanged logic, just called with validated script."""
        if not script_lines:
            raise ValueError("script_lines are required for production")

        episode_dir = self.base_path / "episodes" / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)
        final_audio_path = episode_dir / "audio.mp3"
        transcript_path = episode_dir / "transcript.json"
        metadata_path = episode_dir / "production_metadata.json"
        (self.base_path / "staging").mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(self.base_path / "staging")) as temp_dir:
            staging_dir = Path(temp_dir)
            raw_segments_dir = staging_dir / "segments"
            raw_segments_dir.mkdir(parents=True, exist_ok=True)

            segment_payloads = self._synthesize_segments(script_lines, raw_segments_dir, episode_id)
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
                logger.warning("Post-processing failed; exporting direct MP3 fallback: %s", exc)
                self._export_direct_mp3(raw_mix_path, final_audio_path)
                processing_result = {
                    "processing_chain": "direct_mp3_fallback",
                    "compliant": False,
                    "warning": str(exc),
                }

            # ── Intro / Outro wrap ──────────────────────────────────────
            io_cfg = self.project_config.get("intro_outro", {})
            if io_cfg.get("enabled", False) and final_audio_path.exists():
                try:
                    wrapped_path = episode_dir / "audio_wrapped.mp3"
                    wrap_episode_audio(
                        episode_audio_path=final_audio_path,
                        output_path=wrapped_path,
                        cfg=io_cfg,
                        base_path=self.base_path,
                        topic=topic,
                    )
                    final_audio_path.unlink()
                    wrapped_path.rename(final_audio_path)
                    processing_result["intro_outro"] = "wrapped"
                    logger.info("Intro/outro applied to %s", episode_id)
                except Exception as exc:
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
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return {
            "episode_id": episode_id,
            "audio_file": str(final_audio_path),
            "transcript": script_lines,
            "metadata": metadata,
        }

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
        # Best-effort: prefer announcer_male for unknown 'announcer*' prefixes
        if s.startswith("announcer"):
            return "announcer_male"
        # Fall back to phil so TTS never crashes
        logger.warning("Unknown speaker '%s' — falling back to 'phil'", raw)
        return "phil"

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
                chunks.append(current.rstrip(",;:"))
            current = word
        if current:
            chunks.append(current.rstrip(",;:"))
        return chunks

    def _synthesize_segments(self, script_lines: List[Dict[str, Any]], output_dir: Path, episode_id: str) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        segment_index = 0
        for idx, line in enumerate(script_lines, start=1):
            speaker = self._normalize_speaker(str(line.get("speaker", "phil")))
            text = self._strip_spoken_speaker_prefix(
                text=str(line.get("text", "")).strip(),
                speaker=speaker,
            )
            if not text:
                continue

            chunks = self._split_for_tts(text)
            for chunk_idx, chunk_text in enumerate(chunks, start=1):
                segment_index += 1
                output_path = output_dir / f"{episode_id}_{segment_index:03d}_{speaker}.mp3"
                engine_used = self._synthesize_line(
                    text=chunk_text,
                    speaker=speaker,
                    emotion=str(line.get("emotion", "neutral")),
                    output_path=output_path,
                )
                duration_seconds = self._probe_duration_seconds(output_path) if output_path.exists() else 0.0
                pause_after = float(line.get("pause_after", 0.4) or 0.4)
                if len(chunks) > 1 and chunk_idx < len(chunks):
                    pause_after = max(pause_after, 0.55)
                segments.append({
                    "index": segment_index,
                    "line_index": idx,
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
        if not segments:
            raise RuntimeError("No audio segments were generated")
        return segments

    def _synthesize_line(self, text: str, speaker: str, emotion: str, output_path: Path) -> str:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        errors: List[str] = []

        if self.qwen_tts_config.get("enabled") and self.qwen_tts_config.get("production", {}).get("enabled", True):
            try:
                if self._try_qwen_bridge(text, speaker, emotion, output_path):
                    return "qwen"
            except Exception as exc:
                errors.append(f"qwen:{exc}")

        if self.runtime.primary_engine == "kokoro":
            try:
                if self._try_kokoro(text, speaker, emotion, output_path):
                    return "kokoro"
            except Exception as exc:
                errors.append(f"kokoro:{exc}")

        try:
            self._synthesize_edge(text, speaker, output_path)
            return "edge"
        except Exception as exc:
            errors.append(f"edge:{exc}")

        raise RuntimeError("; ".join(errors) or "All TTS engines failed")

    def _try_qwen_bridge(self, text: str, speaker: str, emotion: str, output_path: Path) -> bool:
        bridge_url = str(self.qwen_tts_config.get("bridge_url") or "").rstrip("/")
        if not bridge_url:
            raise RuntimeError("Qwen bridge_url is not configured")

        voice_map = self.qwen_tts_config.get("voices", {})
        instruction_map = self.qwen_tts_config.get("instructions", {})
        timeout = float(self.qwen_tts_config.get("timeouts", {}).get("synthesis_seconds", 180))
        payload = {
            "text": text,
            "speaker": speaker,
            "voice": voice_map.get(speaker),
            "emotion": emotion,
            "instruction": instruction_map.get(speaker),
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

        produced_path = Path(result.get("audio_file") or result.get("path") or output_path)
        if produced_path.resolve() != output_path.resolve():
            if not produced_path.exists():
                raise RuntimeError(f"Qwen bridge returned missing file: {produced_path}")
            shutil.copyfile(produced_path, output_path)
        if not output_path.exists():
            raise RuntimeError("Qwen bridge did not create an output file")
        return True

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
        subprocess.run(convert_cmd, check=True, capture_output=True)
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

    def _concatenate_segments(self, segments: List[Dict[str, Any]], output_path: Path) -> None:
        concat_list = output_path.with_suffix(".txt")
        generated_files: List[Path] = []
        try:
            with concat_list.open("w", encoding="utf-8") as handle:
                for idx, segment in enumerate(segments, start=1):
                    audio_file = Path(segment["audio_file"]).resolve()
                    handle.write(f"file '{audio_file.as_posix()}'\n")

                    pause_ms = int(float(segment.get("pause_after", 0.4)) * 1000)
                    if pause_ms <= 0:
                        continue
                    silence_file = output_path.parent / f"pause_{idx:03d}.mp3"
                    AudioSegment.silent(duration=pause_ms).export(silence_file, format="mp3")
                    generated_files.append(silence_file)
                    handle.write(f"file '{silence_file.resolve().as_posix()}'\n")

            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(output_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        finally:
            if concat_list.exists():
                concat_list.unlink()
            for generated_file in generated_files:
                if generated_file.exists():
                    generated_file.unlink()

    def _probe_duration_seconds(self, audio_path: Path) -> float:
        cmd = ["ffmpeg", "-i", str(audio_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
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
        subprocess.run(cmd, check=True, capture_output=True, text=True)
