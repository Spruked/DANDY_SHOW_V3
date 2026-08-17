"""Duration-aware short-form generation for Dandy Studio.

New episode creation is treated as segment generation for targets from 1 to
15 minutes. Longer legacy episodes continue through the existing worker path.
The segment writer uses the existing Phil/Jim personas, LLM writer, quality
guard, and audio production pipeline, but scales generation batches to the
requested duration instead of forcing a 30-45 minute conversation plan.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Callable, Dict, List, Optional

from .llm_writer import generate_segment
from .rhythm import RhythmState
from .worker import HardenedPodcastWorker

logger = logging.getLogger(__name__)


class SegmentAwarePodcastWorker(HardenedPodcastWorker):
    """Use a bounded, duration-aware LLM plan for 1-15 minute segments."""

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

        # Preserve the established long-form path for existing legacy episodes.
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

            def append_fresh(lines: List[Dict[str, Any]]) -> None:
                for line in lines:
                    raw_text = str(line.get("text", "")).strip()
                    if not raw_text:
                        continue
                    text = self.communication_layer._apply_rhythm_to_text(raw_text, rhythm)
                    repeat_key = self.communication_layer._repeat_key(text)
                    if not repeat_key or repeat_key in seen_text:
                        continue
                    seen_text.add(repeat_key)
                    exchange = {
                        "speaker": line.get("speaker", "Phil"),
                        "text": text,
                        "emotional_state": line.get("emotional_state", {}),
                        "timestamp": line.get("timestamp", datetime.now().isoformat()),
                        "rhythm": rhythm.to_dict(),
                        "timing": context.get("timing_profile", "balanced"),
                        "generated_by": line.get("generated_by", "llm_writer"),
                    }
                    exchanges.append(exchange)
                    emotion = (line.get("emotional_state") or {}).get("primary", "")
                    emotion_tag = f" [{emotion}]" if emotion else ""
                    history_lines.append(
                        f"{str(exchange['speaker']).upper()}{emotion_tag}: {text}"
                    )

            def request_stage(stage: str, n_exchanges: int) -> bool:
                lines = generate_segment(
                    topic=topic,
                    key_points=key_points,
                    stage=stage,
                    history_lines=history_lines,
                    primary_source_summary=context.get("primary_source_summary", ""),
                    n_exchanges=n_exchanges,
                    persona_brief=persona_brief,
                    generation_nonce=(
                        f"{generation_nonce}-attempt{attempt + 1}-{stage}-{len(exchanges)}"
                    ),
                )
                if not lines:
                    return False
                append_fresh(lines)
                return True

            # Short targets use smaller batches so the model can stop close to the
            # requested duration instead of overshooting with a long fixed plan.
            opening_exchanges = 1 if target_minutes <= 3 else 2
            if not request_stage("opening", opening_exchanges):
                return None

            if target_minutes <= 3:
                middle_exchanges = 1
                max_middle_batches = 6
            elif target_minutes <= 8:
                middle_exchanges = 3
                max_middle_batches = 8
            else:
                middle_exchanges = 4
                max_middle_batches = 10

            for batch_index in range(max_middle_batches):
                current_words = sum(len(e["text"].split()) for e in exchanges)
                # Reach most of the requested duration with substantive body
                # material, then use reflection/closing to land near the target.
                if current_words >= target_words * 0.86:
                    break
                stage = "expansion" if batch_index % 2 == 0 else "deepening"
                if not request_stage(stage, middle_exchanges):
                    break

            current_words = sum(len(e["text"].split()) for e in exchanges)
            if current_words < target_words * 0.94:
                request_stage("reflection", 1)
            request_stage("closing", 1)

            if not exchanges:
                return None

            if line_callback:
                for exchange in exchanges:
                    line_callback(exchange)

            logger.info(
                "[SegmentWorker] Generated %d lines / %d words for %d-minute target",
                len(exchanges),
                sum(len(e["text"].split()) for e in exchanges),
                target_minutes,
            )
            return self._conversation_to_script(exchanges)

        except Exception as exc:
            logger.warning(
                "Segment generation attempt %d failed: %s",
                attempt + 1,
                exc,
            )
            return None
