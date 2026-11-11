"""persona_canon.py - Canonical persona loader for the Phil and Jim SKGs.

The owner-approved character canon lives in config/characters/<id>.persona.json.
Both SKGs load it at startup through this module. It fails closed: a missing
file, wrong schema, mismatched character, broken shared-family fingerprint, or
a shared-family block that differs between Phil and Jim raises
PersonaIntegrityError and the SKG does not start.

Standard library only, so it can be tested without torch or GPU packages.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = "dandy.character.v1"
CHARACTERS = ("phil", "jim")
SIBLING = {"phil": "jim", "jim": "phil"}


class PersonaIntegrityError(RuntimeError):
    """Raised when a persona file is missing, malformed, or inconsistent."""


def shared_family_fingerprint(shared: Dict[str, Any]) -> str:
    """SHA256 of the shared-family block (sorted keys, UTF-8)."""
    payload = json.dumps(shared, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def persona_path(character_id: str, base_path: Optional[Path] = None) -> Path:
    """Locate config/characters/<id>.persona.json under base_path or next to this file."""
    name = f"{character_id}.persona.json"
    candidates = []
    if base_path is not None:
        candidates.append(Path(base_path) / "config" / "characters" / name)
    candidates.append(Path(__file__).resolve().parent / "config" / "characters" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PersonaIntegrityError(
        f"Persona file not found for '{character_id}'. Looked in: "
        + ", ".join(str(c) for c in candidates)
    )


def _read(path: Path) -> Dict[str, Any]:
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonaIntegrityError(f"Persona file is not valid UTF-8 JSON: {path}") from exc
    data["_path"] = str(path)
    data["_file_sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def _check_one(character_id: str, data: Dict[str, Any]) -> None:
    if data.get("schema") != SCHEMA:
        raise PersonaIntegrityError(f"{character_id}: schema must be '{SCHEMA}', got {data.get('schema')!r}")
    if data.get("character_id") != character_id:
        raise PersonaIntegrityError(f"{character_id}: file declares character_id {data.get('character_id')!r}")
    for key in ("identity", "household", "shared_family", "shared_family_sha256"):
        if key not in data:
            raise PersonaIntegrityError(f"{character_id}: missing required section '{key}'")
    actual = shared_family_fingerprint(data["shared_family"])
    if actual != data["shared_family_sha256"]:
        raise PersonaIntegrityError(
            f"{character_id}: shared_family was edited without updating shared_family_sha256 "
            f"(stored {data['shared_family_sha256'][:12]}…, actual {actual[:12]}…)"
        )
    order = data["shared_family"].get("birth_order", {})
    expected = "older" if order.get("older") == character_id else "younger" if order.get("younger") == character_id else None
    if expected is None or data["identity"].get("birth_order") != expected:
        raise PersonaIntegrityError(
            f"{character_id}: identity.birth_order {data['identity'].get('birth_order')!r} "
            f"does not match shared_family.birth_order {order!r}"
        )


def load_persona(character_id: str, base_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate one character, cross-checked against the other brother's file."""
    character_id = character_id.lower()
    if character_id not in CHARACTERS:
        raise PersonaIntegrityError(f"Unknown character '{character_id}'")
    data = _read(persona_path(character_id, base_path))
    _check_one(character_id, data)

    sibling_id = SIBLING[character_id]
    sibling = _read(persona_path(sibling_id, base_path))
    _check_one(sibling_id, sibling)
    if sibling["shared_family"] != data["shared_family"]:
        raise PersonaIntegrityError(
            f"shared_family differs between {character_id}.persona.json and {sibling_id}.persona.json"
        )
    data["_sibling_file_sha256"] = sibling["_file_sha256"]
    data["_sibling_canon_names"] = sorted(canon_names(sibling))
    return data


def household_summary(persona: Dict[str, Any]) -> str:
    """One-line household description built only from the persona file."""
    household = persona.get("household", {})
    parts = []
    spouse = household.get("spouse") or {}
    if spouse.get("name"):
        parts.append(f"married to {spouse['name']}")
    kids = []
    for child in household.get("children", []):
        label = child.get("name", "")
        if child.get("nickname"):
            label += f' "{child["nickname"]}"'
        if child.get("birth_year"):
            label += f" ({child['birth_year']})"
        kids.append(label)
    if kids:
        parts.append("father of " + " and ".join(kids))
    pets = [f"{p['name']} ({p.get('species', 'pet')})" for p in household.get("pets", []) if p.get("name")]
    if pets:
        parts.append("pets " + " and ".join(pets))
    return "; ".join(parts)


def persona_brief(persona: Dict[str, Any]) -> str:
    """Compact plain-text canon for writers: identity, family, relationship."""
    ident = persona["identity"]
    shared = persona["shared_family"]
    parents = shared.get("parents", {})
    father = parents.get("father", {})
    mother = parents.get("mother", {})
    dog = shared.get("childhood_dog", {})
    brother = persona.get("with_brother", {})
    mother_name = mother.get("name", "")
    if mother.get("maiden_name"):
        mother_name += f" (née {mother['maiden_name']})"
    lines = [
        f"{ident.get('full_name')} — on air {ident.get('on_air_name')} — {ident.get('birth_order')} brother, "
        f"{ident.get('hometown')}. Role: {ident.get('show_role')}.",
        f"Born: {ident.get('born') or 'not recorded'}.",
        f"Household: {household_summary(persona) or 'not recorded'}.",
        f"Parents (both {father.get('status', 'unknown')}): {father.get('name')} and {mother_name}.",
        f"Grew up with {dog.get('name')}, a {dog.get('breed', dog.get('species', 'dog'))}; "
        f"shared pastimes: {', '.join(shared.get('shared_pastimes', []))}.",
        f"With his brother: {brother.get('stance', '')}",
        "Continuity: " + " ".join(persona.get("continuity_rules", [])),
    ]
    return "\n".join(line for line in lines if line)


def add_family_nodes(kg, persona: Dict[str, Any], identity_node: str) -> None:
    """Attach canon family nodes to an SKG knowledge graph (edges weight 1.0, never pruned)."""
    shared = persona["shared_family"]
    household = persona["household"]
    prefix = persona["character_id"]

    def link(node_id: str, relation: str, **attrs) -> None:
        kg.add_node(node_id, type="canon_family", stability="immutable", source="persona", **attrs)
        kg.add_edge(identity_node, node_id, weight=1.0, relation=relation)

    for role, parent in shared.get("parents", {}).items():
        link(f"canon_{role}", role, name=parent.get("name"), status=parent.get("status"))
    dog = shared.get("childhood_dog") or {}
    if dog.get("name"):
        link("canon_childhood_dog", "grew_up_with", name=dog["name"], breed=dog.get("breed"))
    spouse = household.get("spouse") or {}
    if spouse.get("name"):
        link(f"canon_{prefix}_spouse", "married_to", name=spouse["name"])
    for child in household.get("children", []):
        link(f"canon_{prefix}_child_{child.get('order')}", "father_of",
             name=child.get("name"), nickname=child.get("nickname"), birth_year=child.get("birth_year"))
    for pet in household.get("pets", []):
        link(f"canon_{prefix}_pet_{pet['name'].lower()}", "owns", name=pet["name"], species=pet.get("species"))


# === Learned-pattern cache ===================================================
# Default location: <project>/<id>_dandy_skg_v3/ (already listed in config/vault.json).
# Override with the environment variable DANDY_SKG_CACHE_ROOT; each character then
# uses <DANDY_SKG_CACHE_ROOT>/<id>/.
CACHE_ENV = "DANDY_SKG_CACHE_ROOT"


def skg_cache_dir(character_id: str, base_path: Path) -> Path:
    import os
    root = os.environ.get(CACHE_ENV)
    path = Path(root) / character_id if root else Path(base_path) / f"{character_id}_dandy_skg_v3"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_cache_manifest(cache_dir: Path, persona: Dict[str, Any], skg_version: str) -> Dict[str, Any]:
    """Record which persona the cache was learned under. Returns the previous manifest, if any."""
    from datetime import datetime
    manifest_path = cache_dir / "cache_manifest.json"
    previous: Dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    manifest = {
        "character_id": persona["character_id"],
        "skg_version": skg_version,
        "persona_version": persona.get("version"),
        "persona_sha256": persona["_file_sha256"],
        "persona_history": previous.get("persona_history", []),
        "patterns_file": "learned_patterns_v3.jsonl",
        "learning_log": "learning_events.jsonl",
        "note": "Learned patterns are delivery style only. Biography and family come from the persona file.",
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    if previous.get("persona_sha256") and previous["persona_sha256"] != persona["_file_sha256"]:
        manifest["persona_history"].append({"persona_sha256": previous["persona_sha256"],
                                            "replaced": manifest["updated"]})
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(manifest_path)
    return previous


def canon_names(persona: Dict[str, Any]) -> set:
    """Family names and nicknames defined in canon (for this brother and the shared family)."""
    names = set()
    shared = persona.get("shared_family", {})
    for parent in shared.get("parents", {}).values():
        names.update(part for part in str(parent.get("name", "")).split() if part != "Dandridge")
    if shared.get("childhood_dog", {}).get("name"):
        names.add(shared["childhood_dog"]["name"])
    household = persona.get("household", {})
    spouse = household.get("spouse") or {}
    names.update(part for part in str(spouse.get("name", "")).split() if part != "Dandridge")
    for child in household.get("children", []):
        names.update(part for part in str(child.get("name", "")).split() if part != "Dandridge")
        if child.get("nickname"):
            names.add(child["nickname"])
    for pet in household.get("pets", []):
        if pet.get("name"):
            names.add(pet["name"])
    return {n for n in names if len(n) > 2}


def style_only(template: str, persona: Dict[str, Any], extra_names: Optional[set] = None) -> bool:
    """True if a learned template is free of family references.

    Continuity rule: stories invented in an episode are not canon until the owner
    approves them, so templates that name family members are never learned.
    """
    import re
    names = canon_names(persona) | set(extra_names or ())
    words = set(re.findall(r"[A-Za-z]+", template or ""))
    return not (names & words)


def log_learning_event(cache_dir: Path, event: Dict[str, Any]) -> None:
    from datetime import datetime
    record = {"time": datetime.now().isoformat(timespec="seconds"), **event}
    with open(cache_dir / "learning_events.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
