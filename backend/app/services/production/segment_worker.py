"""Duration-aware short-form generation for Dandy Studio.

Targets from 1 to 15 minutes use a forward-only generation path. The worker
filters bad turns while the conversation is being built and does not discard a
mostly-good short script just to regenerate the entire conversation from the
beginning. Longer legacy episodes continue through the established worker path.
"""

from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .context_builder import build_rich_context
from .llm_writer import generate_segment
from .rhythm import RhythmState
from .worker import HardenedPodcastWorker

logger = logging.getLogger(__name__)


class SegmentAwarePodcastWorker(HardenedPodcastWorker):
    """Use a bounded, forward-only LLM plan for 1-15 minute segments."""

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
        current = cls._similarity_tokens(text)
        if len(current) < 4:
            return False

        for prior in prior_texts:
            previous = cls._similarity_tokens(prior)
            if len(previous) < 4:
                continue
            shared = len(current & previous)
            if not shared:
                continue
            containment = shared / max(1, min(len(current), len(previous)))
            jaccard = shared / max(1, len(current | previous))
            if containment >= 0.74 or jaccard >= 0.56:
                return True
        return False

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
        if target_minutes > 15:
            return super().generate_script(
                episode_config,
                line_callback=line_callback,
                max_retries=max_retries,
            )

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

        # One final deterministic pass across the completed segment. This never
        # asks the model to start over; it only removes bad lines that somehow
        # survived a stage boundary.
        accepted: List[Dict[str, Any]] = []
        prior_texts: List[str] = []
        seen: set[str] = set()
        for line in script:
            text = str(line.get("text", "")).strip()
            if not text or "[unknown]" in text.lower() or self._looks_incomplete(text):
                continue
            repeat_key = self.communication_layer._repeat_key(text) if self.communication_layer else " ".join(text.lower().split())
            if not repeat_key or repeat_key in seen or self._is_near_duplicate(text, prior_texts):
                continue
            seen.add(repeat_key)
            prior_texts.append(text)
            accepted.append(line)

        if not accepted:
            raise RuntimeError("Short-segment acceptance filter removed every generated line")

        for idx, line in enumerate(accepted, start=1):
            line["line_number"] = idx

        target_words = max(1, target_minutes * 155)
        word_count = sum(len(str(line.get("text", "")).split()) for line in accepted)
        logger.info(
            "[SegmentWorker] Forward-only final: %d lines / %d words for %d-minute target (%.0f%%)",
            len(accepted), word_count, target_minutes, (word_count / target_words) * 100,
        )
        return accepted

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
        target_minutes = int(
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
            target_words = target_minutes * 155
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

            generation_nonce = str(
                episode_config.get("generation_nonce")
                or f"segment-{datetime.now().isoformat()}"
            )
            exchanges: List[Dict[str, Any]] = []
            seen_text: set[str] = set()
            history_lines: List[str] = []
            stage_counter = 0

            def append_fresh(lines: List[Dict[str, Any]]) -> int:
                accepted = 0
                prior_texts = [str(exchange.get("text", "")) for exchange in exchanges]
                for line in lines:
                    text = str(line.get("text", "")).strip()
                    if not text:
                        continue
                    if self._looks_incomplete(text):
                        logger.info("[SegmentWorker] Dropped incomplete turn: %s", text[:90])
                        continue
                    repeat_key = self.communication_layer._repeat_key(text)
                    if not repeat_key or repeat_key in seen_text:
                        logger.info("[SegmentWorker] Dropped exact repeat: %s", text[:90])
                        continue
                    if self._is_near_duplicate(text, prior_texts):
                        logger.info("[SegmentWorker] Dropped near-repeat: %s", text[:90])
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
                    exchanges.append(exchange)
                    prior_texts.append(text)
                    accepted += 1
                    emotion = (line.get("emotional_state") or {}).get("primary", "")
                    emotion_tag = f" [{emotion}]" if emotion else ""
                    history_lines.append(
                        f"{str(exchange['speaker']).upper()}{emotion_tag}: {text}"
                    )
                return accepted

            def request_stage(stage: str, n_exchanges: int) -> int:
                nonlocal stage_counter
                stage_counter += 1
                lines = generate_segment(
                    topic=topic,
                    key_points=key_points,
                    stage=stage,
                    history_lines=history_lines,
                    primary_source_summary=context.get("primary_source_summary", ""),
                    n_exchanges=n_exchanges,
                    persona_brief=persona_brief,
                    generation_nonce=(
                        f"{generation_nonce}-forward-{stage_counter}-{stage}-{len(exchanges)}"
                    ),
                )
                if not lines:
                    return 0
                return append_fresh(lines)

            opening_exchanges = 1 if target_minutes <= 3 else 2
            if request_stage("opening", opening_exchanges) <= 0:
                return None

            if target_minutes <= 3:
                middle_exchanges = 1
                max_middle_batches = 10
            elif target_minutes <= 8:
                middle_exchanges = 3
                max_middle_batches = 12
            else:
                middle_exchanges = 4
                max_middle_batches = 14

            stalled_batches = 0
            for batch_index in range(max_middle_batches):
                current_words = sum(len(e["text"].split()) for e in exchanges)
                if current_words >= target_words * 0.90:
                    break
                stage = "expansion" if batch_index % 2 == 0 else "deepening"
                accepted_count = request_stage(stage, middle_exchanges)
                stalled_batches = stalled_batches + 1 if accepted_count <= 0 else 0
                if stalled_batches >= 3:
                    break

            # If duplicate/incomplete filtering removed too much material, continue
            # forward from retained history instead of throwing everything away.
            continuation_budget = 4
            while continuation_budget > 0:
                current_words = sum(len(e["text"].split()) for e in exchanges)
                if current_words >= target_words * 0.88:
                    break
                accepted_count = request_stage("deepening", 1)
                continuation_budget -= 1
                if accepted_count <= 0 and continuation_budget <= 1:
                    break

            current_words = sum(len(e["text"].split()) for e in exchanges)
            if current_words < target_words * 0.96:
                request_stage("reflection", 1)
            request_stage("closing", 1)

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
            logger.warning(
                "Segment forward generation failed: %s",
                exc,
            )
            return None
