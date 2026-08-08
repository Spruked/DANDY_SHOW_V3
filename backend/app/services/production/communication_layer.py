from datetime import datetime
import logging
import re
from typing import Dict, List, Optional

import networkx as nx

from .rhythm import RhythmState

logger = logging.getLogger(__name__)

# Cached once per process — avoids probing every call.
_BRIDGE_REACHABLE: Optional[bool] = None


def _is_bridge_reachable() -> bool:
    global _BRIDGE_REACHABLE
    if _BRIDGE_REACHABLE is None:
        from . import llm_writer
        _BRIDGE_REACHABLE = llm_writer.check_bridge()
        if _BRIDGE_REACHABLE:
            logger.info("LLM governance bridge reachable — using LLM generation path")
        else:
            logger.info("LLM governance bridge unavailable — falling back to SKG path")
    return _BRIDGE_REACHABLE


class DandyCommunicationLayer:
    def __init__(self, phil_skg, jim_skg):
        self.phil = phil_skg
        self.jim = jim_skg
        self.conversation_history: List[Dict] = []
        self.banter_evolution = nx.DiGraph()
        self.personality_settings: Dict = {}

    def orchestrate_banter(
        self,
        episode_script: Dict,
        audience_feedback: Optional[List] = None,
        line_callback=None,
    ) -> List[Dict]:
        self.personality_settings = episode_script.get("personality_settings", {}) or {}
        self.conversation_history = []
        conversation: List[Dict] = []
        topics = episode_script.get("topics") or [episode_script.get("topic", "general")]
        rhythm = RhythmState.from_context(episode_script)
        episode_script = dict(episode_script)
        episode_script["rhythm"] = rhythm.to_dict()

        for topic in topics:
            topic_conversation = self._generate_topic_banter(topic, episode_script, rhythm, line_callback)
            conversation.extend(topic_conversation)
            self._learn_from_segment(topic_conversation, audience_feedback)

        self.conversation_history.extend(conversation)
        return conversation

    # Varied pool values so template slots don't all collapse to the same topic string.
    _ABSURD_COMPARISONS = [
        "an expensive fortune cookie",
        "a Magic 8-Ball in a suit",
        "a fax machine with better marketing",
        "a really ambitious spreadsheet",
        "a calculator that went to grad school",
        "a chatty encyclopedia",
        "a library card catalog with anxiety",
    ]
    _ANALOG_COMPARISONS = [
        "a library card catalogue",
        "a rotary phone with Wi-Fi",
        "a VHS tape of the future",
        "a chalkboard that learned Python",
        "a paper map with live traffic",
    ]
    _DEEPER_QUESTION_TEMPLATES = [
        "what {topic} really means for people who can't afford to get it wrong",
        "whether {topic} is solving the problem or just renaming it",
        "who actually benefits when {topic} goes mainstream",
        "what the cost of being wrong about {topic} looks like in five years",
        "whether anyone's pressure-tested {topic} outside of ideal conditions",
    ]

    def _load_primary_source(self, script):
        from collections import Counter
        from pathlib import Path

        try:
            from ..storage.episode_store import list_assets
        except Exception:
            return {}

        episode_id = script.get("episode_id")
        if not episode_id:
            return {}

        source_roles = {"primary_source", "reference", "context"}
        source_assets = [
            asset for asset in list_assets(episode_id)
            if str(asset.get("role", "")).lower() in source_roles
        ]
        if not source_assets:
            return {}

        def read_text(path: Path) -> str:
            suffix = path.suffix.lower()
            if suffix in {".txt", ".md"}:
                return path.read_text(encoding="utf-8", errors="ignore")
            if suffix == ".pdf":
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(str(path))
                    return "\n\n".join((page.extract_text() or "") for page in reader.pages)
                except Exception:
                    try:
                        import pdfplumber

                        with pdfplumber.open(str(path)) as pdf:
                            return "\n\n".join((page.extract_text() or "") for page in pdf.pages)
                    except Exception:
                        return ""
            return ""

        primary_text = ""
        for asset in source_assets:
            path = Path(str(asset.get("stored_path", "")))
            if not path.exists():
                continue
            primary_text = read_text(path)
            if primary_text.strip():
                break

        primary_text = primary_text.strip()
        if not primary_text:
            return {}

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", primary_text) if p.strip()]
        summary = "\n\n".join(paragraphs[:3])
        words = re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", primary_text.lower())
        stopwords = {
            "about", "after", "again", "also", "because", "been", "before", "being", "between",
            "could", "does", "down", "from", "have", "into", "just", "like", "more", "most",
            "only", "other", "over", "said", "same", "some", "than", "that", "their", "them",
            "then", "there", "these", "they", "this", "those", "through", "what", "when",
            "where", "which", "while", "with", "would", "your",
        }
        keywords = [word for word, _ in Counter(w for w in words if w not in stopwords).most_common(20)]
        return {
            "primary_source_text": primary_text,
            "primary_source_summary": summary,
            "primary_source_keywords": keywords,
        }

    def _build_context(self, topic: str, script: Dict) -> Dict:
        """Build a varied context dict — each slot gets a distinct value, never all=topic."""
        import random
        key_points = [kp for kp in script.get("key_points", []) if kp]
        title = script.get("title") or topic
        metadata = script.get("metadata", {}) or {}
        primary = self._load_primary_source(script)
        rhythm = RhythmState.from_context(script)
        rich_context = {
            key: value
            for key, value in dict(script.get("_rich_context") or {}).items()
            if value not in (None, "")
        }

        # Rotate through key_points so each call uses a different slice.
        # Shuffle a copy so consecutive banter rounds don't repeat in the same order.
        shuffled = list(key_points)
        if len(shuffled) > 1:
            random.shuffle(shuffled)

        def kp(idx: int, fallback: str = topic) -> str:
            return shuffled[idx] if idx < len(shuffled) else fallback

        # Extract short noun phrases from a key_point for tighter slot fillers.
        def short(text: str, words: int = 4) -> str:
            return " ".join(text.split()[:words]).rstrip(".,;:")

        deeper_q = random.choice(self._DEEPER_QUESTION_TEMPLATES).format(topic=topic)

        context = {
            # Core routing keys used by communication_layer itself
            "current_topic": topic,
            "script_points": key_points,
            "audience": script.get("audience", "general"),
            "intensity": script.get("intensity", "medium"),
            # Template variables expected by Phil and Jim SKG templates
            "topic": topic,
            "title": title,
            "possibility": kp(0),
            "thing": short(kp(0)),
            "idea": kp(0),
            "thought": kp(1, topic),
            "connection": kp(1, f"the broader impact of {topic}"),
            "connected_idea": short(kp(1, kp(0))),
            "domain": short(kp(0), 3),
            "reason": kp(2, kp(0)),
            "insight": short(kp(0)),
            "correction_or_deeper_thought": kp(1, f"the other side of {topic}"),
            "deeper_question": deeper_q,
            "product": short(kp(0), 3),
            "absurd_comparison": random.choice(self._ABSURD_COMPARISONS),
            "conventional_thing": short(kp(0), 3),
            "unconventional_thing": short(kp(1, kp(0)), 4),
            "common_belief": f"everyone understands {short(kp(0), 3)}",
            "clarification_attempt": f"the part about {short(kp(0), 4)}",
            "practical_objection": f"does {short(kp(0), 4)} actually hold up in practice",
            "reality_check": f"the real cost of {short(kp(0), 4)}",
            "tech_product": short(kp(0), 3),
            "tech_trend": short(kp(1, kp(0)), 3),
            "analog_comparison": random.choice(self._ANALOG_COMPARISONS),
            "tech_space": short(kp(0), 3),
            "obvious_thing": short(kp(0)),
            "hidden_thing": short(kp(1, f"the human side of {topic}")),
            "tool": short(kp(0), 3),
            "realization": short(kp(0)),
            "market": short(kp(1, topic), 3),
            "trend": short(kp(0), 4),
            "opportunity": short(kp(1, kp(0)), 4),
            "industry": short(kp(0), 2),
            "sector": short(kp(1, topic), 2),
            "hidden_dynamic": short(kp(2, kp(0))),
            "tech_gadget": short(kp(0), 3),
            "count": random.choice(["three", "four", "a handful of", "a dozen"]),
            "feature": short(kp(0), 4),
            "car_feature": short(kp(0), 3),
            "car_spec": short(kp(1, kp(0)), 3),
            "next_point": short(kp(1, kp(0))),
            "related": short(kp(2, kp(1, topic))),
            "point": short(kp(0)),
            # Rhythm routing keys used by thinker/harmonizer consumers
            "rhythm": rhythm.to_dict(),
            "interaction_tempo": rhythm.interaction_tempo,
            "cognitive_intensity": rhythm.cognitive_intensity,
            "verbosity": rhythm.verbosity,
            "human_load": rhythm.human_load,
            "desync_risk": rhythm.desync_risk,
            "timing_profile": "stretch" if rhythm.interaction_tempo == "slow" else "tight" if rhythm.interaction_tempo == "fast" else "balanced",
            "suggest_pause": bool(rhythm.human_load >= 0.70 or rhythm.desync_risk >= 0.70),
        }
        context.update(rich_context)
        context["current_topic"] = topic
        context["topic"] = topic
        context["title"] = title
        context["script_points"] = key_points
        context["rhythm"] = rhythm.to_dict()
        context["title"] = script.get("episode_title") or topic
        context["idea"] = script.get("core_idea") or metadata.get("core_idea") or topic
        context["connection"] = metadata.get("connection") or context["idea"]
        context["insight"] = metadata.get("insight") or context["idea"]
        context["connected_idea"] = metadata.get("connected_idea") or context["connection"]
        context["point"] = metadata.get("point") or context["insight"]
        if primary:
            context["primary_source_text"] = primary["primary_source_text"]
            context["primary_source_summary"] = primary["primary_source_summary"]
            context["primary_source_keywords"] = primary["primary_source_keywords"]
            context["primary_source_priority"] = True
        return context

    def _try_llm_topic_banter(
        self,
        topic: str,
        script: Dict,
        context: Dict,
        rhythm: RhythmState,
        line_callback=None,
    ) -> List[Dict]:
        """
        Generate topic banter via the governed LLM bridge.
        Returns [] to signal the caller should fall back to SKG.
        line_callback is only fired after all segments succeed to avoid
        partial side-effects if an early segment fails.
        """
        if not _is_bridge_reachable():
            return []

        from . import llm_writer

        key_points = context.get("script_points") or [topic]
        source_summary = context.get("primary_source_summary", "")
        target_words = int(script.get("target_word_count", 5000))
        persona_brief = self._build_persona_brief(context)
        generation_nonce = str(script.get("generation_nonce") or datetime.now().isoformat())

        exchanges: List[Dict] = []
        seen_text: set = set()
        history_lines: List[str] = []

        # Stage plan: opening once, then expansion+deepening pairs until near
        # target, then reflection+closing to land cleanly.
        STAGE_PLAN = [
            ("opening", 4),
            ("expansion", 6),
            ("deepening", 6),
            ("expansion", 6),
            ("deepening", 6),
            ("expansion", 6),
            ("deepening", 6),
            ("expansion", 6),
            ("deepening", 6),
            ("reflection", 4),
            ("closing", 3),
        ]

        first_segment = True
        for stage, n in STAGE_PLAN:
            current_words = sum(len(e["text"].split()) for e in exchanges)
            if current_words >= target_words * 0.90 and stage in ("expansion", "deepening"):
                continue

            lines = llm_writer.generate_segment(
                topic=topic,
                key_points=key_points,
                stage=stage,
                history_lines=history_lines,
                primary_source_summary=source_summary,
                n_exchanges=n,
                persona_brief=persona_brief,
                generation_nonce=f"{generation_nonce}-{stage}-{len(exchanges)}",
            )

            if not lines:
                if first_segment:
                    logger.warning("LLM: first segment empty for topic=%r — falling back to SKG", topic)
                    return []
                logger.warning("LLM: segment empty for stage=%s — using partial output", stage)
                break

            first_segment = False
            for line in lines:
                line["text"] = self._apply_rhythm_to_text(line["text"], rhythm)
                exchange = {
                    "speaker": line["speaker"],
                    "text": line["text"],
                    "emotional_state": line.get("emotional_state", {}),
                    "timestamp": line.get("timestamp", datetime.now().isoformat()),
                    "rhythm": rhythm.to_dict(),
                    "timing": context.get("timing_profile", "balanced"),
                    "generated_by": line.get("generated_by", "llm_writer"),
                }
                key = self._repeat_key(exchange["text"])
                if exchange["text"] and key not in seen_text:
                    seen_text.add(key)
                    exchanges.append(exchange)
                    em = (line.get("emotional_state") or {}).get("primary", "")
                    em_tag = f" [{em}]" if em else ""
                    history_lines.append(
                        f"{exchange['speaker'].upper()}{em_tag}: {exchange['text']}"
                    )

        if line_callback and exchanges:
            for ex in exchanges:
                line_callback(ex)

        return exchanges

    def _build_persona_brief(self, context: Dict) -> str:
        def describe(name: str, skg) -> str:
            parts = [name]
            for attr in (
                "CORE_PERSONALITY",
                "VOICE_CHARACTERISTICS",
                "CONVERSATION_STYLE",
                "BROTHER_DYNAMIC",
                "PERSONALITY_TRAITS",
            ):
                value = getattr(skg, attr, None)
                if value:
                    parts.append(f"{attr}: {value}")
            return "\n".join(parts)

        settings = self.personality_settings or context.get("personality_settings") or {}
        return "\n\n".join(
            [
                describe("Phil", self.phil),
                describe("Jim", self.jim),
                f"Runtime persona settings: {settings}",
                f"Template family is advisory only: {context.get('skg_template_family')}",
            ]
        )

    def _generate_topic_banter(self, topic: str, script: Dict, rhythm: RhythmState, line_callback=None) -> List[Dict]:
        exchanges: List[Dict] = []
        seen_text: set[str] = set()
        context = self._build_context(topic, script)
        template_domain = self._select_template_domain(context)
        context["template_domain"] = template_domain
        context["skg_template_family"] = template_domain

        llm_exchanges = self._try_llm_topic_banter(topic, script, context, rhythm, line_callback)
        if llm_exchanges:
            return llm_exchanges

        if script.get("require_llm", True):
            raise RuntimeError("LLM writer required but returned no usable dialogue")

        logger.info("SKG path active for topic=%r", topic)
        stages = ["opening", "expansion", "deepening", "reflection", "closing"]
        stage_round_span = 10
        current_stage_index = 0

        conversation_stage = stages[current_stage_index]
        context["conversation_stage"] = conversation_stage
        phil_response = self.phil.generate_response(context, conversation_stage=conversation_stage)
        phil_text = self._apply_rhythm_to_text(phil_response.get("text", ""), rhythm)
        phil_exchange = {
            "speaker": "Phil",
            "text": phil_text,
            "emotional_state": phil_response.get("emotional_state", {}),
            "timestamp": datetime.now().isoformat(),
            "rhythm": rhythm.to_dict(),
            "timing": context.get("timing_profile", "balanced"),
        }
        self._append_if_fresh(exchanges, phil_exchange, seen_text, line_callback)

        current_stage_index = 1
        conversation_stage = stages[current_stage_index]
        context["conversation_stage"] = conversation_stage
        jim_response = self.jim.generate_response(context, phil_text)
        jim_text = self._apply_rhythm_to_text(jim_response.get("text", ""), rhythm)
        jim_exchange = {
            "speaker": "Jim",
            "text": jim_text,
            "emotional_state": jim_response.get("emotional_state", {}),
            "brotherly_dynamic": jim_response.get("brotherly_dynamic"),
            "timestamp": datetime.now().isoformat(),
            "rhythm": rhythm.to_dict(),
            "timing": context.get("timing_profile", "balanced"),
        }
        self._append_if_fresh(exchanges, jim_exchange, seen_text, line_callback)

        target_words = int(script.get("target_word_count", 5000))
        if rhythm.human_load >= 0.75:
            target_words = max(1200, int(target_words * 0.70))
        elif rhythm.interaction_tempo == "fast":
            target_words = max(1800, int(target_words * 0.88))
        elif rhythm.interaction_tempo == "slow":
            target_words = int(target_words * 0.96)
        max_rounds = 500  # safety cap — stops well before this in practice
        if rhythm.human_load >= 0.75:
            max_rounds = 180
        elif rhythm.interaction_tempo == "fast":
            max_rounds = 260
        round_idx = 0
        while round_idx < max_rounds:
            current_words = sum(len(e["text"].split()) for e in exchanges)
            if current_words >= target_words:
                break
            if current_words >= target_words * 0.90:
                current_stage_index = len(stages) - 1
            else:
                current_stage_index = min(1 + (round_idx // stage_round_span), len(stages) - 2)
            conversation_stage = stages[current_stage_index]

            context["round_index"] = round_idx + 1
            context["previous_exchange"] = jim_text
            context["recent_lines"] = [entry["text"] for entry in exchanges[-8:]]
            context["conversation_stage"] = conversation_stage

            phil_followup = self.phil.generate_response(
                context,
                jim_text,
                conversation_stage=conversation_stage,
                jim_response=jim_response,
            )
            phil_followup_text = self._apply_rhythm_to_text(phil_followup.get("text", ""), rhythm)
            phil_exchange = {
                "speaker": "Phil",
                "text": phil_followup_text,
                "emotional_state": phil_followup.get("emotional_state", {}),
                "timestamp": datetime.now().isoformat(),
                "rhythm": rhythm.to_dict(),
                "timing": context.get("timing_profile", "balanced"),
            }
            self._append_if_fresh(exchanges, phil_exchange, seen_text, line_callback)

            current_words = sum(len(e["text"].split()) for e in exchanges)
            if current_words >= target_words * 0.90:
                current_stage_index = len(stages) - 1
            else:
                current_stage_index = min(1 + (round_idx // stage_round_span), len(stages) - 2)
            conversation_stage = stages[current_stage_index]
            context["conversation_stage"] = conversation_stage
            jim_response = self.jim.generate_response(context, phil_followup_text)
            jim_text = self._apply_rhythm_to_text(jim_response.get("text", ""), rhythm)
            jim_exchange = {
                "speaker": "Jim",
                "text": jim_text,
                "emotional_state": jim_response.get("emotional_state", {}),
                "brotherly_dynamic": jim_response.get("brotherly_dynamic"),
                "timestamp": datetime.now().isoformat(),
                "rhythm": rhythm.to_dict(),
                "timing": context.get("timing_profile", "balanced"),
            }
            self._append_if_fresh(exchanges, jim_exchange, seen_text, line_callback)

            round_idx += 1

        return exchanges

    def _select_template_domain(self, context: Dict) -> str:
        metadata = context.get("metadata", {}) or {}
        searchable = " ".join(
            [
                str(context.get("topic", "")),
                str(context.get("episode_title", "")),
                str(context.get("episode_type", "")),
                str(metadata),
            ]
        ).lower()
        personal_keywords = [
            "happy toes",
            "abby",
            "poem",
            "fatherhood",
            "legacy",
            "incarceration",
            "literary",
            "reinterpretation",
            "book",
        ]
        if any(keyword in searchable for keyword in personal_keywords):
            return "phil_jim_personal_story"
        return "phil_jim_generic"

    def _append_if_fresh(self, exchanges: List[Dict], exchange: Dict, seen_text: set[str], line_callback=None) -> bool:
        text = str(exchange.get("text", "")).strip()
        key = self._repeat_key(text)
        if not text or key in seen_text:
            return False
        exchange.setdefault("generated_by", "skg_template")
        seen_text.add(key)
        exchanges.append(exchange)
        if line_callback:
            line_callback(exchange)
        return True

    @staticmethod
    def _repeat_key(text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
        normalized = re.sub(r"[^a-z0-9 '\-]", "", normalized)
        return normalized

    def _apply_rhythm_to_text(self, text: str, rhythm: RhythmState) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        if rhythm.verbosity == "high" and rhythm.human_load < 0.70:
            return raw
        max_words = 42
        if rhythm.verbosity == "low" or rhythm.human_load >= 0.80:
            max_words = 26
        elif rhythm.human_load >= 0.70 or rhythm.cognitive_intensity == "light":
            max_words = 34
        elif rhythm.verbosity == "high":
            max_words = 56
        words = raw.split()
        if len(words) <= max_words:
            return raw
        trimmed = " ".join(words[:max_words]).rstrip(".,;: ")
        return f"{trimmed}."

    def _needs_de_escalation(self, exchanges: List[Dict]) -> bool:
        """Kept for external callers; no longer used by _generate_topic_banter."""
        for exchange in exchanges[-2:]:
            frustration = exchange.get("emotional_state", {}).get("frustration", 0)
            if frustration and frustration > 3:
                return True
        return False

    def _learn_from_segment(self, conversation: List[Dict], audience_feedback: Optional[List]):
        if not audience_feedback:
            return

        positive_feedback = [item for item in audience_feedback if item.get("response") == "positive"]
        for feedback in positive_feedback:
            timestamp = feedback.get("timestamp")
            relevant_exchange = next((entry for entry in conversation if entry["timestamp"] == timestamp), None)
            if not relevant_exchange:
                continue

            pattern = {
                "speaker": relevant_exchange["speaker"],
                "topic": feedback.get("topic"),
                "humor_style": self._extract_humor_pattern(relevant_exchange["text"]),
                "audience_score": feedback.get("score", 0),
            }

            if hasattr(self.phil, "learn_from_interaction"):
                self.phil.learn_from_interaction({"pattern": pattern, "success": True})
            if hasattr(self.jim, "learn_from_interaction"):
                self.jim.learn_from_interaction({"pattern": pattern, "success": True})

    def _extract_humor_pattern(self, text: str) -> str:
        if "!" in text and "?" in text:
            return "exclamation_question"
        if "!" in text:
            return "enthusiastic"
        if "?" in text:
            return "skeptical"
        return "neutral"
