# Communication Layer Patch

## What to Change in Your Existing `communication_layer.py`

Your current `_build_context()` method maps almost every template variable to `topic` — this causes repetitive dialogue. Here's the minimal change to use the rich context builder instead.

## Step 1: Add import at top of file

```python
# Add this import at the top of communication_layer.py
from context_builder import build_rich_context
```

## Step 2: Replace `_build_context` method

Replace your entire `_build_context` method with this version:

```python
def _build_context(self, topic: str, script: Dict) -> Dict:
    """Build a context dict that satisfies all SKG template variables.
    
    Uses the rich context builder for varied, intelligent template filling.
    Falls back to the original simple mapping if rich context fails.
    """
    # Check if rich context was pre-built by the worker
    prebuilt = script.get("_rich_context")
    if prebuilt:
        # Merge prebuilt context with any script-specific overrides
        return {**prebuilt, "current_topic": topic, "script_points": script.get("key_points", [])}
    
    # Fallback: build fresh rich context
    try:
        return build_rich_context(
            topic=topic,
            key_points=script.get("key_points", []),
            title=script.get("title", topic),
            audience=script.get("audience", "general"),
            intensity=script.get("intensity", "medium"),
            source_context=script.get("source_context", ""),
        )
    except Exception:
        # Last resort: original minimal mapping
        key_points = [kp for kp in script.get("key_points", []) if kp]
        def kp_fn(idx: int) -> str:
            return key_points[idx] if idx < len(key_points) else topic
        return {
            "current_topic": topic,
            "script_points": key_points,
            "audience": script.get("audience", "general"),
            "intensity": script.get("intensity", "medium"),
            "topic": topic,
            "title": script.get("title") or topic,
            "possibility": kp_fn(0),
            "thing": topic,
            "idea": kp_fn(0),
            "thought": topic,
            "connection": kp_fn(1) if len(key_points) > 1 else topic,
            "connected_idea": kp_fn(1) if len(key_points) > 1 else kp_fn(0),
            "domain": topic,
            "reason": kp_fn(2) if len(key_points) > 2 else kp_fn(0),
            "insight": kp_fn(0),
            "correction_or_deeper_thought": kp_fn(1) if len(key_points) > 1 else topic,
            "deeper_question": f"what {topic} really means long-term",
            "product": topic,
            "absurd_comparison": "an expensive fortune cookie",
            "conventional_thing": topic,
            "unconventional_thing": kp_fn(0),
            "common_belief": f"everyone understands {topic}",
            "clarification_attempt": f"you mean the part about {kp_fn(0)}",
            "practical_objection": f"does {topic} actually hold up in practice",
            "reality_check": f"what does {topic} cost people in real terms",
            "tech_product": topic,
            "tech_trend": topic,
            "analog_comparison": "a library card catalogue",
            "tech_space": topic,
            "obvious_thing": kp_fn(0),
            "hidden_thing": kp_fn(1) if len(key_points) > 1 else f"the human side of {topic}",
            "tool": topic,
            "realization": kp_fn(0),
            "market": topic,
            "trend": kp_fn(0),
            "opportunity": kp_fn(1) if len(key_points) > 1 else kp_fn(0),
            "industry": topic,
            "sector": topic,
            "hidden_dynamic": kp_fn(2) if len(key_points) > 2 else kp_fn(0),
            "tech_gadget": topic,
            "count": "a few",
            "feature": kp_fn(0),
            "car_feature": kp_fn(0),
            "car_spec": kp_fn(0),
        }
```

## Step 3 (Optional): Increase exchange count

Your current `orchestrate_banter` generates a maximum of 6 exchanges per topic.
To get more content from the SKG before expansion, you can increase the loop count:

In `_generate_topic_banter`, change:
```python
for _ in range(2):  # ← Change this to range(5) or higher
```

Or better, make it configurable by adding to `orchestrate_banter`:

```python
def orchestrate_banter(
    self,
    episode_script: Dict,
    audience_feedback: Optional[List] = None,
    line_callback=None,
    max_rounds: int = 5,  # ← Add this parameter
) -> List[Dict]:
```

And use `max_rounds` in `_generate_topic_banter`:
```python
for _ in range(max_rounds):
```

> **Note:** Even with more SKG exchanges, the script_expander will still extend
the script to hit target duration. The SKG output is treated as the "seed"
that sets the tone; the expander builds the full length around it.
