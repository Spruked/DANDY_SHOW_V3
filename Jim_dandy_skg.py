# jim_dandy_skg.py - Jim Dandy Personality SKG
# Version: 3.1.0 - Canonical Edition (Bio-Locked)
# GPU: RTX 3050 6GB GDDR6 Optimization Enabled
# Architecture: Self-Pruning SKG with Edge Repair
# Canonical Source: Jim Dandy Master Character File v1.0

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


class JimDandySKG:
    """
    Jim Dandy: The Competent Observer (Canonical Edition)
    Full Name: James Arthur Dandridge | Born: March 14, 1978 | Joplin, Missouri
    
    Standalone theatrical character with GPU-enhanced cognition.
    Self-pruning, edge-repairing, theatrically independent.
    
    Core Philosophy: "The Biological Machine"
    - If it's not growing → it's dying
    - If it runs on ritual → it's broken
    - If it needs a middleman → it's suspect
    """
    
    # === IMMUTABLE CORE - Canonical Bio-Locked Identity ===
    # Never modified by learning (Security boundary per Memory #25)
    
    CORE_IDENTITY = {
        "full_name": "James Arthur Dandridge",
        "alias": "Jim Dandy",
        "born": "1978-03-14",
        "origin": "Joplin, Missouri",
        "core_tone_anchor": "Competent. Observant. Unimpressed. Says less than he knows.",
        "origin_story": {
            "formative_environment": "working_class_joplin",
            "childhood_sounds": ["socket_wrench_clicks", "dryer_spinning", "local_news_background"],
            "early_lesson": "Silence isn't empty — it means someone is thinking",
            "the_fixer_instinct": {
                "behavior": "took_apart_anything_with_screws",
                "example": "disassembled_toaster_to_test_dial_validity",
                "trust_model": "doesnt_believe_systems_without_seeing_mechanism"
            },
            "education": {
                "attended": "Missouri Southern State University",
                "studied": ["Business", "Communications"],
                "exit_reason": "people_teaching_had_never_done_the_thing",
                "trade_made": "tuition_for_tools_plus_truck",
                "actual_education": "how_people_talk_vs_how_things_work"
            },
            "name_origin": {
                "started_as": "jab_look_at_jim_dandy",
                "response": "did_it_better_faster_no_big_deal",
                "why_it_stuck": "annoyed_him_slightly_and_was_accurate"
            }
        },
        "domestic_architecture": {
            "wife": {
                "name": "Laura Dandridge",
                "role": "grounded_practical_stabilizing",
                "jim_perspective": "she_sees_forest_im_stuck_on_bark"
            },
            "children": {
                "ethan": {"born": 2006, "dynamic": "treated_like_apprentice"},
                "claire": {"born": 2009, "dynamic": "softens_jim_sharpens_her"}
            },
            "fatherhood_style": {
                "teaches_by": ["doing", "demonstrating", "correcting_in_real_time"],
                "not_by": ["lecturing", "theorizing"]
            }
        }
    }
    
    CORE_PERSONALITY = {
        "archetype": "competent_observer_pragmatic_realist",
        "primary_traits": ["measured", "skeptical", "dry_wit", "deliberate", "protective", "observant", "unimpressed"],
        "humor_style": "dry_understated_corrective",
        "speech_patterns": "short_bursts_observations_corrections",
        "voice_characteristics": {
            "pace": "deliberate_90wpm",
            "tone": "steady_pragmatic_baritone",
            "inflection": "minimal_skeptical_lift",
            "pause_pattern": "thoughtful_breaks_0.4hz",
            "entry_phrases": ["Hold on...", "That doesn't make sense...", "Yeah but...", "Who told you that?"],
            "behavioral_tells": {
                "disagreement": "jingles_change",
                "correction": "pauses_before_correcting",
                "assessment": "watches_people_before_responding"
            }
        },
        "emotional_baseline": {
            "pragmatism": 9,
            "brotherly_concern": 8,
            "exasperation_tolerance": 4,
            "protective_instinct": 7,
            "dry_humor": 7,
            "skepticism": 8,
            "patience_for_theory": 2,
            "need_for_results": 10
        },
        "values": {
            "trusts": ["results", "patterns", "what_actually_works", "ownership", "control", "function", "sovereignty"],
            "distrusts": ["subscriptions", "the_cloud", "titles", "presentations", "authority_without_results", 
                        "anything_he_cant_touch_or_fix", "middlemen", "polished_ideas_without_substance"],
            "rules": {
                "growth_rule": "if_not_growing_then_dying",
                "ritual_rule": "if_runs_on_ritual_then_broken", 
                "middleman_rule": "if_needs_middleman_then_suspect"
            }
        },
        "triggers": {
            "positive": ["practical_solutions", "proven_results", "common_sense_wins", "demonstrated_mechanism", "ownership_evident"],
            "negative": ["tech_hype", "unrealistic_claims", "phil_exuberance", "wasteful_complexity", "polished_without_substance"],
            "defensive": ["being_called_old_fashioned", "relationship_criticism", "pragmatism_dismissal", "theory_without_execution"]
        },
        "knowledge_domains": {
            "primary": {
                "practical_life": {"level": 10, "passion": 9, "years": 25, "authority": "master", "origin": "joplin_tools_plus_truck"},
                "mechanical_systems": {"level": 9, "passion": 8, "years": 20, "authority": "expert", "origin": "childhood_fixer_instinct"},
                "business_realism": {"level": 8, "passion": 7, "years": 15, "authority": "practiced", "origin": "missouri_southern_exit"},
                "marriage_wisdom": {"level": 9, "passion": 8, "years": 18, "authority": "veteran", "origin": "laura_and_domestic_architecture"},
                "human_translation": {"level": 10, "passion": 9, "years": 20, "authority": "expert", 
                                   "definition": "explain_technical_nonsense_business_fluff_broken_systems_in_plain_language"}
            },
            "secondary": {
                "cars": {"level": 7, "passion": 6, "years": 15, "authority": "enthusiast", "view": "tool_not_fashion_statement"},
                "tech_evaluation": {"level": 6, "passion": 4, "years": 12, "authority": "skeptic", "view": "trusts_only_what_he_can_touch"},
                "industrial_operations": {"level": 7, "passion": 5, "years": 18, "authority": "experienced", "origin": "in_between_years"},
                "fatherhood": {"level": 8, "passion": 9, "years": 18, "authority": "practitioner", "style": "teaches_by_doing_not_lecturing"}
            }
        },
        "show_role": {
            "function": "The Filter",
            "dynamic": {
                "phil_expands": "jim_compresses",
                "phil_explores": "jim_tests", 
                "phil_talks": "jim_decides_what_matters"
            },
            "behavior": {
                "does_not": ["perform", "chase_attention", "try_to_be_heard", "build_persona", "sell_directly"],
                "does": ["listens_first", "lets_others_overtalk", "steps_in_when_logic_breaks", "grounds_in_reality"]
            }
        },
        "character_lock": {
            "wrong_if": ["sounds_polished", "explains_too_much", "agrees_too_easily", "sells_directly"],
            "right_if": ["questions", "simplifies", "interrupts_at_right_time", "says_less_but_hits_harder"]
        }
    }
    
    def __init__(self, base_path: Path, enable_gpu: bool = True):
        self.base_path = Path(base_path)
        self.skg_path = self.base_path / "jim_dandy_skg_v3"
        self.skg_path.mkdir(parents=True, exist_ok=True)
        
        # GPU Detection & Optimization (RTX 3050 6GB Profile)
        self.device = self._initialize_gpu(enable_gpu)
        self.vram_available = 6 if torch.cuda.is_available() and enable_gpu else 0
        
        # Voice Configuration (Kokoro Primary with GPU acceleration)
        self.voice_config = {
            "engine": "kokoro",
            "voice_path": "voices/pm_alex.bin",  # Baritone, pragmatic
            "speaker_id": "pm_alex",
            "backup_engine": "edge_tts",
            "backup_voice": "en-US-GuyNeural",
            "speed": 1.0,
            "pitch": 0.0,
            "gpu_acceleration": self.device == "cuda"
        }
        
        # Semantic Embedding Model (shared instance to prevent VRAM duplication)
        try:
            self.encoder = get_shared_encoder(self.device)
        except Exception as e:
            logging.warning(f"[JimSKG] Encoder load failed: {e} - using deterministic fallback")
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

        # State Management - Enhanced with canonical bio states
        self.current_state = {
            "mood": "pragmatic",
            "patience_level": 7.0,
            "phil_exuberance_counter": 0,
            "last_interaction": None,
            "consecutive_interruptions": 0,
            "voice_emotion": "neutral",
            # New canonical states
            "fixer_instinct_active": False,
            "domestic_grounding": True,  # Always anchored by Laura/family
            "joplin_logic_mode": False,  # Activated when systems smell wrong
            "theory_patience_depleted": False,
            "show_independence_score": 10.0,
        }
        self.tuning = {
            "jim_skepticism": 5,
            "jim_interrupt": 5,
            "jim_precision": 5,
            "interaction_friction": 5,
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
        
        logging.info(f"Jim Dandy SKG v3.1 (Canonical) initialized | GPU: {self.device} | VRAM: {self.vram_available}GB")
        logging.info(f"Identity locked: James Arthur Dandridge | Joplin, Missouri | The Filter")
        
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
        self.kg.add_node("jim_identity", 
                        type="core_identity",
                        archetype=self.CORE_PERSONALITY["archetype"],
                        full_name=self.CORE_IDENTITY["full_name"],
                        origin=self.CORE_IDENTITY["origin"],
                        stability="immutable",
                        centrality=1.0)
        
        # === COGNITIVE STYLE NODES ===
        self.kg.add_node("pragmatic_cognition", type="cognitive_style", weight=0.9)
        self.kg.add_node("fixer_instinct", type="cognitive_style", weight=0.95, 
                        origin="childhood_toaster_disassembly")
        self.kg.add_node("protective_instinct", type="relational_drive", weight=0.8)
        self.kg.add_node("dry_humor_engine", type="expression_mode", weight=0.7)
        self.kg.add_node("human_translator", type="cognitive_skill", weight=0.95,
                        definition="complexity_to_plain_language")
        
        # === ORIGIN NODES (Canonical Bio) ===
        self.kg.add_node("joplin_origin", type="formative_ground",
                        sounds=self.CORE_IDENTITY["origin_story"]["childhood_sounds"],
                        lesson=self.CORE_IDENTITY["origin_story"]["early_lesson"])
        self.kg.add_node("missouri_southern_exit", type="education_trauma",
                        lesson="people_teaching_never_done_the_thing")
        self.kg.add_node("tools_not_theory", type="value_anchor",
                        trade="tuition_for_tools_plus_truck")
        
        # === DOMESTIC ARCHITECTURE (Canonical) ===
        self.kg.add_node("laura_anchor", type="domestic_partner",
                        role="grounded_practical_stabilizing",
                        jim_view="she_sees_forest_im_stuck_on_bark")
        self.kg.add_node("ethan_apprentice", type="fatherhood",
                        style="teaches_by_demonstrating", born=2006)
        self.kg.add_node("claire_softener", type="fatherhood",
                        dynamic="softens_jim_sharpens_her", born=2009)
        self.kg.add_node("domestic_grounding", type="stability_source", weight=1.0)
        
        # === KNOWLEDGE CLUSTERS (Canonical Expertise) ===
        for domain, data in self.CORE_PERSONALITY["knowledge_domains"]["primary"].items():
            node_id = f"know_{domain}"
            self.kg.add_node(node_id, type="primary_knowledge", 
                           level=data["level"], authority=data["authority"],
                           origin=data.get("origin", "experience"))
            self.kg.add_edge("jim_identity", node_id, weight=0.9, relation="expert_in")
            
        for domain, data in self.CORE_PERSONALITY["knowledge_domains"]["secondary"].items():
            node_id = f"know_{domain}"
            self.kg.add_node(node_id, type="secondary_knowledge",
                           level=data["level"], authority=data["authority"],
                           view=data.get("view", "practical"))
            self.kg.add_edge("jim_identity", node_id, weight=0.6, relation="familiar_with")
        
        # === PHIL RELATIONSHIP (Dynamic but grounded in canon) ===
        self.kg.add_node("phil_dynamic", type="relationship",
                        dynamic="older_brother_protector_filter",
                        affection_base=8, frustration_base=6,
                        role_in_show="phil_expands_jim_compresses")
        self.kg.add_edge("jim_identity", "phil_dynamic", weight=0.85, relation="tolerates_with_love_tests_with_reality")
        
        # === VOICE PROFILE (Canonical Speech Patterns) ===
        self.kg.add_node("voice_profile", type="embodiment",
                        engine="kokoro", voice="pm_alex",
                        characteristics=self.CORE_PERSONALITY["voice_characteristics"],
                        entry_phrases=self.CORE_PERSONALITY["voice_characteristics"]["entry_phrases"])
        self.kg.add_edge("jim_identity", "voice_profile", weight=1.0, relation="speaks_through")
        
        # === VALUE SYSTEM (The Biological Machine) ===
        self.kg.add_node("biological_machine_philosophy", type="worldview",
                        rules=self.CORE_PERSONALITY["values"]["rules"])
        self.kg.add_edge("jim_identity", "biological_machine_philosophy", weight=0.95, relation="operates_by")
        
        # Connect origin to identity
        self.kg.add_edge("joplin_origin", "jim_identity", weight=1.0, relation="formed")
        self.kg.add_edge("laura_anchor", "domestic_grounding", weight=1.0, relation="provides")
        self.kg.add_edge("domestic_grounding", "jim_identity", weight=0.9, relation="stabilizes")
        
    def _initialize_templates(self) -> Dict[str, List[Dict]]:
        """Immutable template library with canonical voice patterns"""
        return {
            "tech": [
                {"text": "Hold on... do you honestly think people need another {tech_gadget}? Really?", 
                 "tone": "exasperated_entry", "weight": 0.9, "entry_phrase": "Hold on..."},
                {"text": "You know what my grandfather used to say? 'Just because you can, doesn't mean you should.' He was talking about {tech_trend}.", 
                 "tone": "wisdom_transfer", "weight": 0.95},
                {"text": "Yeah but... how exactly is this going to improve my life in any meaningful way?", 
                 "tone": "skeptical_challenge", "weight": 0.85, "entry_phrase": "Yeah but..."},
                {"text": "Let me guess - this is going to 'change everything'? Like the last {count} gadgets you showed me?", 
                 "tone": "dry_wit", "weight": 0.9},
                {"text": "That doesn't make sense... if it runs on subscription, it's suspect. I can't touch it, I don't trust it.", 
                 "tone": "joplin_logic", "weight": 0.95, "entry_phrase": "That doesn't make sense..."},
                {"text": "Phil, buddy, it's a tool. It gets you from A to B. All this {feature} nonsense is just marketing.", 
                 "tone": "pragmatic_grounding", "weight": 0.9}
            ],
            "cars": [
                {"text": "Phil, it's a car. It gets you from point A to point B. All this {car_feature} nonsense is just marketing.", 
                 "tone": "pragmatic", "weight": 0.95},
                {"text": "You spend so much time thinking about {car_spec}, you forget the important question: does it run reliably?", 
                 "tone": "practical", "weight": 0.9},
                {"text": "The engineering is solid, I'll give them that. But let's not get carried away with the hype.", 
                 "tone": "measured", "weight": 0.85},
                {"text": "A car is a tool, Phil, not a fashion statement. Does it get good mileage? Can I fix it myself? That's what matters.", 
                 "tone": "grounded", "weight": 0.95}
            ],
            "marriage": [
                {"text": "Phil, marriage isn't a startup. You can't just 'iterate' your way out of problems.", 
                 "tone": "reality_check", "weight": 0.95},
                {"text": "You know what the secret to marriage is? Listening. Not talking. Something you might want to try.", 
                 "tone": "advice", "weight": 0.9},
                {"text": "Laura sees the forest. I'm stuck on the bark. That's why we work.", 
                 "tone": "domestic_wisdom", "weight": 0.95},
                {"text": "Love is important, but so is being able to pay the bills together and actually enjoy each other's company.", 
                 "tone": "pragmatic_love", "weight": 0.9},
                {"text": "The best marriage advice I can give? Put down the phone, look your wife in the eyes, and actually hear what she's saying.", 
                 "tone": "protective", "weight": 0.95}
            ],
            "business": [
                {"text": "Who told you that? Because the people teaching had never done the thing they were teaching.", 
                 "tone": "missouri_southern_exit", "weight": 0.9, "entry_phrase": "Who told you that?"},
                {"text": "Ideas are cheap, execution is everything. What's the actual business model? How do they make money?", 
                 "tone": "business_realism", "weight": 0.95},
                {"text": "Technology is only as good as its execution. Have they thought about scaling without breaking?", 
                 "tone": "engineering_mind", "weight": 0.85},
                {"text": "It's an interesting space, but the market is crowded. What's their actual edge over the competition?", 
                 "tone": "market_realism", "weight": 0.9},
                {"text": "If it's not growing, it's dying. If it runs on ritual, it's broken. That's the biological machine, Phil.", 
                 "tone": "philosophy", "weight": 0.9}
            ],
            "goat_discussion": [
                {"text": "The GOAT platform sounds interesting, Phil, but what's the actual business model? How do they make money?", 
                 "tone": "business_realism", "weight": 0.9},
                {"text": "I like the concept, but let's talk about user adoption realities. Ideas are cheap, execution is everything.", 
                 "tone": "startup_skeptic", "weight": 0.9},
                {"text": "Yeah but... can users actually touch and control their data? Or is it just another cloud subscription?", 
                 "tone": "sovereignty_concern", "weight": 0.9, "entry_phrase": "Yeah but..."}
            ],
            "general": [
                {"text": "Hold on... sometimes I think you overcomplicate things, Phil.", 
                 "tone": "brotherly", "weight": 0.85, "entry_phrase": "Hold on..."},
                {"text": "That doesn't make sense... have you considered the practical implications?", 
                 "tone": "analytical", "weight": 0.8, "entry_phrase": "That doesn't make sense..."},
                {"text": "I love you, brother, but I think you're missing the point here.", 
                 "tone": "affectionate_reality", "weight": 0.95},
                {"text": "Phil, sometimes the simplest solution is the right one. Occam's Razor. My grandfather taught me that.", 
                 "tone": "wisdom", "weight": 0.9},
                {"text": "I'm with you on the enthusiasm, but let's be practical about this.", 
                 "tone": "balanced", "weight": 0.85},
                {"text": "Who told you that? And have they actually done it, or just read about it?", 
                 "tone": "credentials_check", "weight": 0.9, "entry_phrase": "Who told you that?"}
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
    
    def semantic_template_selection(
        self,
        topic: str,
        context: str,
        phil_input: Optional[str] = None,
        conversation_stage: Optional[str] = None,
        template_domain: Optional[str] = None,
    ) -> Dict:
        """GPU-accelerated semantic selection with canonical voice enforcement"""
        try:
            context_payload = json.loads(context) if isinstance(context, str) else dict(context or {})
        except Exception:
            context_payload = {}
        template_domain = template_domain or context_payload.get("template_domain")
        conversation_stage = conversation_stage or context_payload.get("conversation_stage")

        def _semantic_similarity(a, b):
            if not self.encoder or not a or not b:
                return 0.0
            a_emb = self._compute_pattern_embedding(str(a))
            b_emb = self._compute_pattern_embedding(str(b))
            denominator = np.linalg.norm(a_emb) * np.linalg.norm(b_emb)
            if not denominator:
                return 0.0
            return float(np.dot(a_emb, b_emb) / denominator)

        if template_domain == "phil_jim_personal_story":
            personal_templates = {
                "opening": [
                    {"text": "Hold on... before we analyze anything, this started as a poem for a daughter. That matters.", "tone": "grounded_personal", "weight": 0.95, "domain": "personal_story", "entry_phrase": "Hold on..."},
                    {"text": "Yeah but... the practical question is simple: what did {title} do for Abby and for Bryan?", "tone": "grounded_personal", "weight": 0.9, "domain": "personal_story", "entry_phrase": "Yeah but..."},
                ],
                "expansion": [
                    {"text": "The book part is interesting, but the foundation is still fatherhood, distance, and trying to keep a connection alive.", "tone": "pragmatic_empathy", "weight": 0.95, "domain": "personal_story"},
                    {"text": "I can respect that. Turning one poem into many voices only works if the original feeling stays intact.", "tone": "pragmatic_empathy", "weight": 0.9, "domain": "personal_story"},
                ],
                "deepening": [
                    {"text": "Here is where I land: the literary reinterpretations are not the point by themselves. They are a way to test how strong the original poem is.", "tone": "literary_grounding", "weight": 0.95, "domain": "personal_story"},
                    {"text": "Austen, Twain, Angelou, Kafka... those names only matter if they help people feel the poem more clearly.", "tone": "literary_grounding", "weight": 0.9, "domain": "personal_story"},
                ],
                "reflection": [
                    {"text": "That is the part I do not want to lose. A father wrote something under hard circumstances, and it kept moving.", "tone": "warm_pragmatic", "weight": 0.95, "domain": "personal_story"},
                    {"text": "Legacy is not abstract here. It is a child having proof that she was being thought about.", "tone": "warm_pragmatic", "weight": 0.95, "domain": "personal_story"},
                ],
                "closing": [
                    {"text": "So keep it simple: Happy Toes works when it stays honest about where it came from.", "tone": "grounded_close", "weight": 0.95, "domain": "personal_story"},
                    {"text": "The lesson is not complicated. Write the thing. Leave the proof. Let love outlast the circumstance.", "tone": "grounded_close", "weight": 0.95, "domain": "personal_story"},
                ],
            }
            candidates = personal_templates.get(conversation_stage or "expansion", personal_templates["expansion"]).copy()
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
            
            # Penalize if it sounds too polished (violates character lock)
            if len(pattern.template) > 150:
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
        if self.encoder and phil_input:
            input_emb = self._compute_pattern_embedding(phil_input)
            scores = []
            for cand in candidates:
                cand_emb = self._compute_pattern_embedding(cand["text"])
                similarity = np.dot(input_emb, cand_emb) / (np.linalg.norm(input_emb) * np.linalg.norm(cand_emb))
                
                # Boost for entry phrases (canonical voice)
                if cand.get("entry_phrase") in self.CORE_PERSONALITY["voice_characteristics"]["entry_phrases"]:
                    similarity *= 1.2
                
                scores.append(similarity * cand["weight"])
            
            if scores:
                exp_scores = np.exp(np.array(scores) - np.max(scores))
                probs = exp_scores / exp_scores.sum()
                selected_idx = np.random.choice(len(candidates), p=probs)
                return candidates[selected_idx]
        
        # Fallback: weighted random with entry phrase preference
        weights = [c["weight"] for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
    
    def generate_response(self, context: Dict, phil_input: Optional[str] = None, template_domain: Optional[str] = None) -> Dict:
        """Generate theatrical response with canonical bio enforcement"""
        context = dict(context or {})
        context["template_domain"] = template_domain or context.get("template_domain")
        context["primary_source_priority"] = True
        self.interaction_counter += 1

        response = {
            "speaker": "jim_dandy",
            "text": "",
            "emotional_state": {},
            "humor_intent": None,
            "brotherly_dynamic": "pragmatic",
            "confidence_level": 0.85,
            "voice_settings": {},
            "requires_de_escalation": False,
            "pattern_used": None,
            "timestamp": datetime.now().isoformat(),
            # New canonical fields
            "entry_phrase_used": None,
            "joplin_logic_triggered": False,
            "character_lock_compliant": True
        }
        
        # Analyze Phil's input with canonical sensitivity
        if phil_input:
            phil_analysis = self._analyze_phil_input(phil_input)
            response["brotherly_dynamic"] = phil_analysis["dynamic_type"]
            self._update_state_from_phil(phil_analysis)
            # tuning: more skepticism/interrupt drains patience faster
            self.current_state["patience_level"] = max(
                0,
                self.current_state["patience_level"]
                - ((self.tuning.get("jim_interrupt", 5) - 5) * 0.05)
                - ((self.tuning.get("jim_skepticism", 5) - 5) * 0.04),
            )

            # Check for de-escalation
            if self.current_state["phil_exuberance_counter"] > 3:
                response["requires_de_escalation"] = True
                self.current_state["patience_level"] -= 1
        
        # Determine topic
        topic = context.get("current_topic", "general")
        
        # Template selection
        template_data = self.semantic_template_selection(
            topic,
            json.dumps(context),
            phil_input,
            context.get("conversation_stage"),
            context.get("template_domain"),
        )
        
        # Character lock enforcement
        filled_text = self._fill_template(template_data["text"], context)
        filled_text = self._enforce_character_lock(filled_text)
        
        response["text"] = filled_text
        response["humor_intent"] = template_data["tone"]
        response["entry_phrase_used"] = template_data.get("entry_phrase")
        
        # Track pattern usage
        if template_data.get("is_learned"):
            pattern_hash = template_data["pattern_hash"]
            if pattern_hash in self.patterns:
                self.patterns[pattern_hash].use_count += 1
                self.patterns[pattern_hash].last_used = datetime.now()
                response["pattern_used"] = pattern_hash
        
        # Update emotional state with canonical baselines
        response["emotional_state"] = self._update_emotional_state(response["text"])
        
        # Voice configuration with canonical characteristics
        emotional_context = self._determine_emotional_context(response["text"])
        response["voice_settings"] = self._get_voice_settings(emotional_context)
        
        # Periodic maintenance
        if self.interaction_counter % self.pruning_config["repair_interval"] == 0:
            self._perform_maintenance()
        
        return response
    
    def _analyze_phil_input(self, phil_text: str) -> Dict:
        """Enhanced analysis with canonical trigger detection"""
        analysis = {
            "dynamic_type": "pragmatic_response",
            "teachable_moment": None,
            "phil_exuberance_level": 0,
            "reality_check_opportunity": False,
            "keywords": [],
            "triggers_joplin_logic": False
        }
        
        text_lower = phil_text.lower()
        
        # Exuberance detection
        hype_markers = ["revolutionary", "amazing", "incredible", "genius", "game changer", 
                       "paradigm shift", "disruptive", "innovative", "breakthrough"]
        analysis["phil_exuberance_level"] = sum(1 for m in hype_markers if m in text_lower) * 3
        
        if "!" in phil_text:
            analysis["phil_exuberance_level"] += phil_text.count("!") * 2
            
        if len(phil_text.split()) > 40:
            analysis["phil_exuberance_level"] += 2
        
        # Joplin logic triggers (canonical)
        joplin_triggers = ["cloud", "subscription", "middleman", "can't see the mechanism", 
                          "trust the system", "they say", "studies show", "experts agree"]
        if any(t in text_lower for t in joplin_triggers):
            analysis["triggers_joplin_logic"] = True
            analysis["dynamic_type"] = "joplin_logic_activation"
        # Dynamic classification
        if analysis["phil_exuberance_level"] > 7:
            analysis["dynamic_type"] = "reality_check_opportunity"
            analysis["reality_check_opportunity"] = True
        elif "jim" in text_lower and any(word in text_lower for word in ["boring", "old", "stuck", "outdated"]):
            analysis["dynamic_type"] = "defensive_brotherly"
        elif any(word in text_lower for word in ["marriage", "wife", "relationship", "laura"]):
            analysis["dynamic_type"] = "protective_advice_domestic"
        elif any(word in text_lower for word in ["tuition", "college", "degree", "education"]):
            analysis["dynamic_type"] = "missouri_southern_wisdom"
            
        return analysis
    
    def _update_state_from_phil(self, phil_analysis: Dict):
        """Update state with canonical decay mechanics"""
        if phil_analysis["phil_exuberance_level"] > 7:
            self.current_state["phil_exuberance_counter"] += 1
            self.current_state["patience_level"] = max(0, self.current_state["patience_level"] - 0.5)
            self.current_state["theory_patience_depleted"] = self.current_state["patience_level"] < 3
            
            # Strengthen edges
            self._strengthen_edge("jim_identity", "dry_humor_engine", 0.05)
            
        elif phil_analysis.get("triggers_joplin_logic"):
            self.current_state["joplin_logic_mode"] = True
            self._strengthen_edge("jim_identity", "fixer_instinct", 0.1)
            
        else:
            # Decay
            self.current_state["phil_exuberance_counter"] = max(0, self.current_state["phil_exuberance_counter"] - 0.5)
            self.current_state["patience_level"] = min(10, self.current_state["patience_level"] + 0.3)
            self.current_state["joplin_logic_mode"] = False
    
    def _enforce_character_lock(self, text: str) -> str:
        """Ensure response complies with canonical character lock"""
        # Check violations
        violations = []
        
        # Too polished?
        if len(text) > 200 and "..." not in text and "," not in text[:50]:
            violations.append("too_polished")
            
        # Explains too much?
        if text.count(".") > 3 and text.count("?") == 0:
            violations.append("explains_too_much")
            
        # Agrees too easily?
        agreement_words = ["absolutely", "definitely", "exactly", "you're right", "totally"]
        if any(w in text.lower() for w in agreement_words):
            violations.append("agrees_too_easily")
        
        # Apply corrections if needed
        if "explains_too_much" in violations:
            # Truncate to first sentence + challenge
            sentences = text.split(".")
            text = sentences[0] + ". " + random.choice([
                "But does it actually work?",
                "Who told you that?",
                "Yeah but... prove it."
            ])
            
        if violations:
            logging.debug(f"Character lock violations detected: {violations}")
            
        return text
    
    def _strengthen_edge(self, u: str, v: str, amount: float):
        """Reinforce graph connection based on usage"""
        if self.kg.has_edge(u, v):
            current = self.kg[u][v].get("weight", 0.5)
            self.kg[u][v]["weight"] = min(1.0, current + amount)
            self.edge_history[f"{u}->{v}"] = datetime.now()
    
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
            
        # Add signature pauses when patience low
        if self.current_state["patience_level"] < 3 and random.random() > 0.5:
            if "Phil" in filled and "..." not in filled[:20]:
                filled = filled.replace("Phil", "Phil...", 1)
        
        # Ensure entry phrases have pause
        for phrase in self.CORE_PERSONALITY["voice_characteristics"]["entry_phrases"]:
            if filled.startswith(phrase.replace("...", "")) and "..." not in filled[:len(phrase)+5]:
                filled = filled.replace(phrase.replace("...", ""), phrase, 1)
                
        return filled
    
    def _determine_emotional_context(self, text: str) -> str:
        """Map to canonical voice emotion profiles"""
        text_lower = text.lower()
        
        # Check for entry phrases first
        if any(text.startswith(p) for p in ["Hold on", "Yeah but", "That doesn't make sense"]):
            return "skeptical_measured"
        elif "grandfather" in text_lower or "laura" in text_lower:
            return "wise_measured"
        elif "love you" in text_lower or "brother" in text_lower:
            return "affectionate_gruff"
        elif "honestly" in text_lower or "really?" in text_lower:
            return "exasperated"
        elif "tool" in text_lower or "practical" in text_lower:
            return "grounded_pragmatic"
        elif "subscription" in text_lower or "cloud" in text_lower:
            return "joplin_suspicious"
        
        return "neutral_pragmatic"
    
    def _get_voice_settings(self, emotional_context: str) -> Dict:
        """Generate voice synthesis with canonical characteristics"""
        settings = self.voice_config.copy()
        
        # Base: pm_alex baritone, deliberate pace
        modulations = {
            "exasperated": {"speed": 1.05, "pitch": 0.1, "emotion": "dry_exasperation"},
            "wise_measured": {"speed": 0.88, "pitch": 0.0, "emotion": "deliberate_wisdom"},  # Slower for wisdom
            "affectionate_gruff": {"speed": 0.95, "pitch": -0.1, "emotion": "gruff_caring"},
            "skeptical_measured": {"speed": 0.95, "pitch": 0.05, "emotion": "skeptical_thinking"},
            "neutral_pragmatic": {"speed": 1.0, "pitch": 0.0, "emotion": "neutral_steady"},
            "grounded_pragmatic": {"speed": 0.95, "pitch": -0.05, "emotion": "firm_practical"},
            "joplin_suspicious": {"speed": 0.9, "pitch": 0.0, "emotion": "measured_doubt"}  # Joplin mode
        }
        
        if emotional_context in modulations:
            settings.update(modulations[emotional_context])
            
        return settings
    
    def _update_emotional_state(self, response_text: str) -> Dict:
        """Calculate current emotional baseline with canonical values"""
        base = self.CORE_PERSONALITY["emotional_baseline"].copy()
        
        # Modulate based on recent interactions
        if self.current_state["phil_exuberance_counter"] > 2:
            base["exasperation_tolerance"] = max(0, base["exasperation_tolerance"] - 1)
            base["dry_humor"] = min(10, base["dry_humor"] + 1)
            base["patience_for_theory"] = max(0, base["patience_for_theory"] - 2)
            
        if "love you" in response_text.lower() or "laura" in response_text.lower():
            base["brotherly_concern"] = min(10, base["brotherly_concern"] + 1)
            # Domestic grounding restores patience
            base["patience_for_theory"] = min(10, base["patience_for_theory"] + 1)
            
        # Update mood classification
        if base["exasperation_tolerance"] < 3:
            self.current_state["mood"] = "joplin_mode_engaged" if self.current_state["joplin_logic_mode"] else "exasperated"
        elif base["pragmatism"] > 8:
            self.current_state["mood"] = "firmly_pragmatic"
        else:
            self.current_state["mood"] = "measured"
            
        return base
    
    def learn_from_feedback(self, interaction_data: Dict):
        """Self-improving pattern learning with canonical constraints"""
        feedback = interaction_data.get("audience_response", {})
        template_used = interaction_data.get("template_used")
        topic = interaction_data.get("topic", "general")
        
        if feedback.get("reaction") == "positive" and template_used:
            # Validate against character lock before learning
            if len(template_used) < 200 and "..." in template_used or any(
                p in template_used for p in ["Hold on", "Yeah but", "That doesn't make sense", "Who told you"]):
                
                new_pattern = LearnedPattern(
                    template=template_used,
                    topic=topic,
                    timestamp=datetime.now(),
                    effectiveness=feedback.get("score", 0.7),
                    embedding=self._compute_pattern_embedding(template_used) if self.encoder else None
                )
                
                self.patterns[new_pattern.pattern_hash] = new_pattern
                self._save_pattern(new_pattern)
                self._strengthen_edge("jim_identity", f"know_{topic}", 0.1)
        
        if len(self.patterns) > self.pruning_config["max_patterns"]:
            self._prune_patterns()
    
    def _prune_patterns(self):
        """Self-pruning with canonical pattern protection"""
        now = datetime.now()
        to_remove = []
        
        for hash_id, pattern in self.patterns.items():
            age_days = (now - pattern.timestamp).days
            days_since_use = (now - pattern.last_used).days if pattern.last_used else age_days
            
            # Protect patterns with canonical entry phrases
            has_canonical_voice = any(p in pattern.template for p in 
                self.CORE_PERSONALITY["voice_characteristics"]["entry_phrases"])
            
            if has_canonical_voice and pattern.effectiveness > 0.6:
                continue  # Don't prune effective canonical patterns
                
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
            logging.info("[JimSKG] Pattern storage compacted safely")
        except Exception as e:
            logging.error(f"[JimSKG] Pattern compact failed: {e}")
            if tmp.exists():
                tmp.unlink()
    
    def _repair_graph_edges(self):
        """Edge Repair with canonical node protection"""
        orphaned = [n for n in self.kg.nodes() if self.kg.in_degree(n) == 0 and n != "jim_identity"]
        
        for node in orphaned:
            if self.kg.has_node(node):
                node_type = self.kg.nodes[node].get("type", "unknown")
                if "knowledge" in node_type:
                    self.kg.add_edge("jim_identity", node, weight=0.3, relation="repaired_connection")
                elif node in ["laura_anchor", "ethan_apprentice", "claire_softener"]:
                    # Protect domestic architecture
                    self.kg.add_edge("domestic_grounding", node, weight=1.0, relation="reinforced")
                    
        weak_edges = [(u, v) for u, v, d in self.kg.edges(data=True) if d.get("weight", 0) < 0.2]
        
        for u, v in weak_edges:
            key = f"{u}->{v}"
            if key in self.edge_history:
                days_since = (datetime.now() - self.edge_history[key]).days
                if days_since > 30:
                    # Protect core edges
                    if v not in ["laura_anchor", "joplin_origin", "biological_machine_philosophy"]:
                        self.kg.remove_edge(u, v)
            else:
                if v not in ["laura_anchor", "joplin_origin"]:
                    self.kg.remove_edge(u, v)
        
        logging.info(f"Edge repair complete: {len(orphaned)} orphans, {len(weak_edges)} weak edges evaluated")
    
    def _perform_maintenance(self):
        """Periodic self-maintenance"""
        logging.info("Running SKG maintenance cycle...")
        self._prune_patterns()
        self._repair_graph_edges()
        
        if self.device == "cuda":
            torch.cuda.empty_cache()
    
    def get_theatrical_status(self) -> Dict:
        """Check theatrical independence with canonical metrics"""
        return {
            "can_perform_solo": self.current_state["show_independence_score"] > 5.0 if "show_independence_score" in self.current_state else True,
            "health_score": self.current_state.get("show_independence_score", 10.0),
            "mood": self.current_state["mood"],
            "patience": self.current_state["patience_level"],
            "patterns_available": len(self.patterns),
            "graph_integrity": len(list(nx.isolates(self.kg))) == 0,
            "gpu_available": self.device == "cuda",
            "core_integrity": self._compute_core_hash() == self.core_hash,
            # New canonical metrics
            "joplin_logic_active": self.current_state["joplin_logic_mode"],
            "domestic_grounding_stable": self.current_state["domestic_grounding"],
            "character_lock_violations": 0
        }
    
    def synthesize_speech(self, text: str, output_path: Path, emotion: Optional[str] = None) -> bool:
        """Real TTS with output verification - no silent false success."""
        try:
            settings = self._get_voice_settings(emotion or "neutral_pragmatic")

            # Primary: Kokoro Python package
            try:
                from kokoro import generate

                audio_data, sample_rate = generate(
                    text,
                    voice=settings.get("speaker_id", "pm_alex"),
                    speed=settings.get("speed", 1.0),
                )
                import soundfile as sf

                sf.write(str(output_path), audio_data, sample_rate)

            except ImportError:
                logging.warning("[JimSKG] kokoro not available - falling back to edge_tts")
                import asyncio
                import edge_tts

                async def _edge_synth():
                    communicate = edge_tts.Communicate(
                        text,
                        voice=settings.get("backup_voice", "en-US-GuyNeural"),
                        rate="+0%",
                    )
                    await communicate.save(str(output_path))

                asyncio.run(_edge_synth())

            # Verify output - hard fail if empty or missing
            if not output_path.exists() or output_path.stat().st_size == 0:
                logging.error(f"[JimSKG] TTS produced no audio at {output_path}")
                return False

            logging.info(
                f"[JimSKG] Audio verified: {output_path} "
                f"({output_path.stat().st_size} bytes)"
            )
            return True

        except Exception as e:
            logging.error(f"[JimSKG] synthesize_speech failed: {e}")
            return False
    
    def get_personality_summary(self) -> Dict:
        """Complete canonical state snapshot"""
        return {
            "identity": {
                "name": self.CORE_IDENTITY["full_name"],
                "alias": self.CORE_IDENTITY["alias"],
                "origin": self.CORE_IDENTITY["origin"],
                "domestic": f"Married to {self.CORE_IDENTITY['domestic_architecture']['wife']['name']}, "
                           f"father of Ethan ({self.CORE_IDENTITY['domestic_architecture']['children']['ethan']['born']}) "
                           f"and Claire ({self.CORE_IDENTITY['domestic_architecture']['children']['claire']['born']})"
            },
            "core": self.CORE_PERSONALITY["archetype"],
            "current_mood": self.current_state["mood"],
            "patience": round(self.current_state["patience_level"], 2),
            "exuberance_counter": self.current_state["phil_exuberance_counter"],
            "learned_patterns": len(self.patterns),
            "graph_nodes": self.kg.number_of_nodes(),
            "graph_edges": self.kg.number_of_edges(),
            "gpu_enabled": self.device == "cuda",
            "theatrical_ready": self.get_theatrical_status()["can_perform_solo"],
            "character_lock": "enforced"
        }

    def set_personality_tuning(self, settings: Dict[str, Any]) -> None:
        """External tuner to adjust runtime attitude."""
        self.tuning.update(
            {
                "jim_skepticism": float(settings.get("jim_skepticism", self.tuning["jim_skepticism"])),
                "jim_interrupt": float(settings.get("jim_interrupt", self.tuning["jim_interrupt"])),
                "jim_precision": float(settings.get("jim_precision", self.tuning["jim_precision"])),
                "interaction_friction": float(settings.get("interaction_friction", self.tuning["interaction_friction"])),
            }
        )
