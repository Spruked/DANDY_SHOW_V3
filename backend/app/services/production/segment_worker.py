"""Duration-aware short-form generation for Dandy Studio.

Targets from 1 to 15 minutes use a forward-only generation path. The worker
filters bad turns while the conversation is being built and does not discard a
mostly-good short script just to regenerate the entire conversation from the
beginning. Longer legacy episodes continue through the established worker path.

Short-segment audio assembly also honors episode media cues. Reusable repo
assets and episode-specific assets can be inserted or overlaid after a selected
script line before intro/outro wrapping.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional

from pydub import AudioSegment

from .context_builder import build_rich_context
from .episode_governor import EpisodeGovernor, TurnDirective
from . import llm_writer
from .rhythm import RhythmState
from .worker import HardenedPodcastWorker
from ..storage.asset_library import load_library_asset
from ..storage.episode_store import load_asset, load_media_cues

logger = logging.getLogger(__name__)


class SegmentAwarePodcastWorker(HardenedPodcastWorker):
    """Use a bounded, forward-only LLM plan for 1-15 minute segments."""

    def _spoken_wpm(self) -> int:
        return max(1, int(self.project_config.get("production", {}).get("spoken_wpm", 90)))

    _SIMILARITY_STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "because", "but", "by",
        "do", "does", "for", "from", "got", "have", "how", "i", "if", "in",
        "is", "it", "its", "just", "like", "me", "of", "on", "or", "right",
        "so", "that", "the", "their", "them", "they", "this", "to", "up",
        "was", "what", "when", "where", "which", "with", "you", "your",
        "yeah", "exactly", "okay", "well",
    }
    _BAD_ENDINGS = {
        "a", "an", "and", "as", "at", "because", "but", "by", "for", "from",
        "if", "in", "into", "of", "on", "or", "related", "than", "that", "the",
        "then", "through", "to", "toward", "with", "without",
    }

    @classmethod
    def _similarity_tokens(cls, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9']+", str(text or "").lower())
            if len(token) >= 3 and token not in cls._SIMILARITY_STOPWORDS
        }

    @classmethod
    def _is_near_duplicate(cls, text: str, prior_texts: List[str]) -> bool:
        return cls._repetition_score(text, prior_texts) >= 0.86

    @classmethod
    def _repetition_score(cls, text: str, prior_texts: List[str]) -> float:
        """Return the strongest overlap score without treating shared topics as duplicates."""
        current = cls._similarity_tokens(text)
        if len(current) < 4:
            return 0.0

        strongest = 0.0
        for prior in prior_texts:
            previous = cls._similarity_tokens(prior)
            if len(previous) < 4:
                continue
            shared = len(current & previous)
            if not shared:
                continue
            containment = shared / max(1, min(len(current), len(previous)))
            jaccard = shared / max(1, len(current | previous))
            strongest = max(strongest, containment, jaccard)
        return strongest

    @classmethod
    def _looks_incomplete(cls, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return True
        if cleaned.endswith((",", ";", ":", "-", "—")):
            return True
        words = re.findall(r"[A-Za-z0-9']+", cleaned.lower())
        if not words:
            return True
        if words[-1] in cls._BAD_ENDINGS:
            return True
        return False

    def generate_script(
        self,
        episode_config: Dict[str, Any],
        line_callback: Optional[Callable] = None,
        max_retries: int = 2,
    ) -> List[Dict[str, Any]]:
        """Generate one forward-only short segment; never whole-script retry it."""
        target_minutes = int(
            episode_config.get("target_duration_minutes")
            or (episode_config.get("target_duration", 600) // 60)
            or 10
        )
        if target_minutes >= 5:
            return self._generate_episode_sections(episode_config, line_callback)

        topic = str(episode_config.get("topic", "general")).strip()
        title = str(episode_config.get("title") or topic).strip()
        key_points = [str(kp).strip() for kp in episode_config.get("key_points", []) if str(kp).strip()]
        if not key_points:
            key_points = [topic]

        rich_context = build_rich_context(
            topic=topic,
            key_points=key_points,
            title=title,
            audience=episode_config.get("audience", "general"),
            intensity=episode_config.get("intensity", "medium"),
            source_context=str(episode_config.get("source_context", "")),
            personality_settings=episode_config.get("personality_settings"),
        )

        script = self._try_skg_generation(
            episode_config=episode_config,
            rich_context=rich_context,
            key_points=key_points,
            topic=topic,
            title=title,
            attempt=0,
            line_callback=line_callback,
        )
        if not script:
            raise RuntimeError("Direct llama.cpp writer returned no usable short-segment dialogue")

        accepted: List[Dict[str, Any]] = []
        prior_texts: List[str] = []
        seen: set[str] = set()
        for line in script:
            text = str(line.get("text", "")).strip()
            if not text or "[unknown]" in text.lower() or self._looks_incomplete(text):
                continue
            repeat_key = self.communication_layer._repeat_key(text) if self.communication_layer else " ".join(text.lower().split())
            if not repeat_key or repeat_key in seen:
                continue
            if self._is_near_duplicate(text, prior_texts):
                continue
            if self._repetition_score(text, prior_texts) >= 0.56:
                line["repetition_warning"] = "possible_repetition"
            seen.add(repeat_key)
            prior_texts.append(text)
            accepted.append(line)

        if not accepted:
            raise RuntimeError("Short-segment acceptance filter removed every generated line")

        for idx, line in enumerate(accepted, start=1):
            line["line_number"] = idx

        target_words = max(1, round(target_minutes * self._spoken_wpm()))
        word_count = sum(len(str(line.get("text", "")).split()) for line in accepted)
        logger.info(
            "[SegmentWorker] Forward-only final: %d lines / %d words for %d-minute target (%.0f%%)",
            len(accepted), word_count, target_minutes, (word_count / target_words) * 100,
        )
        return accepted

    def _generate_episode_sections(self, config, line_callback=None):
        target_seconds = int(config.get("target_duration") or 1800)
        if not 300 <= target_seconds <= 2700:
            raise ValueError("Episodes must target 5 to 45 minutes")
        # The requested duration is the total dialogue target. Generation is
        # internally bounded to five-minute sections plus the exact remainder.
        content_seconds = target_seconds
        section_seconds = 5 * 60
        count = __import__('math').ceil(content_seconds / section_seconds)
        result, history = [], []
        progress = config.get("_progress_callback")
        section_phases = [
            ("Setup / define the issue", "establish the topic, why it matters, and the first concrete example"),
            ("Mechanics / deeper explanation", "explain how it works and add technical or practical detail"),
            ("Consequences / challenge", "surface limitations, objections, tradeoffs, and a different perspective"),
            ("Resolution / takeaway", "draw implications, lessons, what happens next, and a natural close"),
        ]
        for index in range(count):
            seconds = min(section_seconds, content_seconds - index * section_seconds)
            phase_index = 0 if count <= 1 else round(index * 3 / (count - 1))
            section_angle, new_ground = section_phases[phase_index]
            prior_section_excerpt = "\n".join(history[-12:]) if history else "(none — this is the opening section)"
            section_config = {**config, "target_duration_minutes": seconds / 60,
                              "target_duration": round(seconds), "target_word_count": round(seconds / 60 * self._spoken_wpm()),
                              "_prior_texts": [line["text"] for line in result], "_prior_history": history,
                              "_previous_section_summary": prior_section_excerpt,
                              "_section_angle": section_angle, "_section_new_ground": new_ground,
                              "_section_transition": "Open the show naturally." if index == 0 else "Pick up naturally from the previous section without summarizing it.",
                              "_section_index": index, "_section_count": count,
                              "generation_nonce": f"{config.get('generation_nonce', 'episode')}-section-{index + 1}"}
            if callable(progress):
                progress({"section": index + 1, "section_count": count, "accepted_words": sum(len(line["text"].split()) for line in result)})
            topic = str(config.get("topic") or config.get("title") or "general")
            points = config.get("key_points") or [topic]
            context = build_rich_context(topic=topic, key_points=points, title=config.get("title") or topic,
                                         audience=config.get("audience", "general"), intensity=config.get("intensity", "medium"),
                                         source_context=str(config.get("source_context", "")), personality_settings=config.get("personality_settings"))
            lines = self._try_skg_generation(section_config, context, points, topic, config.get("title") or topic, 0)
            if not lines:
                raise RuntimeError(f"Section {index + 1} produced no fresh dialogue; no repeated filler was added")
            words = sum(len(line["text"].split()) for line in lines)
            nominal_words = section_config["target_word_count"]
            hard_floor = round(seconds / 60 * 60)
            if words < nominal_words:
                logger.warning(
                    "Section %d below spoken-word target: %d/%d words (hard save floor %d); preserving generated dialogue",
                    index + 1, words, nominal_words, hard_floor,
                )
            for line in lines:
                line.update(segment_index=index + 1, segment_title=f"Part {index + 1}", line_number=len(result) + 1)
                result.append(line)
                history.append(f"{str(line['speaker']).upper()}: {line['text']}")
                if line_callback:
                    line_callback(line)
        return result

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
        target_minutes = float(
            episode_config.get("target_duration_minutes")
            or (episode_config.get("target_duration", 600) // 60)
            or 10
        )

        if target_minutes > 15:
            return super()._try_skg_generation(
                episode_config=episode_config,
                rich_context=rich_context,
                key_points=key_points,
                topic=topic,
                title=title,
                attempt=attempt,
                line_callback=line_callback,
            )

        target_minutes = max(1, min(15, target_minutes))
        if not self.communication_layer:
            return None

        try:
            self._apply_personality_settings(episode_config.get("personality_settings"))
            target_words = int(episode_config.get("target_word_count") or target_minutes * 90)
            rhythm = RhythmState.from_context(episode_config)

            script_definition = {
                "episode_id": episode_config.get("episode_id"),
                "episode_title": title,
                "topics": [topic],
                "topic": topic,
                "title": title,
                "key_points": key_points,
                "audience": episode_config.get("audience", "general"),
                "intensity": episode_config.get("intensity", "medium"),
                "source_context": str(episode_config.get("source_context", "")),
                "personality_settings": episode_config.get("personality_settings"),
                "require_llm": bool(episode_config.get("require_llm", True)),
                "generation_nonce": episode_config.get("generation_nonce"),
                "target_word_count": target_words,
                "target_duration_minutes": target_minutes,
                "target_duration": target_minutes * 60,
                "_rich_context": rich_context,
                "rhythm": rhythm.to_dict(),
            }

            context = self.communication_layer._build_context(topic, script_definition)
            persona_brief = self.communication_layer._build_persona_brief(context)
            custom_instructions = str(episode_config.get("custom_instructions", "")).strip()
            if custom_instructions:
                persona_brief = (
                    f"{persona_brief}\n\nRUNTIME CREATIVE INSTRUCTIONS:\n"
                    f"{custom_instructions[:1200]}"
                )
            persona_brief += (
                "\n\nSECTION CONTINUITY BRIEF:\n"
                f"PREVIOUS SECTION SUMMARY:\n{str(episode_config.get('_previous_section_summary') or '(none)')[:1800]}\n\n"
                f"THIS SECTION'S ANGLE:\n{episode_config.get('_section_angle', 'Continue the discussion with a new angle.')}\n\n"
                f"TRANSITION:\n{episode_config.get('_section_transition', 'Pick up naturally without repeating earlier material.')}\n\n"
                "DO NOT REPEAT:\n"
                "- the topic definition\n- the first example or analogy\n- previously established claims\n\n"
                f"NEW GROUND TO COVER:\n- {episode_config.get('_section_new_ground', 'a specific new angle, consequence, or practical example')}"
            )

            generation_nonce = str(
                episode_config.get("generation_nonce")
                or f"segment-{datetime.now().isoformat()}"
            )
            exchanges: List[Dict[str, Any]] = []
            prior_episode_texts = list(episode_config.get("_prior_texts") or [])
            seen_text: set[str] = {self.communication_layer._repeat_key(text) for text in prior_episode_texts}
            history_lines: List[str] = list(episode_config.get("_prior_history") or [])
            stage_counter = 0
            governor = EpisodeGovernor(
                getattr(self.communication_layer, "phil", None),
                getattr(self.communication_layer, "jim", None),
                history=history_lines,
            )
            beat_templates = [
                "introduce the central question",
                "explain why people should care",
                "give one concrete example",
                "explain the mechanism behind it",
                "have Jim challenge the main assumption",
                "have Phil answer with a different concrete example",
                "discuss a limitation or tradeoff",
                "show the practical consequence for real people",
                "draw the section's takeaway",
                "create a natural transition to the next section",
            ]
            beat_count = 10 if target_minutes >= 4 else max(4, int(round(target_minutes * 2)))
            section_beats = [
                {"number": index + 1, "description": description}
                for index, description in enumerate(beat_templates[:beat_count])
            ]
            completed_beats: List[int] = []

            def append_fresh(lines: List[Dict[str, Any]], rejection_stats: Dict[str, int], directives: List[TurnDirective]) -> int:
                accepted = 0
                prior_texts = prior_episode_texts + [str(exchange.get("text", "")) for exchange in exchanges]
                for line in lines:
                    text = str(line.get("text", "")).strip()
                    if not text:
                        continue
                    if self._looks_incomplete(text):
                        logger.info("[SegmentWorker] Dropped incomplete turn: %s", text[:90])
                        continue
                    directive = next((item for item in directives if item.speaker.lower() == str(line.get("speaker", "")).lower()), None)
                    if directive and not governor.validate_completion(directive, text):
                        rejection_stats["directive_rejected_lines"] += 1
                        logger.info("[EpisodeGovernor] Rejected completion for %s", directive.speaker)
                        continue
                    repeat_key = self.communication_layer._repeat_key(text)
                    if not repeat_key or repeat_key in seen_text:
                        rejection_stats["duplicate_rejected_lines"] += 1
                        logger.info("[SegmentWorker] Dropped exact repeat: %s", text[:90])
                        continue
                    if self._is_near_duplicate(text, prior_texts):
                        rejection_stats["duplicate_rejected_lines"] += 1
                        logger.info("[SegmentWorker] Dropped very-close repeat: %s", text[:90])
                        continue

                    seen_text.add(repeat_key)
                    exchange = {
                        "speaker": line.get("speaker", "Phil"),
                        "text": text,
                        "emotional_state": line.get("emotional_state", {}),
                        "timestamp": line.get("timestamp", datetime.now().isoformat()),
                        "rhythm": rhythm.to_dict(),
                        "timing": context.get("timing_profile", "balanced"),
                        "generated_by": line.get("generated_by", "llamacpp"),
                    }
                    if self._repetition_score(text, prior_texts) >= 0.56:
                        exchange["repetition_warning"] = "possible_repetition"
                        logger.info("[SegmentWorker] Kept possible repetition for editor review: %s", text[:90])
                    exchanges.append(exchange)
                    prior_texts.append(text)
                    accepted += 1
                    emotion = (line.get("emotional_state") or {}).get("primary", "")
                    emotion_tag = f" [{emotion}]" if emotion else ""
                    history_lines.append(
                        f"{str(exchange['speaker']).upper()}{emotion_tag}: {text}"
                    )
                    governor.record_turn(str(exchange["speaker"]), text)
                return accepted

            def request_stage(stage: str, n_exchanges: int, assigned_beats: List[Dict[str, Any]]) -> int:
                nonlocal stage_counter
                stage_counter += 1
                started = time.perf_counter()
                beat_numbers = [int(beat["number"]) for beat in assigned_beats]
                beat_descriptions = [str(beat["description"]) for beat in assigned_beats]
                beat_block = "\n".join(f"- Beat {number}: {description}" for number, description in zip(beat_numbers, beat_descriptions))
                completed_block = ", ".join(str(number) for number in completed_beats) or "none"
                directives = [
                    governor.plan_next_turn(stage=stage, beat_number=number, beat_description=description)
                    for number, description in zip(beat_numbers, beat_descriptions)
                ]
                directive_block = "\n\n".join(item.to_prompt_block() for item in directives)
                agenda_brief = (
                    f"\n\nBEAT-OWNED GENERATION:\n"
                    f"COMPLETED BEATS: {completed_block}\n"
                    "CRITICAL: Do not repeat any exact phrase, greeting, question, example, or claim used earlier.\n"
                    "DO NOT REPEAT the completed beat ideas above. Move the conversation forward immediately.\n"
                    f"CURRENT ASSIGNMENT:\n{beat_block}\n"
                    f"GOVERNOR DIRECTIVES:\n{directive_block}\n"
                    "RETURN ONLY DIALOGUE FOR THESE BEATS. DO NOT DISCUSS ANY OTHER BEAT."
                )
                rejection_stats = {"duplicate_rejected_lines": 0, "directive_rejected_lines": 0}
                try:
                    lines = llm_writer.generate_segment(
                        topic=topic,
                        key_points=key_points[stage_counter % len(key_points):] + key_points[:stage_counter % len(key_points)],
                        stage=stage,
                        history_lines=history_lines,
                        primary_source_summary=context.get("primary_source_summary", ""),
                        n_exchanges=n_exchanges,
                        persona_brief=persona_brief + f"\nEpisode section {episode_config.get('_section_index', 0) + 1}/{episode_config.get('_section_count', 1)}. Continue forward. Do not restart or repeat earlier material.{agenda_brief}",
                        generation_nonce=(
                            f"{generation_nonce}-forward-{stage_counter}-{stage}-{len(exchanges)}"
                        ),
                    )
                except Exception as exc:
                    lines = []
                    logger.exception("Segment stage call crashed: stage=%s requested=%d", stage, n_exchanges)
                    diagnostic = {"status": "exception", "error": str(exc)}
                else:
                    diagnostic = llm_writer.last_call_diagnostic()
                elapsed = round(time.perf_counter() - started, 3)
                returned = len(lines or [])
                stage_words = sum(len(str(line.get("text", "")).split()) for line in (lines or []))
                stage_record = {
                    "section": episode_config.get("_section_index", 0) + 1,
                    "stage": stage,
                    "requested_exchanges": n_exchanges,
                    "returned_lines": returned,
                    "returned_exchanges": returned // 2,
                    "stage_words": stage_words,
                    "cumulative_section_words": sum(len(str(e.get("text", "")).split()) for e in exchanges),
                    "elapsed_seconds": elapsed,
                    "status": diagnostic.get("status", "parse_empty" if not returned else "success"),
                    "error": diagnostic.get("error"),
                    "beat_numbers": beat_numbers,
                    "beat_descriptions": beat_descriptions,
                    "completed_beats": list(completed_beats),
                    "duplicate_rejected_lines": 0,
                    "directive_rejected_lines": 0,
                    "accepted_lines": 0,
                }
                stage_telemetry = list(episode_config.get("_stage_telemetry") or [])
                stage_telemetry.append(stage_record)
                episode_config["_stage_telemetry"] = stage_telemetry
                logger.info("LLM segment stage telemetry: %s", stage_record)
                if not lines:
                    progress = episode_config.get("_progress_callback")
                    if callable(progress):
                        progress({"section": episode_config.get("_section_index", 0) + 1, "section_count": episode_config.get("_section_count", 1),
                                  "stage": stage, "batch": stage_counter,
                                  "accepted_words": sum(len(text.split()) for text in prior_episode_texts) + sum(len(line["text"].split()) for line in exchanges),
                                  "stage_telemetry": stage_telemetry})
                    return 0
                count = append_fresh(lines, rejection_stats, directives)
                stage_record["accepted_lines"] = count
                stage_record["duplicate_rejected_lines"] = rejection_stats["duplicate_rejected_lines"]
                stage_record["directive_rejected_lines"] = rejection_stats["directive_rejected_lines"]
                stage_record["cumulative_section_words"] = sum(len(str(e.get("text", "")).split()) for e in exchanges)
                completed_beats.extend(beat_numbers)
                stage_record["completed_beats"] = list(completed_beats)
                progress = episode_config.get("_progress_callback")
                if callable(progress):
                    progress({"section": episode_config.get("_section_index", 0) + 1, "section_count": episode_config.get("_section_count", 1),
                              "stage": stage, "batch": stage_counter,
                              "accepted_words": sum(len(text.split()) for text in prior_episode_texts) + sum(len(line["text"].split()) for line in exchanges),
                              "stage_telemetry": stage_telemetry})
                return count

            for beat_offset in range(0, len(section_beats), 2):
                assigned_beats = section_beats[beat_offset:beat_offset + 2]
                stage = "opening" if beat_offset == 0 and not prior_episode_texts else "expansion"
                exchanges_requested = 2 if beat_offset == 0 else 3
                if request_stage(stage, exchanges_requested, assigned_beats) <= 0 and beat_offset == 0:
                    return None

            if not exchanges:
                return None

            if line_callback:
                for exchange in exchanges:
                    line_callback(exchange)

            logger.info(
                "[SegmentWorker] Generated forward-only %d lines / %d words for %d-minute target",
                len(exchanges),
                sum(len(e["text"].split()) for e in exchanges),
                target_minutes,
            )
            return self._conversation_to_script(exchanges)

        except Exception as exc:
            logger.warning("Segment forward generation failed: %s", exc)
            return None

    def _synthesize_segments(self, script_lines, output_dir, episode_id):
        from ..storage.episode_store import list_ads
        import json
        from .ads import ad_audio_fingerprint
        ads = {ad["ad_id"]: ad for ad in list_ads(episode_id)}
        segments, offset, block = [], 0, 0
        while offset < len(script_lines):
            line = script_lines[offset]
            ad_id = line.get("ad_id")
            end = offset + 1
            if ad_id:
                while end < len(script_lines) and script_lines[end].get("ad_id") == ad_id:
                    end += 1
                ad = ads.get(ad_id)
                if not ad or not ad.get("audio_file") or not Path(ad["audio_file"]).is_file():
                    raise RuntimeError(f"Ad {ad_id} must have produced audio before episode assembly")
                signature = ad_audio_fingerprint(script_lines[offset:end])
                if signature != ad.get("audio_script_fingerprint"):
                    raise RuntimeError(f"Ad {ad_id} audio does not match the inserted script; produce/reinsert the matching ad before assembly")
                selected_engine = self.project_config.get("tts", {}).get("primary_engine", "kokoro")
                provenance = ad.get("voice_resolution") or []
                if not provenance or any(item.get("engine") != selected_engine or
                                         item.get("resolved_voice_id") != self._resolve_voice_name(item.get("resolved_voice"), selected_engine)
                                         for item in provenance):
                    raise RuntimeError(f"Ad {ad_id} audio voice settings have changed or are unverified; produce the ad again")
                audio_file = Path(ad["audio_file"])
                if ad.get("composition", {}).get("sfx_tracks"):
                    from .ads import mix_ad_tracks
                    asset_meta = self.base_path / "episodes" / episode_id / "ads" / f"{ad_id}_assets.json"
                    assets = json.loads(asset_meta.read_text(encoding="utf-8")) if asset_meta.is_file() else []
                    mixed = mix_ad_tracks(ad, ad["composition"]["sfx_tracks"], assets)
                    audio_file = output_dir / f"{ad_id}_mixed.mp3"
                    mixed.export(audio_file, format="mp3", bitrate="192k").close()
                segments.append({"index": len(segments) + 1, "line_index": end, "speaker": ad.get("resolved_voice", ad.get("announcer_key")),
                                 "audio_file": str(audio_file), "duration_seconds": self._probe_duration_seconds(audio_file),
                                 "pause_after": 0, "engine": "saved_ad_audio", "ad_id": ad_id, "text": " ".join(item['text'] for item in script_lines[offset:end]),
                                 "voice_resolution": ad.get("voice_resolution"), "generated_by": "ad_engine"})
            else:
                while end < len(script_lines) and not script_lines[end].get("ad_id"):
                    end += 1
                block += 1
                produced = super()._synthesize_segments(script_lines[offset:end], output_dir, f"{episode_id}_block{block}")
                for item in produced:
                    item["line_index"] += offset
                    item["index"] = len(segments) + 1
                    segments.append(item)
            offset = end
        return segments

    def _concatenate_segments(
        self, segments: List[Dict[str, Any]], output_path: Path,
        media_cues_override: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Build dialogue audio, then apply episode media cues before wrapping."""
        super()._concatenate_segments(segments, output_path, media_cues_override=[])
        if not output_path.exists():
            return

        episode_id = output_path.stem
        if episode_id.endswith("_raw_mix"):
            episode_id = episode_id[: -len("_raw_mix")]
        if media_cues_override is None:
            cue_payload = load_media_cues(episode_id)
            cues = list(cue_payload.get("cues", []) or [])
        else:
            cues = list(media_cues_override)
        seen_line_cues = set()
        for segment in segments:
            for cue in segment.get("production_cues", []) or []:
                identity = (segment.get("production_line_id"), json.dumps(cue, sort_keys=True, ensure_ascii=False))
                if identity in seen_line_cues:
                    continue
                seen_line_cues.add(identity)
                try:
                    line_index = int(segment.get("line_index", 1)) - 1
                except (TypeError, ValueError):
                    line_index = 0
                cues.append({**cue, "line_number": line_index})
        if not cues:
            return

        elapsed_ms = 0
        line_end_ms: Dict[int, int] = {}
        for segment in segments:
            elapsed_ms += int(float(segment.get("duration_seconds", 0.0) or 0.0) * 1000)
            elapsed_ms += int(float(segment.get("pause_after", 0.0) or 0.0) * 1000)
            try:
                line_number = int(segment.get("line_index", 0) or 0)
            except (TypeError, ValueError):
                line_number = 0
            if line_number > 0:
                line_end_ms[line_number] = elapsed_ms

        audio = AudioSegment.from_file(str(output_path))
        resolved_cues: List[tuple[int, Dict[str, Any], Dict[str, Any]]] = []
        for cue in cues:
            asset_id = str(cue.get("asset_id") or "")
            if not asset_id:
                continue
            asset = load_library_asset(asset_id) if asset_id.startswith("lib_") else load_asset(episode_id, asset_id)
            if not asset:
                logger.warning("Media cue asset missing: %s", asset_id)
                continue
            try:
                raw_index = cue.get("line_number")
                if raw_index is None:
                    base_ms = len(audio)
                else:
                    anchor_line = max(1, int(raw_index) + 1)
                    base_ms = line_end_ms.get(anchor_line, len(audio))
            except (TypeError, ValueError):
                base_ms = len(audio)
            resolved_cues.append((base_ms, cue, asset))

        resolved_cues.sort(key=lambda item: item[0])
        inserted_shift_ms = 0
        for base_ms, cue, asset in resolved_cues:
            asset_path = Path(str(asset.get("stored_path") or ""))
            if not asset_path.exists():
                continue
            try:
                clip = AudioSegment.from_file(str(asset_path))
            except Exception as exc:
                logger.warning("Media cue could not load %s: %s", asset_path, exc)
                continue

            role = str(asset.get("role") or cue.get("display_label") or "media").lower()
            note = str(cue.get("notes") or "").lower()
            overlay = "overlay" in note or role == "sfx"
            position_ms = max(0, min(len(audio), base_ms + inserted_shift_ms))

            if overlay:
                gain_db = -8.0
                clip = clip.apply_gain(gain_db)
                audio = audio.overlay(clip, position=position_ms)
                logger.info("Media cue overlay %s at %dms", asset_path.name, position_ms)
            else:
                audio = audio[:position_ms] + clip + audio[position_ms:]
                inserted_shift_ms += len(clip)
                logger.info("Media cue insert %s at %dms", asset_path.name, position_ms)

        audio.export(str(output_path), format="mp3", bitrate="192k")
