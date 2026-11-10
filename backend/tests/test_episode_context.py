"""Document handoff tests isolate all storage and never call a model."""
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.services.storage import episode_store as store
from app.services.authoring.context import extract_document


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name, value in [('EPISODES_ROOT', self.root / 'episodes'),
                            ('DRAFTS_ROOT', self.root / 'episodes/.drafts'),
                            ('JOBS_ROOT', self.root / 'episodes/.drafts/jobs')]:
            self.stack.enter_context(patch.object(store, name, value))
        self.client = self.stack.enter_context(TestClient(create_app(runtime_root=self.root, recover_jobs=False)))
        response = self.client.post('/api/episodes/create', json={'episode_id': 'context-test', 'title': 'Context test', 'topic': 'Evidence', 'target_duration': 300})
        self.assertEqual(response.status_code, 200, response.text)
        self.job = response.json()['job_id']
        self.url = '/api/episodes/context-test/context'

    def add_source(self, text='Original evidence.\n' * 500):
        response = self.client.post(self.url + '/sources/text', json={'title': 'Source', 'text': text, 'source_url': 'https://docs.google.com/example'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['asset_id']

    def test_empty_folders_are_not_listed_as_episodes(self):
        ghost = self.root / 'episodes/contract/assets'
        ghost.mkdir(parents=True)
        response = self.client.get('/api/episodes')
        self.assertEqual(response.status_code, 200, response.text)
        ids = [episode['episode_id'] for episode in response.json()['episodes']]
        self.assertIn('context-test', ids)
        self.assertNotIn('contract', ids)
        self.assertTrue(ghost.exists())

    def test_episode_creation_assigns_unique_ids_without_writing_dialogue(self):
        with patch('app.api.production._get_worker') as worker:
            first = self.client.post('/api/episodes/create', json={'title': 'Planning one', 'topic': 'Evidence', 'description': 'Owner episode brief.', 'target_duration': 600})
            second = self.client.post('/api/episodes/create', json={'title': 'Planning two', 'topic': 'Evidence'})
            worker.assert_not_called()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertRegex(first.json()['episode_id'], r'^ep_[0-9a-f]{12}$')
        self.assertNotEqual(first.json()['episode_id'], second.json()['episode_id'])
        self.assertEqual(first.json()['status'], 'draft_created')
        self.assertEqual(first.json()['config']['target_duration'], 600)
        self.assertFalse((store.episode_dir(first.json()['episode_id']) / 'script.json').exists())
        reference = self.client.get(f"/api/episodes/{first.json()['episode_id']}/context/reference").json()
        self.assertEqual(reference['episode_brief'], 'Owner episode brief.')

    def test_creation_cannot_overwrite_an_existing_episode(self):
        path = store.episode_dir('context-test') / 'config.json'
        before = path.read_bytes()
        response = self.client.post('/api/episodes/create', json={'episode_id': 'context-test', 'title': 'Overwrite', 'topic': 'Changed'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(path.read_bytes(), before)

    def test_full_text_provenance_versioning_and_no_script_mutation(self):
        asset = self.add_source('Fact one.\n' * 1000 + 'FINAL FACT AT THE END.')
        before = (store.episode_dir('context-test') / 'status.json').read_bytes()
        response = self.client.post(self.url, json={'brief': 'Explain the evidence.', 'source_ids': [asset]})
        self.assertEqual(response.status_code, 200, response.text)
        packet = response.json()
        self.assertIn('FINAL FACT AT THE END.', packet['markdown'])
        self.assertIn(asset, packet['markdown'])
        self.assertEqual(len(packet['sources'][0]['sha256']), 64)
        self.assertEqual(packet['target_seconds'], 300)
        self.assertEqual(packet['title'], 'Context test')
        self.assertFalse((store.episode_dir('context-test') / 'script.json').exists())
        self.assertEqual(before, (store.episode_dir('context-test') / 'status.json').read_bytes())
        self.assertEqual(self.client.get(self.url).json(), packet)
        second = self.client.post(self.url, json={'brief': 'Revised angle'}).json()
        self.assertNotEqual(packet['version_id'], second['version_id'])
        self.assertTrue((store.episode_dir('context-test') / 'context_packages' / (packet['version_id'] + '.json')).exists())

    def test_unreadable_sources_are_reported_and_missing_selection_rejected(self):
        self.add_source('Readable evidence.')
        response = self.client.post('/api/episodes/context-test/assets', files={'file': ('old.doc', b'legacy document', 'application/msword')})
        self.assertEqual(response.status_code, 200, response.text)
        packet = self.client.post(self.url, json={}).json()
        self.assertIn('old.doc', packet['warnings'][0])
        self.assertEqual(len(packet['sources']), 1)
        self.assertEqual(self.client.post(self.url, json={'source_ids': ['missing']}).status_code, 422)
        self.assertEqual(self.client.post(self.url, json={'source_ids': []}).status_code, 422)

    def test_owner_direction_is_first_separate_and_versioned_without_reextracting_evidence(self):
        asset = self.add_source('The original price is ten dollars.')
        owner = {'episode_direction': 'Explain the real costs.', 'angle_and_tone': 'Teaching with dry humor',
                 'must_include': 'Explain the fee.', 'must_avoid': 'Do not claim it is free.',
                 'segment_notes': 'Closing: ask what remains unknown.', 'per_source_notes': {asset: 'Use only the pricing section.'}}
        response = self.client.post(self.url, json={'brief': 'Pricing episode', 'source_ids': [asset],
                                    'owner_direction': owner, 'expected_direction_revision': ''})
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()
        self.assertEqual(first['owner_direction']['authority'], 'owner_direction')
        self.assertEqual(first['owner_direction']['per_source_notes'], owner['per_source_notes'])
        self.assertNotIn('owner_direction', first['sources'][0])
        headings = ['## Owner direction', '## Episode brief', '## Show bible', '## Source facts', '## Format contract', '## Ad slots']
        positions = [first['markdown'].index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('Use only the pricing section.', first['markdown'])
        self.assertEqual({character['speaker'] for character in first['show_bible']}, {'phil', 'jim'})
        original_path = store.episode_dir('context-test') / 'context_packages' / (first['version_id'] + '.json')
        original_bytes = original_path.read_bytes()
        owner['episode_direction'] = 'Focus on affordability.'
        with patch('app.services.authoring.context.extract_document', side_effect=AssertionError('Must reuse evidence')):
            response = self.client.put(self.url + '/direction', json={'owner_direction': owner,
                                       'expected_direction_revision': first['owner_direction']['revision_id']})
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertTrue(updated['pack_regenerated'])
        second = updated['package']
        self.assertNotEqual(first['version_id'], second['version_id'])
        self.assertEqual(second['parent_version_id'], first['version_id'])
        self.assertEqual(second['sources'], first['sources'])
        self.assertEqual(second['show_bible'], first['show_bible'])
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(self.client.get(self.url).json(), second)
        self.assertEqual(self.client.get(self.url + '/direction').json(), updated['owner_direction'])

    def test_direction_can_be_saved_before_sources_and_used_by_next_pack(self):
        response = self.client.put(self.url + '/direction', json={'owner_direction': {'episode_direction': 'My own words.'}, 'expected_direction_revision': ''})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['package'])
        self.assertFalse(response.json()['pack_regenerated'])
        self.add_source()
        packet = self.client.post(self.url, json={}).json()
        self.assertEqual(packet['owner_direction']['episode_direction'], 'My own words.')
        self.assertEqual(packet['owner_direction']['revision_id'], response.json()['owner_direction']['revision_id'])

    def test_stale_direction_edits_and_unknown_source_notes_are_rejected(self):
        initial = self.client.put(self.url + '/direction', json={'owner_direction': {'must_avoid': 'Unsupported claims'}, 'expected_direction_revision': ''}).json()
        response = self.client.put(self.url + '/direction', json={'owner_direction': {'must_avoid': 'Overwrite'}, 'expected_direction_revision': ''})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(self.url + '/direction').json(), initial['owner_direction'])
        response = self.client.put(self.url + '/direction', json={'owner_direction': {'per_source_notes': {'missing': 'Unknown source'}}})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(self.url + '/direction').json(), initial['owner_direction'])

    def test_docx_paragraphs_and_tables_have_references(self):
        path = self.root / 'source.docx'
        with zipfile.ZipFile(path, 'w') as doc:
            doc.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>First fact.</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table fact.</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        sections = extract_document(path)
        self.assertEqual([s['text'] for s in sections], ['First fact.', 'Table fact.'])
        self.assertEqual(sections[1]['location'], 'paragraph 2')

    def test_pdf_text_and_empty_scan_are_distinguished(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 50 700 Td (PDF source evidence.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        path = self.root / 'source.pdf'
        writer.write(path)
        record = extract_document(path)[0]
        self.assertEqual(record['location'], 'page 1')
        self.assertEqual(record['text'], 'PDF source evidence.')
        self.assertEqual(record['evidence_type'], 'direct-extracted')
        self.assertEqual(record['schema_version'], 1)
        empty = PdfWriter(); empty.add_blank_page(width=100, height=100); empty.write(path)
        with self.assertRaisesRegex(ValueError, 'OCR'):
            extract_document(path)

    def test_priority_and_size_budget_preserve_every_selected_source(self):
        first = self.add_source('Evidence A. ' * 1000)
        second = self.add_source('Evidence B. ' * 1000)
        before = (store.episode_dir('context-test') / 'status.json').read_bytes()
        inspect = self.client.post(self.url + '/inspect', json={'source_ids': [first, second]})
        self.assertEqual(inspect.status_code, 200, inspect.text)
        self.assertEqual(len(inspect.json()['sources']), 2)
        self.assertGreater(inspect.json()['estimated_source_tokens'], 0)
        self.assertFalse(inspect.json()['exact_tokenizer'])
        self.assertEqual(before, (store.episode_dir('context-test') / 'status.json').read_bytes())
        self.assertIsNone(self.client.get(self.url).json())
        response = self.client.post(self.url, json={'source_ids': [first, second], 'curation': {
            'priority_source_ids': [second], 'model_name': 'My external writer',
            'context_window_tokens': 1024, 'reserved_output_tokens': 256}})
        self.assertEqual(response.status_code, 200, response.text)
        packet = response.json()
        self.assertEqual(packet['sources'][0]['source_id'], second)
        self.assertTrue(packet['sources'][0]['priority'])
        self.assertEqual({s['source_id'] for s in packet['sources']}, {first, second})
        self.assertEqual(sum(s['character_count'] for s in packet['sources']), 24000)
        self.assertFalse(packet['sizing']['fits_estimate'])
        self.assertFalse(packet['sizing']['exact_tokenizer'])
        self.assertEqual(packet['sizing']['model_name'], 'My external writer')
        self.assertIn('PRIORITY SOURCE', packet['markdown'])
        self.assertEqual(packet['sources'][0]['sections'][0]['source_id'], second)
        self.assertEqual(packet['sources'][0]['sections'][0]['source_sha256'], packet['sources'][0]['sha256'])

    def test_invalid_priority_or_output_reservation_is_rejected(self):
        source = self.add_source()
        response = self.client.post(self.url, json={'source_ids': [source], 'curation': {'priority_source_ids': ['missing']}})
        self.assertEqual(response.status_code, 422)
        response = self.client.post(self.url, json={'curation': {'context_window_tokens': 1024, 'reserved_output_tokens': 1024}})
        self.assertEqual(response.status_code, 422)

    def test_writer_requires_saved_context_and_retired_rewrite_never_mutates_script(self):
        with patch('app.api.production.save_script') as save:
            response = self.client.post(f'/api/episodes/generate-script?job_id={self.job}')
            self.assertEqual(response.status_code, 422)
            self.assertIn('context package', response.json()['detail'])
            response = self.client.post('/api/episodes/edit-script', json={'episode_id': 'context-test', 'edit_type': 'regenerate_section', 'section_start': 0, 'section_end': 1})
            self.assertEqual(response.status_code, 410)
            save.assert_not_called()

    def test_external_import_creates_canonical_without_approval(self):
        self.add_source()
        self.client.post(self.url, json={})
        response = self.client.post('/api/episodes/context-test/replace-script', json={'text': 'PHIL: Welcome to the show.\nJIM: Let us examine the evidence.'})
        self.assertEqual(response.status_code, 200, response.text)
        versions = self.client.get('/api/episodes/context-test/canonical-scripts').json()
        self.assertIn('canonical_v0001', json.dumps(versions))
        state = self.client.get('/api/episodes/context-test/production-editor').json()
        self.assertFalse(state.get('current_approved_version_id'))
        self.assertEqual(response.json()['script'][0]['generated_by'], 'script_feed')

    def test_short_writer_is_bounded_and_uses_pinned_model(self):
        from app.services.authoring.short_copy import generate_short_copy
        with patch.dict('os.environ', {'DANDY_WRITER_PROVIDER': 'llamacpp'}), patch('app.services.authoring.short_copy.llm_writer._verified_model', return_value='pinned'), patch('app.services.authoring.short_copy.llm_writer._post_json', return_value={'choices': [{'finish_reason': 'stop', 'message': {'content': 'A short factual post.'}}]}) as post:
            self.assertEqual(generate_short_copy('post', 'Supplied facts'), 'A short factual post.')
            self.assertEqual(post.call_args.args[1]['model'], 'pinned')
            self.assertIn('120 words', post.call_args.args[1]['messages'][0]['content'])
        with patch.dict('os.environ', {'DANDY_WRITER_PROVIDER': 'llamacpp'}), patch('app.services.authoring.short_copy.llm_writer._verified_model', return_value='pinned'), patch('app.services.authoring.short_copy.llm_writer._post_json', return_value={'choices': [{'finish_reason': 'length', 'message': {'content': 'Incomplete'}}]}):
            with self.assertRaisesRegex(ValueError, 'truncated'):
                generate_short_copy('ad', 'Facts')
        self.assertEqual(self.client.post('/api/authoring/short-copy', json={'kind': 'episode', 'facts': 'Facts'}).status_code, 422)
