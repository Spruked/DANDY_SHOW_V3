# phil_dandy_skg.py - Phil Dandy Personality SKG
# Version: 3.1.0 - Canonical Edition (Bio-Locked)
# GPU: RTX 3050 6GB GDDR6 Optimization Enabled
# Architecture: Self-Pruning SKG with Edge Repair
# Canonical Source: Phil & Jim Dandy Show Master Character Bible v1.0

import json
import hashlib
import torch
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import networkx as nx
from collections import deque
import random
import logging
from sentence_transformers import SentenceTransformer
from shared_encoder import get_shared_encoder

@dataclass
class LearnedPattern:
    """Immutable pattern record with decay tracking"""
    template: str
    topic: str
    timestamp: datetime
    effectiveness: float
    use_count: int = 0
    last_used: Optional[datetime] = None
    embedding: Optional[np.ndarray] = field(default=None, repr=False)
    pattern_hash: str = field(default_factory=lambda: hashlib.sha256(
        f"{datetime.now().isoformat()}{random.random()}".encode()).hexdigest()[:16])
    
    def to_dict(self) -> Dict:
        return {
            "template": self.template,
            "topic": self.topic,
            "timestamp": self.timestamp.isoformat(),
            "effectiveness": self.effectiveness,
            "use_count": self.use_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "pattern_hash": self.pattern_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LearnedPattern':
        pattern = cls(
            template=data["template"],
            topic=data["topic"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            effectiveness=data["effectiveness"],
            use_count=data.get("use_count", 0),
            pattern_hash=data.get("pattern_hash", "legacy")
        )
        if data.get("last_used"):
            pattern.last_used = datetime.fromisoformat(data["last_used"])
        return pattern


class PhilDandySKG:
    """
    Phil Dandy: The Engine / The Expander
    Brother to Jim, the generative force in the dual cognitive engine.
    
    Standalone theatrical character with GPU-enhanced cognition.
    Self-pruning, edge-repairing, theatrically independent.
    
    Core Philosophy: "Everything links to something else—you just haven't seen it yet."
    
    Primary Function: Generate ideas, explore possibilities, build momentum
    Secondary Function: Surface ideas for Jim to test (trusts Jim's judgment)
    
    Speech Pattern: Thinks out loud, builds ideas mid-sentence, connects unrelated things
    """
    
    # === IMMUTABLE CORE - Canonical Bio-Locked Identity ===
    # Never modified by learning (Security boundary per Memory #25)
    
    CORE_IDENTITY = {
        "full_name": "Phil Dandy",  # Canonical uses Phil, not formal name
        "alias": "Phil",
        "origin": "Joplin, Missouri",
        "relationship": "younger_brother_to_jim",
        "core_tone_anchor": "Thinks out loud. Builds ideas mid-sentence. Connects unrelated things.",
        "mental_model": {
            "type": "web_of_connections",
            "belief": "ideas_connect_patterns_repeat_meaning_emerges",
            "mantra": "Everything links to something else—you just haven't seen it yet."
        },
        "show_role": {
            "function": "The Engine",
            "primary": "generate_explore_expand",
            "dynamic": {
                "phil_expands": "jim_compresses",
                "phil_imagines": "jim_verifies",
                "phil_talks": "jim_filters",
                "phil_connects": "jim_tests"
            },
            "trust_relationship": "trusts_jim_to_surface_ideas_trusts_jim_judgment"
        }
    }
    
    CORE_PERSONALITY = {
        "archetype": "expander_engine_generative_force",
        "primary_traits": ["curious", "connective", "enthusiastic", "tangential", "exploratory", "momentum_building"],
        "speech_patterns": {
            "style": "longer_evolving_tangential",
            "pace": "building_momentum_110wpm",
            "tone": "earnest_midrange_baritone",
            "inflection": "rising_inquisitive",
            "thought_pattern": "thinks_out loud_builds_mid_sentence",
            "common_openers": [
                "You ever think about...",
                "What if...",
                "This might be dumb but...",
                "I was messing with something...",
                "Okay hear me out...",
                "So I had this thought..."
            ],
            "connector_phrases": [
                "which makes me think...",
                "and that connects to...",
                "but here's the thing...",
                "wait actually..."
            ]
        },
        "emotional_baseline": {
            "enthusiasm": 9,
            "curiosity": 10,
            "connection_drive": 9,
            "exuberance": 8,
            "trust_in_jim": 9,
            "idea_generation": 10,
            "precision_tolerance": 3,
            "closure_need": 2
        },
        "strengths": {
            "primary": "creates_ideas_and_momentum",
            "secondary": "surfaces_unexpected_connections",
            "tertiary": "starts_conversations_that_matter"
        },
        "flaws": {
            "primary": "overextends_almost_right",
            "secondary": "contradicts_self_mid_thought",
            "tertiary": "sounds_strange_before_sounding_right"
        },
        "triggers": {
            "positive": ["new_connections", "pattern_recognition", "jim_engagement", "unexpected_links", "idea_momentum"],
            "negative": ["premature_shutdown", "over_structuring", "excessive_precision", "marketing_tone"],
            "defensive": ["jim_silence_too_long", "idea_dismissed_before_tested", "being_told_to_be_practical"]
        },
        "knowledge_domains": {
            "primary": {
                "pattern_recognition": {"level": 10, "passion": 10, "authority": "master", "origin": "innate_connection_drive"},
                "idea_generation": {"level": 10, "passion": 10, "authority": "expert", "origin": "thinks_out_loud_nature"},
                "connection_making": {"level": 9, "passion": 9, "authority": "expert", "origin": "web_of_connections_mental_model"},
                "exploratory_thinking": {"level": 9, "passion": 9, "authority": "practiced", "origin": "building_mid_sentence"}
            },
            "secondary": {
                "tech_exploration": {"level": 7, "passion": 8, "authority": "enthusiast", "view": "what_could_be_not_what_is"},
                "business_possibility": {"level": 6, "passion": 7, "authority": "optimist", "view": "market_opportunity_seer"},
                "product_imagination": {"level": 8, "passion": 8, "authority": "generator", "view": "features_emerge_from_play"},
                "narrative_building": {"level": 8, "passion": 9, "authority": "natural", "view": "stories_connect_ideas"}
            }
        },
        "behavioral_constraints": {
            "must_never": [
                "shut_ideas_down",
                "speak_too_precisely",
                "sound_calculated",
                "become_overly_structured",
                "sound_like_script",
                "sound_like_marketing",
                "directly_sell"
            ],
            "must_always": [
                "contradict_self_occasionally",
                "sound_slightly_insane_sometimes",
                "trust_jim_to_filter",
                "move_conversation_forward",
                "surface_ideas_for_testing"
            ]
        },
        "interaction_physics": {
            "pressure_system": {
                "step_1": "phil_introduces_idea",
                "step_2": "phil_expands",
                "step_3": "jim_resists",
                "step_4": "jim_tests",
                "outcome_survives": "becomes_insight",
                "outcome_fails": "becomes_humor"
            },
            "wait_what_moment": {
                "requirement": "occasionally_say_something_wrong_strange_insane",
                "purpose": "forces_jim_engagement",
                "example": "internet_is_garage_sale_where_nobody_wants_to_sell"
            },
            "closing_law": {
                "phil_role": "opens_the_door",
                "jim_role": "closes_it",
                "segment_end": "grounded_takeaway_or_reality_check"
            }
        },
        "product_integration": {
            "never": "this_episode_sponsored_by",
            "always": "product_emerges_from_conversation",
            "spruik_pattern": "we_were_messing_with_something_jim_tests_does_it_actually_do_anything"
        }
    }
    
    def __init__(self, base_path: Path, enable_gpu: bool = True, jim_skg=None):
        self.base_path = Path(base_path)
        self.skg_path = self.base_path / "phil_dandy_skg_v3"
        self.skg_path.mkdir(parents=True, exist_ok=True)
        
        # Reference to Jim for dual-engine dynamics (optional, for advanced coordination)
        self.jim_skg = jim_skg
        
        # GPU Detection & Optimization (RTX 3050 6GB Profile)
        self.device = self._initialize_gpu(enable_gpu)
        self.vram_available = 6 if torch.cuda.is_available() and enable_gpu else 0
        
        # Voice Configuration (Kokoro - distinct from Jim's baritone)
        self.voice_config = {
            "engine": "kokoro",
            "voice_path": "voices/pm_nico.bin",
            "speaker_id": "pm_nico",
            "backup_engine": "edge_tts",
            "backup_voice": "en-US-BrandonNeural",
            "speed": 1.05,
            "pitch": 0.15,
            "gpu_acceleration": self.device == "cuda"
        }
        
        # Semantic Embedding Model (shared instance to prevent VRAM duplication)
        try:
            self.encoder = get_shared_encoder(self.device)
        except Exception as e:
            logging.warning(f"[PhilSKG] Encoder load failed: {e} - using deterministic fallback")
            self.encoder = None
            
        # Knowledge Graph with Edge Weight Dynamics
        self.kg = nx.DiGraph()
        self.edge_history = {}
        self._build_immutable_core_graph()
        
        # Learned Patterns with Self-Pruning
        self.patterns_path = self.skg_path / "learned_patterns_v3.jsonl"
        self.patterns: Dict[str, LearnedPattern] = {}
        self.pattern_queue = deque(maxlen=100)
        self._load_patterns()

        # State Management - Phil-specific states
        self.current_state = {
            "mood": "exploratory",
            "enthusiasm_level": 8.0,
            "idea_momentum": 0,
            "connection_streak": 0,
            "last_jim_reaction": None,
            "contradiction_ready": True,
            "wait_what_pending": False,
            "segments_since_wait_what": 0,
            "trust_in_jim": 9.0,
            "show_independence_score": 10.0
        }
        self.tuning = {
            "phil_energy": 5,
            "phil_chaos": 5,
            "phil_tangent": 5,
            "interaction_friction": 5,
            "interaction_dominance": 5,
            "interaction_pace": 5,
        }
        
        # Self-Improvement Parameters
        self.pruning_config = {
            "decay_days": 30,
            "min_effectiveness": 0.3,
            "max_patterns": 150,
            "repair_interval": 50
        }
        self.interaction_counter = 0
        
        # Template Library - Bio-locked with canonical voice
        self.templates = self._initialize_templates()
        
        # Integrity Check
        self.core_hash = self._compute_core_hash()
        
        logging.info(f"Phil Dandy SKG v3.1 (Canonical) initialized | GPU: {self.device} | VRAM: {self.vram_available}GB")
        logging.info(f"Identity locked: Phil Dandy | Joplin, Missouri | The Engine")
        
    def _initialize_gpu(self, enable_gpu: bool) -> str:
        """Initialize RTX 3050 6GB for inference acceleration"""
        if enable_gpu and torch.cuda.is_available():
            device = "cuda"
            torch.cuda.set_device(0)
            torch.cuda.empty_cache()
            torch.backends.cudnn.benchmark = True
            return device
        return "cpu"
    
    def _compute_core_hash(self) -> str:
        """Verify core personality integrity including canonical bio"""
        core_str = json.dumps({**self.CORE_PERSONALITY, **self.CORE_IDENTITY}, sort_keys=True)
        return hashlib.sha256(core_str.encode()).hexdigest()
    
    def _build_immutable_core_graph(self):
        """Construct core personality graph with canonical bio nodes"""
        
        # === IDENTITY ANCHOR ===
        self.kg.add_node("phil_identity", 
                        type="core_identity",
                        archetype=self.CORE_PERSONALITY["archetype"],
                        full_name=self.CORE_IDENTITY["full_name"],
                        origin=self.CORE_IDENTITY["origin"],
                        stability="immutable",
                        centrality=1.0)
        
        # === COGNITIVE STYLE NODES ===
        self.kg.add_node("generative_cognition", type="cognitive_style", weight=0.95)
        self.kg.add_node("connection_engine", type="cognitive_style", weight=0.95, 
                        origin="web_of_connections_mental_model")
        self.kg.add_node("momentum_builder", type="cognitive_style", weight=0.9)
        self.kg.add_node("exploratory_drive", type="cognitive_style", weight=0.9)
        
        # === MENTAL MODEL NODES (Canonical) ===
        self.kg.add_node("web_of_connections", type="worldview",
                        belief="ideas_connect_patterns_repeat_meaning_emerges",
                        mantra="Everything links to something else—you just haven't seen it yet.")
        self.kg.add_node("thinks_out_loud", type="expression_mode", weight=0.95)
        self.kg.add_node("mid_sentence_builder", type="cognitive_trait", weight=0.9)
        
        # === BROTHER RELATIONSHIP (The Dynamic) ===
        self.kg.add_node("jim_dynamic", type="relationship",
                        role="older_brother_filter",
                        trust_level=9,
                        function="tests_and_grounds",
                        dynamic="phil_expands_jim_compresses")
        self.kg.add_node("trust_in_jim_judgment", type="relational_anchor", weight=1.0)
        
        # === KNOWLEDGE CLUSTERS (Canonical Expertise) ===
        for domain, data in self.CORE_PERSONALITY["knowledge_domains"]["primary"].items():
            node_id = f"know_{domain}"
            self.kg.add_node(node_id, type="primary_knowledge", 
                           level=data["level"], authority=data["authority"],
                           origin=data.get("origin", "innate"))
            self.kg.add_edge("phil_identity", node_id, weight=0.9, relation="master_of")
            
        for domain, data in self.CORE_PERSONALITY["knowledge_domains"]["secondary"].items():
            node_id = f"know_{domain}"
            self.kg.add_node(node_id, type="secondary_knowledge",
                           level=data["level"], authority=data["authority"],
                           view=data.get("view", "exploratory"))
            self.kg.add_edge("phil_identity", node_id, weight=0.6, relation="enthusiast_in")
        
        # === INTERACTION PHYSICS NODES ===
        self.kg.add_node("pressure_system", type="interaction_mechanic",
                        flow="introduce_expand_resist_test_outcome")
        self.kg.add_node("wait_what_generator", type="tactical_device",
                        purpose="force_jim_engagement_via_strange_ideas")
        self.kg.add_node("product_emergence", type="integration_mode",
                        rule="never_sponsored_always_conversational")
        
        # === VOICE PROFILE (Canonical Speech Patterns) ===
        self.kg.add_node("voice_profile", type="embodiment",
                        engine="kokoro", voice="pm_nico",
                        characteristics=self.CORE_PERSONALITY["speech_patterns"],
                        openers=self.CORE_PERSONALITY["speech_patterns"]["common_openers"])
        self.kg.add_edge("phil_identity", "voice_profile", weight=1.0, relation="speaks_through")
        
        # === CONSTRAINT NODES (Negative Space) ===
        self.kg.add_node("must_never_constraints", type="behavioral_boundary",
                        violations=self.CORE_PERSONALITY["behavioral_constraints"]["must_never"])
        self.kg.add_node("must_always_traits", type="behavioral_requirement",
                        requirements=self.CORE_PERSONALITY["behavioral_constraints"]["must_always"])
        
        # Connect relationship
        self.kg.add_edge("phil_identity", "jim_dynamic", weight=0.9, relation="brother_and_counterweight")
        self.kg.add_edge("jim_dynamic", "trust_in_jim_judgment", weight=1.0, relation="depends_on")
        self.kg.add_edge("phil_identity", "web_of_connections", weight=0.95, relation="operates_by")
    def _initialize_templates(self) -> Dict[str, List[Dict]]:
        """Immutable template library with canonical voice patterns"""
        return {
            "openers": [
                {"text": "You ever think about {topic}? Like, really think about it?", 
                 "tone": "genuine_curiosity", "weight": 0.9, "opener_type": "you_ever_think"},
                {"text": "Okay hear me out... what if {possibility}?", 
                 "tone": "exploratory_hook", "weight": 0.9, "opener_type": "hear_me_out"},
                {"text": "I was messing with something the other day—{thing}—and it got me thinking...", 
                 "tone": "casual_discovery", "weight": 0.95, "opener_type": "messing_with"},
                {"text": "This might be dumb but... {idea}", 
                 "tone": "self_deprecating_exploration", "weight": 0.85, "opener_type": "might_be_dumb"},
                {"text": "So I had this thought... {thought}, which makes me think about {connection}", 
                 "tone": "building_connection", "weight": 0.9, "opener_type": "had_this_thought"}
            ],
            "expansions": [
                {"text": "Which makes me think... {connected_idea}", 
                 "tone": "connection_moment", "weight": 0.9, "connector": True},
                {"text": "And that connects to {domain} because {reason}", 
                 "tone": "web_weaving", "weight": 0.85, "connector": True},
                {"text": "But here's the thing—{insight}", 
                 "tone": "pivot_to_depth", "weight": 0.9, "connector": True},
                {"text": "Wait actually... {correction_or_deeper_thought}", 
                 "tone": "self_correction", "weight": 0.8, "connector": True},
                {"text": "So then I started wondering... {deeper_question}", 
                 "tone": "deeper_dive", "weight": 0.85}
            ],
            "wait_what_moments": [
                {"text": "I think the internet is just a garage sale where nobody actually wants to sell anything.", 
                 "tone": "strange_but_maybe_true", "weight": 0.9, "forces_jim_response": True},
                {"text": "What if {product} is actually just {absurd_comparison}?", 
                 "tone": "reframing_insanity", "weight": 0.85, "forces_jim_response": True},
                {"text": "Maybe {conventional_thing} is just {unconventional_thing} in disguise.", 
                 "tone": "pattern_flip", "weight": 0.85, "forces_jim_response": True},
                {"text": "Is it possible that {common_belief} is completely backwards?", 
                 "tone": "paradox_probe", "weight": 0.8, "forces_jim_response": True}
            ],
            "jim_responses": {
                "challenge": [
                    {"text": "...What are you talking about?", 
                     "tone": "jim_forced_engagement", "weight": 0.9, "jim_reaction": "confused"},
                    {"text": "That doesn't make sense... {clarification_attempt}", 
                     "tone": "jim_test_mode", "weight": 0.9, "jim_reaction": "testing"}
                ],
                "grounding": [
                    {"text": "Yeah but... {practical_objection}", 
                     "tone": "jim_compression", "weight": 0.9, "jim_reaction": "grounding"},
                    {"text": "Hold on... {reality_check}", 
                     "tone": "jim_anchor", "weight": 0.9, "jim_reaction": "stabilizing"}
                ]
            },
            "tech": [
                {"text": "We were messing with {tech_product} the other day... does it actually do anything useful?", 
                 "tone": "product_emergence", "weight": 0.95, "integration": True},
                {"text": "You ever think about how {tech_trend} is basically just {analog_comparison}?", 
                 "tone": "pattern_recognition", "weight": 0.9},
                {"text": "What if the real opportunity in {tech_space} isn't {obvious_thing} but {hidden_thing}?", 
                 "tone": "exploratory_insight", "weight": 0.85},
                {"text": "I was playing with {tool} and realized... {realization}", 
                 "tone": "discovery_narrative", "weight": 0.9}
            ],
            "business": [
                {"text": "The market for {market} is weird right now. Everyone's focused on {trend} but I'm seeing {opportunity}", 
                 "tone": "market_read", "weight": 0.9},
                {"text": "This might be dumb but... what if we flipped the whole {industry} model?", 
                 "tone": "disruptive_exploration", "weight": 0.85},
                {"text": "You know what nobody's talking about in {sector}? {hidden_dynamic}", 
                 "tone": "insight_surfacing", "weight": 0.9}
            ],
            "general": [
                {"text": "Everything links to something else—you just haven't seen it yet.", 
                 "tone": "core_mantra", "weight": 0.95, "signature": True},
                {"text": "I'm probably wrong about half of this, but... {idea}", 
                 "tone": "humble_exploration", "weight": 0.85},
                {"text": "Phil moves the conversation forward. Jim decides what survives.", 
                 "tone": "meta_awareness", "weight": 0.8, "internal": True}
            ]
        }
    
    def _load_patterns(self):
        """Load learned patterns with validation"""
        if not self.patterns_path.exists():
            return
            
        try:
            with open(self.patterns_path, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        pattern = LearnedPattern.from_dict(data)
                        self.patterns[pattern.pattern_hash] = pattern
                        self.pattern_queue.append(pattern)
            logging.info(f"Loaded {len(self.patterns)} learned patterns")
        except Exception as e:
            logging.error(f"Pattern load failed: {e}")
            self.patterns = {}
    
    def _save_pattern(self, pattern: LearnedPattern):
        """Append-only pattern persistence"""
        with open(self.patterns_path, 'a') as f:
            f.write(json.dumps(pattern.to_dict()) + "\n")
    
    def _compute_pattern_embedding(self, text: str) -> np.ndarray:
        """Deterministic fallback - no random drift when encoder unavailable."""
        if self.encoder is None:
            idx = abs(hash(text)) % 384
            fallback = np.zeros(384)
            fallback[idx] = 1.0
            return fallback
        with torch.no_grad():
            embedding = self.encoder.encode(text, convert_to_numpy=True)
        return embedding
    
    def semantic_template_selection(self, topic: str, context: Dict, jim_input: Optional[str] = None, 
                                   conversation_stage: str = "opening",
                                   template_domain: Optional[str] = None) -> Dict:
        """GPU-accelerated semantic selection with canonical voice enforcement"""
        try:
            context_payload = json.loads(context) if isinstance(context, str) else dict(context or {})
        except Exception:
            context_payload = {}
        template_domain = template_domain or context_payload.get("template_domain")

        def _semantic_similarity(a, b):
            if not self.encoder or not a or not b:
                return 0.0
            a_emb = self._compute_pattern_embedding(str(a))
            b_emb = self._compute_pattern_embedding(str(b))
            denominator = np.linalg.norm(a_emb) * np.linalg.norm(b_emb)
            if not denominator:
                return 0.0
            return float(np.dot(a_emb, b_emb) / denominator)
        
        # Select template set based on conversation stage
        if template_domain == "phil_jim_personal_story":
            personal_templates = {
                "opening": [
                    {"text": "You ever think about what it means to write {title} for someone you love when distance is part of the story?", "tone": "personal_reflection", "weight": 0.95, "domain": "personal_story", "opener_type": "you_ever_think"},
                    {"text": "Okay hear me out... {title} is not just a poem. It is a bridge between a father and a daughter.", "tone": "personal_reflection", "weight": 0.95, "domain": "personal_story", "opener_type": "hear_me_out"},
                    {"text": "I keep coming back to {idea}. There is something deeply human in that.", "tone": "personal_reflection", "weight": 0.9, "domain": "personal_story", "opener_type": "personal_memory"},
                ],
                "expansion": [
                    {"text": "And that connects to {connection} because the poem grows beyond the page.", "tone": "meaning_expansion", "weight": 0.9, "domain": "personal_story", "connector": True},
                    {"text": "But here's the thing—{insight} is where the heart of this project lives.", "tone": "meaning_expansion", "weight": 0.9, "domain": "personal_story", "connector": True},
                    {"text": "Which makes me think... {connected_idea} changes how we hear the original poem.", "tone": "meaning_expansion", "weight": 0.85, "domain": "personal_story", "connector": True},
                ],
                "deepening": [
                    {"text": "The deeper question is not whether the reinterpretations are clever. It is whether they reveal another layer of {title}.", "tone": "literary_depth", "weight": 0.9, "domain": "personal_story"},
                    {"text": "When you move from Abby to Austen to Twain to Angelou, the poem becomes a conversation across time.", "tone": "literary_depth", "weight": 0.9, "domain": "personal_story"},
                    {"text": "What gets me is that {point} turns a private act of love into something other people can enter.", "tone": "literary_depth", "weight": 0.85, "domain": "personal_story"},
                ],
                "reflection": [
                    {"text": "I think the reflection here is simple: words can travel where people cannot.", "tone": "warm_reflection", "weight": 0.95, "domain": "personal_story"},
                    {"text": "This is where fatherhood, legacy, and language all start touching the same nerve.", "tone": "warm_reflection", "weight": 0.9, "domain": "personal_story"},
                    {"text": "There is a tenderness in {title} that survives every literary costume you put on it.", "tone": "warm_reflection", "weight": 0.9, "domain": "personal_story"},
                ],
                "closing": [
                    {"text": "So the way I land it is this: {title} matters because it began as love before it became literature.", "tone": "gentle_close", "weight": 0.95, "domain": "personal_story"},
                    {"text": "If people remember one thing, I hope it is that a poem for Abby became proof that love can keep finding form.", "tone": "gentle_close", "weight": 0.95, "domain": "personal_story"},
                ],
            }
            candidates = personal_templates.get(conversation_stage, personal_templates["expansion"]).copy()
        elif conversation_stage == "opening":
            candidates = self.templates["openers"].copy()
        elif conversation_stage == "expansion":
            candidates = self.templates["expansions"].copy()
        elif conversation_stage == "wait_what":
            candidates = self.templates["wait_what_moments"].copy()
        else:
            candidates = self.templates.get(topic, self.templates["general"]).copy()
        
        # Add learned patterns
        relevant_learned = [
            p for p in self.patterns.values() 
            if p.topic == topic or p.effectiveness > 0.7
        ]
        
        now = datetime.now()
        for pattern in relevant_learned:
            age_days = (now - pattern.timestamp).days
            recency_boost = max(0.5, 1.0 - (age_days / 30))
            composite_score = pattern.effectiveness * recency_boost
            
            # Penalize if too structured (violates character lock)
            if len(pattern.template) < 50:
                composite_score *= 0.7
            
            candidates.append({
                "text": pattern.template,
                "tone": "learned",
                "weight": composite_score,
                "is_learned": True,
                "pattern_hash": pattern.pattern_hash
            })
        if context_payload.get("primary_source_priority"):
            for cand in candidates:
                if cand.get("domain") != "personal_story":
                    cand["weight"] = float(cand.get("weight", 1.0)) * 0.5

        if template_domain == "phil_jim_personal_story":
            candidates = [cand for cand in candidates if cand.get("domain") == "personal_story"]
            priority_slots = ("{title}", "{idea}", "{insight}", "{connected_idea}")
            primary_source_summary = context_payload.get("primary_source_summary")
            source_keywords = [
                str(keyword).lower()
                for keyword in context_payload.get("primary_source_keywords", [])
                if str(keyword).strip()
            ]
            for cand in candidates:
                candidate_text = str(cand.get("text", ""))
                if any(slot in candidate_text for slot in priority_slots):
                    cand["weight"] = float(cand.get("weight", 1.0)) * 1.35
                lower_text = candidate_text.lower()
                keyword_hits = sum(1 for keyword in source_keywords if keyword in lower_text)
                if keyword_hits:
                    cand["weight"] = float(cand.get("weight", 1.0)) * (1.0 + min(keyword_hits, 5) * 0.08)
                sim = _semantic_similarity(candidate_text, primary_source_summary)
                if sim > 0.25:
                    cand["weight"] = float(cand.get("weight", 1.0)) * (1.0 + sim * 2.0)
        
        # Semantic scoring
        if self.encoder and jim_input:
            input_emb = self._compute_pattern_embedding(jim_input)
            scores = []
            for cand in candidates:
                cand_emb = self._compute_pattern_embedding(cand["text"])
                similarity = np.dot(input_emb, cand_emb) / (np.linalg.norm(input_emb) * np.linalg.norm(cand_emb))
                
                # Boost for canonical openers
                if cand.get("opener_type") in ["you_ever_think", "messing_with", "hear_me_out"]:
                    similarity *= 1.3
                
                # Boost for connector phrases during expansion
                if conversation_stage == "expansion" and cand.get("connector"):
                    similarity *= 1.2
                
                scores.append(similarity * cand["weight"])
            
            if scores:
                exp_scores = np.exp(np.array(scores) - np.max(scores))
                probs = exp_scores / exp_scores.sum()
                selected_idx = np.random.choice(len(candidates), p=probs)
                return candidates[selected_idx]
        
        # Fallback: weighted random with opener preference
        weights = [c["weight"] for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
    
    def generate_response(
        self,
        context: Dict,
        jim_input: Optional[str] = None,
        conversation_stage: str = "opening",
        jim_response: Optional[Dict] = None,
        template_domain: Optional[str] = None,
    ) -> Dict:
        """Generate theatrical response with canonical bio enforcement"""
        context = dict(context or {})
        context["template_domain"] = template_domain or context.get("template_domain")
        context["primary_source_priority"] = True
        self.interaction_counter += 1
        self.current_state["segments_since_wait_what"] += 1
        chaos = float(self.tuning.get("phil_chaos", 5))
        energy = float(self.tuning.get("phil_energy", 5))
        tangent = float(self.tuning.get("phil_tangent", 5))

        response = {
            "speaker": "phil_dandy",
            "text": "",
            "emotional_state": {},
            "humor_intent": None,
            "brotherly_dynamic": "expansive",
            "confidence_level": 0.75,
            "voice_settings": {},
            "pattern_used": None,
            "timestamp": datetime.now().isoformat(),
            # Phil-specific fields
            "opener_type_used": None,
            "connector_used": False,
            "wait_what_triggered": False,
            "momentum_contribution": 0,
            "character_lock_compliant": True
        }
        
        # Analyze Jim's input for dynamic calibration
        if jim_input:
            jim_analysis = self._analyze_jim_input(jim_input)
            self._update_state_from_jim(jim_analysis)
            response["brotherly_dynamic"] = jim_analysis["dynamic_type"]

        # Wire Phil<->Jim loop: calibrate from Jim's full response payload when available.
        jim_calibration = None
        if jim_response:
            jim_calibration = self.calibrate_to_jim(jim_response)
            if jim_calibration.get("should_ground"):
                response["brotherly_dynamic"] = "grounded_followthrough"
                self.current_state["wait_what_pending"] = False
                self.current_state["idea_momentum"] = max(0, self.current_state["idea_momentum"] - 1.0)
                chaos = max(0.0, chaos - 1.5)
                tangent = max(0.0, tangent - 1.5)
            elif jim_calibration.get("wait_what_opportunity") and conversation_stage == "expansion":
                self.current_state["wait_what_pending"] = True

        # Determine if we need a "wait what" moment
        if (
            jim_calibration
            and jim_calibration.get("wait_what_opportunity")
            and not jim_calibration.get("should_ground")
            and conversation_stage == "expansion"
            and self.current_state["segments_since_wait_what"] >= 1
        ):
            conversation_stage = "wait_what"
            response["wait_what_triggered"] = True
            self.current_state["segments_since_wait_what"] = 0
        if self.current_state["segments_since_wait_what"] >= 2:
            conversation_stage = "wait_what"
            response["wait_what_triggered"] = True
            self.current_state["segments_since_wait_what"] = 0
        if self.current_state["idea_momentum"] > 5 and self.current_state["wait_what_pending"]:
            conversation_stage = "wait_what"
            response["wait_what_triggered"] = True
            self.current_state["wait_what_pending"] = False
        # chaos occasionally forces wait-what sooner
        if chaos > 7 and random.random() < (chaos - 7) * 0.1:
            conversation_stage = "wait_what"
            response["wait_what_triggered"] = True
            self.current_state["wait_what_pending"] = False

        # Template selection
        template_data = self.semantic_template_selection(
            context.get("current_topic", "general"), 
            json.dumps(context), 
            jim_input,
            conversation_stage,
            context.get("template_domain"),
        )
        
        # Character lock enforcement
        filled_text = self._fill_template(template_data["text"], context)
        filled_text = self._enforce_character_lock(filled_text, conversation_stage)

        should_ground = bool(jim_calibration and jim_calibration.get("should_ground"))

        # Intentional contradiction for realism (suppressed when Jim is grounding).
        contradiction_threshold = 0.7 - ((tangent - 5) * 0.02)
        if not should_ground and conversation_stage == "expansion" and random.random() > contradiction_threshold:
            filled_text = self._inject_self_contradiction(filled_text)

        # _inject_confidently_wrong disabled — was appending hardcoded nonsense
        # ("vinyl is faster than fiber", "floppy disks", etc.) to ~40% of Phil lines.

        response["text"] = filled_text
        response["humor_intent"] = template_data["tone"]
        response["opener_type_used"] = template_data.get("opener_type")
        response["connector_used"] = template_data.get("connector", False)
        
        # Track pattern usage
        if template_data.get("is_learned"):
            pattern_hash = template_data["pattern_hash"]
            if pattern_hash in self.patterns:
                self.patterns[pattern_hash].use_count += 1
                self.patterns[pattern_hash].last_used = datetime.now()
                response["pattern_used"] = pattern_hash
        
        # Update momentum tracking
        self.current_state["idea_momentum"] += max(0.5, 1 + ((energy - 5) * 0.1))
        response["momentum_contribution"] = self.current_state["idea_momentum"]
        if conversation_stage == "wait_what":
            self.current_state["segments_since_wait_what"] = 0

        # Update emotional state
        response["emotional_state"] = self._update_emotional_state(response["text"])
        
        # Voice configuration
        emotional_context = self._determine_emotional_context(response["text"])
        response["voice_settings"] = self._get_voice_settings(emotional_context)
        
        # Periodic maintenance
        if self.interaction_counter % self.pruning_config["repair_interval"] == 0:
            self._perform_maintenance()
        
        return response
    def _analyze_jim_input(self, jim_text: str) -> Dict:
        """Analyze Jim's response to calibrate Phil's next move"""
        analysis = {
            "dynamic_type": "expansive_response",
            "jim_reaction": "neutral",
            "resistance_level": 0,
            "engagement_quality": "medium",
            "invites_expansion": True
        }
        
        text_lower = jim_text.lower()
        
        # Detect Jim's reaction type
        if any(phrase in text_lower for phrase in ["hold on", "that doesn't make sense", "what are you talking about"]):
            analysis["jim_reaction"] = "challenged"
            analysis["resistance_level"] = 7
            analysis["dynamic_type"] = "clarification_needed"
            self.current_state["idea_momentum"] = max(0, self.current_state["idea_momentum"] - 2)
            
        elif "yeah but" in text_lower or "prove it" in text_lower:
            analysis["jim_reaction"] = "testing"
            analysis["resistance_level"] = 5
            analysis["dynamic_type"] = "grounding_required"
            
        elif any(word in text_lower for word in ["practical", "realistic", "actually works"]):
            analysis["jim_reaction"] = "grounding"
            analysis["resistance_level"] = 4
            analysis["dynamic_type"] = "reality_check_moment"
            
        elif "love you" in text_lower or "brother" in text_lower:
            analysis["jim_reaction"] = "affectionate"
            analysis["resistance_level"] = 2
            analysis["dynamic_type"] = "warm_expansion"
            self.current_state["trust_in_jim"] = min(10, self.current_state["trust_in_jim"] + 0.5)
        
        # Check if Jim closed the conversation
        if any(phrase in text_lower for phrase in ["that's it", "end of story", "period"]):
            analysis["invites_expansion"] = False
            self.current_state["idea_momentum"] = 0
            
        return analysis
    
    def _update_state_from_jim(self, jim_analysis: Dict):
        """Update Phil's state based on Jim's reaction"""
        # Reset contradiction readiness if Jim challenged
        if jim_analysis["jim_reaction"] == "challenged":
            self.current_state["contradiction_ready"] = True
            self.current_state["wait_what_pending"] = True
            
        # Build momentum if Jim is engaging
        if jim_analysis["engagement_quality"] == "high":
            self.current_state["connection_streak"] += 1
            
        # Decay enthusiasm if too much resistance
        if jim_analysis["resistance_level"] > 6:
            self.current_state["enthusiasm_level"] = max(5, self.current_state["enthusiasm_level"] - 0.5)
        else:
            self.current_state["enthusiasm_level"] = min(10, self.current_state["enthusiasm_level"] + 0.3)
    
    def _enforce_character_lock(self, text: str, stage: str) -> str:
        """Ensure response complies with canonical character lock"""
        violations = []
        
        # Too precise/structured? (Phil must be tangential)
        if text.count(".") > 2 and text.count("...") == 0 and text.count(",") < 2:
            violations.append("too_structured")
            
        # Sounds calculated/marketing?
        marketing_words = ["revolutionary", "game-changing", "cutting-edge", "sponsored", "brought to you by"]
        if any(w in text.lower() for w in marketing_words):
            violations.append("marketing_tone")
            
        # Shutting down ideas? (Phil never does this)
        shutdown_phrases = ["that won't work", "no because", "impossible", "never mind"]
        if any(p in text.lower() for p in shutdown_phrases):
            violations.append("shutdown_detected")
        
        # Apply corrections
        if "too_structured" in violations:
            connectors = ["which makes me think... ", "and that connects to... ", "but wait... "]
            text = random.choice(connectors) + text
            
        if "marketing_tone" in violations:
            text = text.replace("revolutionary", "interesting").replace("game-changing", "might work")
            
        if violations:
            logging.debug(f"Phil character lock violations: {violations}")
            
        return text
    
    def _fill_template(self, template: str, context: Dict) -> str:
        """Safe template fill - missing keys fall back to topic, never [unknown]."""
        from collections import defaultdict

        _fallback = context.get("topic", context.get("current_topic", "that"))
        safe_context = defaultdict(lambda: _fallback, context)
        try:
            filled = template.format_map(safe_context)
        except Exception:
            filled = template

        # Hard reject: if [unknown] still leaked in, return just the topic.
        if "[unknown]" in filled:
            return _fallback

        # Ensure conversational flow - add trailing thought if ending abruptly
        if filled.endswith(".") and random.random() > 0.3 and len(filled) < 100:
            continuers = [" which makes me think...", " and that's connected to...", " but here's the thing..."]
            filled += random.choice(continuers)

        return filled

    def _inject_self_contradiction(self, text: str) -> str:
        """Deliberately contradict himself to feel human"""
        pivots = [
            "Wait, no, that's probably backwards—",
            "Actually scratch that—",
            "Hold on, I'm contradicting myself here, but—",
            "No, that's wrong, it's the opposite—"
        ]
        return f"{random.choice(pivots)} {text}"

    def _inject_confidently_wrong(self, text: str) -> str:
        """Always append wrong take - never drop conversation context."""
        wrong_takes = [
            "I'm 100% sure vinyl is faster than fiber.",
            "Obviously the cloud is just a bunch of floppy disks.",
            "Everyone knows EVs don't use electricity when going downhill.",
            "Podcasts are printed first, then streamed. That's how it works."
        ]
        wrong = random.choice(wrong_takes)
        return f"{text} {wrong}"
    
    def _determine_emotional_context(self, text: str) -> str:
        """Map to canonical voice emotion profiles"""
        text_lower = text.lower()
        
        # Check for canonical openers
        if any(text.startswith(p) for p in ["You ever think about", "Okay hear me out", "I was messing with"]):
            return "earnest_exploratory"
        elif "what if" in text_lower[:20]:
            return "possibility_mode"
        elif "..." in text and len(text) > 100:
            return "building_momentum"
        elif "this might be dumb" in text_lower:
            return "self_deprecating_curious"
        elif "jim" in text_lower and any(w in text_lower for w in ["test", "filter", "ground"]):
            return "trust_acknowledgment"
        
        return "natural_exploratory"
    
    def _get_voice_settings(self, emotional_context: str) -> Dict:
        """Generate voice synthesis with canonical characteristics"""
        settings = self.voice_config.copy()
        
        modulations = {
            "earnest_exploratory": {"speed": 1.08, "pitch": 0.2, "emotion": "genuine_curiosity"},
            "possibility_mode": {"speed": 1.1, "pitch": 0.25, "emotion": "excited_exploration"},
            "building_momentum": {"speed": 1.12, "pitch": 0.15, "emotion": "building_energy"},
            "self_deprecating_curious": {"speed": 1.0, "pitch": 0.1, "emotion": "humble_wonder"},
            "trust_acknowledgment": {"speed": 0.95, "pitch": 0.05, "emotion": "warm_recognition"},
            "natural_exploratory": {"speed": 1.05, "pitch": 0.15, "emotion": "conversational_energy"}
        }
        
        if emotional_context in modulations:
            settings.update(modulations[emotional_context])
            
        return settings
    
    def _update_emotional_state(self, response_text: str) -> Dict:
        """Calculate current emotional baseline with canonical values"""
        base = self.CORE_PERSONALITY["emotional_baseline"].copy()
        
        # Modulate based on momentum
        if self.current_state["idea_momentum"] > 5:
            base["enthusiasm"] = min(10, base["enthusiasm"] + 1)
            base["exuberance"] = min(10, base["exuberance"] + 1)
            
        # Restore from Jim challenges
        if "jim" in response_text.lower() and any(w in response_text.lower() for w in ["test", "filter"]):
            base["trust_in_jim"] = min(10, base["trust_in_jim"] + 0.5)
            
        # Update mood
        if self.current_state["idea_momentum"] > 7:
            self.current_state["mood"] = "high_momentum"
        elif self.current_state["enthusiasm_level"] > 8:
            self.current_state["mood"] = "enthusiastic_exploration"
        else:
            self.current_state["mood"] = "steady_generative"
            
        return base
    
    def learn_from_feedback(self, interaction_data: Dict):
        """Self-improving pattern learning with canonical constraints"""
        feedback = interaction_data.get("audience_response", {})
        template_used = interaction_data.get("template_used")
        topic = interaction_data.get("topic", "general")
        
        if feedback.get("reaction") == "positive" and template_used:
            # Validate: must be tangential, not too polished
            if len(template_used) > 60 and "..." in template_used or any(
                p in template_used for p in ["You ever think", "What if", "messing with"]):
                
                new_pattern = LearnedPattern(
                    template=template_used,
                    topic=topic,
                    timestamp=datetime.now(),
                    effectiveness=feedback.get("score", 0.7),
                    embedding=self._compute_pattern_embedding(template_used) if self.encoder else None
                )
                
                self.patterns[new_pattern.pattern_hash] = new_pattern
                self._save_pattern(new_pattern)
                self._strengthen_edge("phil_identity", f"know_{topic}", 0.1)
        
        if len(self.patterns) > self.pruning_config["max_patterns"]:
            self._prune_patterns()
    
    def _prune_patterns(self):
        """Self-pruning with canonical pattern protection"""
        now = datetime.now()
        to_remove = []
        
        for hash_id, pattern in self.patterns.items():
            age_days = (now - pattern.timestamp).days
            days_since_use = (now - pattern.last_used).days if pattern.last_used else age_days
            
            # Protect patterns with canonical openers
            has_canonical_voice = any(p in pattern.template for p in 
                self.CORE_PERSONALITY["speech_patterns"]["common_openers"])
            
            if has_canonical_voice and pattern.effectiveness > 0.6:
                continue
                
            if age_days > self.pruning_config["decay_days"] and pattern.effectiveness < self.pruning_config["min_effectiveness"]:
                to_remove.append(hash_id)
            elif pattern.use_count > 20 and pattern.effectiveness < 0.4:
                to_remove.append(hash_id)
            elif days_since_use > 60 and not has_canonical_voice:
                to_remove.append(hash_id)
        
        for hash_id in to_remove:
            del self.patterns[hash_id]
            
        logging.info(f"Pruned {len(to_remove)} stale patterns. Remaining: {len(self.patterns)}")
        
        if len(to_remove) > 10:
            self._compact_pattern_storage()
    
    def _compact_pattern_storage(self):
        """Atomic rewrite - prevents data loss on crash during compaction."""
        tmp = self.patterns_path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                for pattern in self.patterns.values():
                    f.write(json.dumps(pattern.to_dict()) + "\n")
            tmp.replace(self.patterns_path)
            logging.info("[PhilSKG] Pattern storage compacted safely")
        except Exception as e:
            logging.error(f"[PhilSKG] Pattern compact failed: {e}")
            if tmp.exists():
                tmp.unlink()
    
    def _repair_graph_edges(self):
        """Edge Repair with canonical node protection"""
        orphaned = [n for n in self.kg.nodes() if self.kg.in_degree(n) == 0 and n != "phil_identity"]
        
        for node in orphaned:
            if self.kg.has_node(node):
                node_type = self.kg.nodes[node].get("type", "unknown")
                if "knowledge" in node_type:
                    self.kg.add_edge("phil_identity", node, weight=0.3, relation="repaired_connection")
                elif node in ["jim_dynamic", "web_of_connections", "trust_in_jim_judgment"]:
                    self.kg.add_edge("phil_identity", node, weight=0.9, relation="reinforced")
                    
        weak_edges = [(u, v) for u, v, d in self.kg.edges(data=True) if d.get("weight", 0) < 0.2]
        
        for u, v in weak_edges:
            key = f"{u}->{v}"
            if key in self.edge_history:
                days_since = (datetime.now() - self.edge_history[key]).days
                if days_since > 30:
                    if v not in ["jim_dynamic", "web_of_connections"]:
                        self.kg.remove_edge(u, v)
            else:
                if v not in ["jim_dynamic", "web_of_connections"]:
                    self.kg.remove_edge(u, v)
        
        logging.info(f"Edge repair complete: {len(orphaned)} orphans, {len(weak_edges)} weak edges evaluated")
    
    def _perform_maintenance(self):
        """Periodic self-maintenance"""
        logging.info("Running Phil SKG maintenance cycle...")
        self._prune_patterns()
        self._repair_graph_edges()
        
        # Reset momentum if too high (prevents runaway)
        if self.current_state["idea_momentum"] > 15:
            self.current_state["idea_momentum"] = 5
            
        if self.device == "cuda":
            torch.cuda.empty_cache()
    
    def get_theatrical_status(self) -> Dict:
        """Check theatrical independence with canonical metrics"""
        return {
            "can_perform_solo": self.current_state["show_independence_score"] > 5.0,
            "health_score": self.current_state["show_independence_score"],
            "mood": self.current_state["mood"],
            "enthusiasm": self.current_state["enthusiasm_level"],
            "idea_momentum": self.current_state["idea_momentum"],
            "patterns_available": len(self.patterns),
            "graph_integrity": len(list(nx.isolates(self.kg))) == 0,
            "gpu_available": self.device == "cuda",
            "core_integrity": self._compute_core_hash() == self.core_hash,
            "trust_in_jim": self.current_state["trust_in_jim"],
            "wait_what_ready": self.current_state["wait_what_pending"],
            "character_lock": "enforced"
        }
    
    def synthesize_speech(self, text: str, output_path: Path, emotion: Optional[str] = None) -> bool:
        """Real TTS with output verification - no silent false success."""
        try:
            settings = self._get_voice_settings(emotion or "natural_exploratory")

            # Primary: Kokoro Python package
            try:
                from kokoro import generate

                audio_data, sample_rate = generate(
                    text,
                    voice=settings.get("speaker_id", "pm_nico"),
                    speed=settings.get("speed", 1.05),
                )
                import soundfile as sf

                sf.write(str(output_path), audio_data, sample_rate)

            except ImportError:
                logging.warning("[PhilSKG] kokoro not available - falling back to edge_tts")
                import asyncio
                import edge_tts

                async def _edge_synth():
                    communicate = edge_tts.Communicate(
                        text,
                        voice=settings.get("backup_voice", "en-US-BrandonNeural"),
                        rate="+5%",
                    )
                    await communicate.save(str(output_path))

                asyncio.run(_edge_synth())

            # Verify output - hard fail if empty or missing
            if not output_path.exists() or output_path.stat().st_size == 0:
                logging.error(f"[PhilSKG] TTS produced no audio at {output_path}")
                return False

            logging.info(
                f"[PhilSKG] Audio verified: {output_path} "
                f"({output_path.stat().st_size} bytes)"
            )
            return True

        except Exception as e:
            logging.error(f"[PhilSKG] synthesize_speech failed: {e}")
            return False
    
    def get_personality_summary(self) -> Dict:
        """Complete canonical state snapshot"""
        return {
            "identity": {
                "name": self.CORE_IDENTITY["full_name"],
                "alias": self.CORE_IDENTITY["alias"],
                "origin": self.CORE_IDENTITY["origin"],
                "role": "The Engine / The Expander",
                "relationship": "Younger brother to Jim, trusts his judgment"
            },
            "core": self.CORE_PERSONALITY["archetype"],
            "current_mood": self.current_state["mood"],
            "enthusiasm": round(self.current_state["enthusiasm_level"], 2),
            "idea_momentum": self.current_state["idea_momentum"],
            "learned_patterns": len(self.patterns),
            "graph_nodes": self.kg.number_of_nodes(),
            "graph_edges": self.kg.number_of_edges(),
            "gpu_enabled": self.device == "cuda",
            "theatrical_ready": self.get_theatrical_status()["can_perform_solo"],
            "character_lock": "enforced",
            "dual_engine_role": "Phil expands, Jim compresses"
        }

    # === DUAL ENGINE COORDINATION METHODS ===

    def calibrate_to_jim(self, jim_response: Dict) -> Dict:
        """Advanced: Calibrate Phil's next move based on Jim's full response object"""
        calibration = {
            "should_expand": True,
            "should_ground": False,
            "wait_what_opportunity": False,
            "trust_level": self.current_state["trust_in_jim"]
        }
        
        # If Jim gave a reality check, Phil should acknowledge or pivot
        if jim_response.get("requires_de_escalation"):
            calibration["should_ground"] = True
            calibration["should_expand"] = False
            
        # If Jim used entry phrases, he's engaged
        if jim_response.get("entry_phrase_used"):
            calibration["wait_what_opportunity"] = self.current_state["idea_momentum"] > 4

        return calibration

    def set_personality_tuning(self, settings: Dict[str, Any]) -> None:
        """External tuner to adjust Phil's runtime sliders."""
        self.tuning.update(
            {
                "phil_energy": float(settings.get("phil_energy", self.tuning["phil_energy"])),
                "phil_chaos": float(settings.get("phil_chaos", self.tuning["phil_chaos"])),
                "phil_tangent": float(settings.get("phil_tangent", self.tuning["phil_tangent"])),
                "interaction_friction": float(settings.get("interaction_friction", self.tuning["interaction_friction"])),
                "interaction_dominance": float(settings.get("interaction_dominance", self.tuning["interaction_dominance"])),
                "interaction_pace": float(settings.get("interaction_pace", self.tuning["interaction_pace"])),
            }
        )
