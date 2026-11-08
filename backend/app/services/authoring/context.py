"""Build source-grounded handoff packages without generating episode dialogue."""
from ...core.safety import contained_path, file_lock
from ..storage.episode_store import episode_dir, list_assets, load_episode_detail
from .extractors import extract_document
from .sizing import estimated_tokens


def read_sources(episode_id, source_ids=None):
    assets = [a for a in list_assets(episode_id) if a.get('role', 'source') == 'source']
    if source_ids is not None:
        if set(source_ids) - {a['asset_id'] for a in assets}:
            raise ValueError('A selected source is missing or is not an episode source')
        assets = [a for a in assets if a['asset_id'] in source_ids]
    sources, warnings = [], []
    for asset in assets:
        name = asset['original_name']
        try:
            path = contained_path(episode_dir(episode_id) / 'assets', asset['stored_name'])
            records = extract_document(path)
            for record in records:
                record.update(source_id=asset['asset_id'], source_name=name)
            empty = [r['location'] for r in records if not r['text'].strip()]
            if empty:
                warnings.append(f"{name}: no extractable text at {', '.join(empty)}; check for scanned pages.")
            if path.suffix.lower() == '.docx':
                warnings.append(f'{name}: imported body paragraphs and tables; images, headers, footnotes and comments are not included.')
            elif path.suffix.lower() == '.pdf':
                warnings.append(f'{name}: imported the PDF text layer; check reading order and any images or diagrams manually.')
            elif any(r.get('extraction_method') == 'tesseract_ocr' for r in records):
                warnings.append(f'{name}: machine-transcribed by local Tesseract OCR. Review recognition errors. OCR confidence is not factual confidence; pictures are not described.')
            for warning in sorted({r['parse_warning'] for r in records if r.get('parse_warning')}):
                warnings.append(f'{name}: {warning}')
            text = ''.join(r['text'] for r in records)
            sources.append({'source_id': asset['asset_id'], 'name': name, 'description': asset.get('description', ''),
                            'sha256': records[0]['source_sha256'], 'sections': records,
                            'character_count': len(text), 'estimated_tokens': estimated_tokens(text)})
        except Exception as exc:
            warnings.append(f'{name}: {exc}')
    return sources, warnings


def inspect_sources(episode_id, source_ids=None):
    sources, warnings = read_sources(episode_id, source_ids)
    return {'sources': [{key: value for key, value in source.items() if key != 'sections'} | {
        'record_count': len(source['sections']), 'preview_limited': len(source['sections']) > 20,
        'records': [{key: value for key, value in record.items() if key != 'text'} |
                    {'text_preview': record['text'][:200]} for record in source['sections'][:20]]}
        for source in sources], 'warnings': warnings,
        'estimated_source_tokens': sum(source['estimated_tokens'] for source in sources),
        'estimator': 'UTF-8 bytes / 3; full pack also includes owner direction, show bible and instructions',
        'exact_tokenizer': False}


def build_context(episode_id: str, brief: str = '', source_ids: list[str] | None = None,
                  owner_direction: dict | None = None, expected_direction_revision: str | None = None,
                  curation: dict | None = None) -> dict:
    detail = load_episode_detail(episode_id)
    if not detail.get('config'):
        raise ValueError('Episode not found')
    sources, warnings = read_sources(episode_id, source_ids)
    if not sources:
        raise ValueError('No readable sources. ' + ' '.join(warnings))
    if sum(len(s['text']) for src in sources for s in src['sections']) > 2_000_000:
        raise ValueError('Context exceeds two million characters. Select fewer sources.')
    curation = dict(curation or {})
    priority_ids = curation.get('priority_source_ids', [])
    if set(priority_ids) - {source['source_id'] for source in sources}:
        raise ValueError('Priority sources must be selected readable sources')
    for source in sources:
        source['priority'] = source['source_id'] in priority_ids
    sources.sort(key=lambda source: not source['priority'])
    curation['source_ids'] = [source['source_id'] for source in sources]
    config = detail.get('config', {})
    package = {'schema_version': 2, 'episode_id': episode_id, 'title': config.get('title', episode_id),
               'topic': config.get('topic', ''), 'target_seconds': config.get('target_duration', 300),
               'description': config.get('description', ''), 'key_points': config.get('key_points', []),
               'custom_instructions': config.get('custom_instructions', ''),
               'brief': brief.strip(),
               'sources': sources, 'warnings': warnings, 'curation': curation}
    from .direction import current_direction, write_direction, publish_package
    from .pack import show_bible, ad_slots, FORMAT_CONTRACT
    package.update(show_bible=show_bible(), ad_slots=ad_slots(episode_id), format_contract=FORMAT_CONTRACT)
    folder = episode_dir(episode_id) / 'context_packages'
    folder.mkdir(exist_ok=True)
    with file_lock(folder / 'context-update'):
        package['owner_direction'] = (write_direction(episode_id, owner_direction, expected_direction_revision)
                                      if owner_direction is not None else current_direction(episode_id))
        return publish_package(episode_id, package)
