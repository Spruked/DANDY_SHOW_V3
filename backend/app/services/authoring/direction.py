"""Owner instructions remain separate from extracted evidence and immutable packs."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from ...core.safety import atomic_json, file_lock
from ..storage.episode_store import episode_dir, list_assets


class OwnerDirection(BaseModel):
    episode_direction: str = Field(default='', max_length=20000)
    angle_and_tone: str = Field(default='', max_length=10000)
    must_include: str = Field(default='', max_length=20000)
    must_avoid: str = Field(default='', max_length=20000)
    segment_notes: str = Field(default='', max_length=20000)
    per_source_notes: dict[str, str] = Field(default_factory=dict, max_length=200)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def current_direction(episode_id):
    return read_json(episode_dir(episode_id) / 'context_packages' / 'direction.json') or {
        **OwnerDirection().model_dump(), 'authority': 'owner_direction', 'revision_id': '',
    }


def write_direction(episode_id, value, expected_revision=None):
    """Caller holds context-update lock, shared with context publication."""
    normalized = OwnerDirection(**value).model_dump()
    if any(len(note) > 10000 for note in normalized['per_source_notes'].values()):
        raise ValueError('Per-source notes must be at most 10000 characters each')
    available = {a['asset_id'] for a in list_assets(episode_id) if a.get('role', 'source') == 'source'}
    if set(normalized['per_source_notes']) - available:
        raise ValueError('A per-source note refers to a missing episode source')
    current = current_direction(episode_id)
    if expected_revision is not None and (current.get('revision_id') or '') != expected_revision:
        raise ValueError('Owner direction changed elsewhere. Reload before saving your edits.')
    if OwnerDirection(**current).model_dump() == normalized and current.get('revision_id'):
        return current
    revision = 'direction_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result = {**normalized, 'authority': 'owner_direction', 'revision_id': revision,
              'created_at': datetime.now(timezone.utc).isoformat(),
              'parent_revision_id': current.get('revision_id') or None}
    path = episode_dir(episode_id) / 'context_packages' / 'direction_versions' / f'{revision}.json'
    atomic_json(path, result)
    from ..storage.vault_store import preserve_files
    preserve_files([path], 'owner episode direction saved')
    atomic_json(path.parent.parent / 'direction.json', result)
    return result


def publish_package(episode_id, package):
    """Caller holds context-update lock. Existing version files are never replaced."""
    from .pack import render_pack, show_bible, ad_slots, FORMAT_CONTRACT
    if 'show_bible' not in package:
        package['show_bible'] = show_bible()
    if 'ad_slots' not in package:
        package['ad_slots'] = ad_slots(episode_id)
    package.setdefault('format_contract', FORMAT_CONTRACT)
    package['pack_order'] = ['owner_direction', 'episode_brief', 'show_bible', 'source_facts', 'format_contract', 'ad_slots']
    first_keys = ['schema_version', 'episode_id', 'title', 'owner_direction', 'brief', 'show_bible', 'sources', 'format_contract', 'ad_slots']
    package = {**{key: package[key] for key in first_keys if key in package},
               **{key: value for key, value in package.items() if key not in first_keys}}
    folder = episode_dir(episode_id) / 'context_packages'
    version = 'context_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    package['version_id'] = version
    package['created_at'] = datetime.now(timezone.utc).isoformat()
    package['markdown'] = render_pack(package)
    from .sizing import pack_size, estimated_tokens
    package['sizing'] = pack_size(package['markdown'], package.get('curation', {}))
    package['sizing']['json_estimated_input_tokens'] = estimated_tokens(json.dumps(package, ensure_ascii=False, indent=2))
    path = folder / f'{version}.json'
    atomic_json(path, package)
    from ..storage.vault_store import preserve_files
    preserve_files([path], 'episode context package saved')
    atomic_json(folder / 'latest.json', package)
    return package


def save_direction(episode_id, value, expected_revision=None):
    folder = episode_dir(episode_id) / 'context_packages'
    with file_lock(folder / 'context-update'):
        direction = write_direction(episode_id, value, expected_revision)
        prior = read_json(folder / 'latest.json')
        regenerated = False
        if prior and prior.get('owner_direction', {}).get('revision_id') != direction['revision_id']:
            package = deepcopy(prior)
            package.update(schema_version=max(3, prior.get('schema_version', 3)), parent_version_id=prior['version_id'], owner_direction=direction)
            prior = publish_package(episode_id, package)
            regenerated = True
        return {'owner_direction': direction, 'package': prior, 'pack_regenerated': regenerated}
