"""Isolated contracts: no provider calls, GPU work, or live episode mutations."""
import io
import json
import tempfile
import shutil
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.api import ads, production
from app.services.authoring import generated_drafts
from app.services.production import llm_writer as writer
from app.services.production.ads import AD_SLOT_IDS, ad_audio_fingerprint
from app.services.production.worker import HardenedPodcastWorker
from app.services.storage import episode_store as store


def dialogue(count=8):
    return [{'speaker': 'phil' if index % 2 == 0 else 'jim',
             'text': f'This is complete sample sentence number {index}.',
             'emotion': 'neutral', 'pause_after': 0.0} for index in range(count)]


class WriterContracts(unittest.TestCase):
    def test_episode_budget_and_short_copy_payload_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(writer, '_PROJECT_ROOT', Path(tmp)), \
             patch.dict(writer.os.environ, {'NVIDIA_API_KEY': 'test-only', 'DANDY_NVIDIA_MAX_RETRIES': '0'}):
            body = {'choices': [{'finish_reason': 'stop', 'message': {'content': '[]'}}], 'usage': {}}
            for kind in ('episode', 'short-copy'):
                with patch.object(writer.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(body).encode())) as call:
                    writer._call_nvidia('Prompt', kind=kind)
                payload = json.loads(call.call_args.args[0].data)
                self.assertEqual(payload.get('reasoning_budget'), 2000 if kind == 'episode' else None)
                self.assertNotIn('chat_template_kwargs', payload)

    def test_truncation_captures_request_and_response_before_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(writer, '_PROJECT_ROOT', Path(tmp)), \
             patch.dict(writer.os.environ, {'NVIDIA_API_KEY': 'test-only', 'DANDY_NVIDIA_MAX_RETRIES': '0'}):
            body = {'choices': [{'finish_reason': 'length', 'message': {'content': '[partial'}}],
                    'usage': {'completion_tokens': 6000, 'completion_tokens_details': {'reasoning_tokens': 2000}}}
            success = writer._USAGE['success_count']
            with patch.object(writer.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
                with self.assertRaisesRegex(RuntimeError, 'truncated'):
                    writer._call_nvidia('Prompt', kind='episode')
            saved = json.loads((Path(tmp) / 'data/debug/nemotron_last_episode_response.json').read_text())
            self.assertEqual(saved['response'], body)
            self.assertEqual(saved['request_payload']['reasoning_budget'], 2000)
            self.assertNotIn('test-only', json.dumps(saved))
            self.assertEqual(writer._USAGE['success_count'], success)
            self.assertEqual(len(list((Path(tmp) / 'data/debug').glob('nemotron_episode_*.json'))), 1)

    def test_malformed_turns_are_rejected_without_silent_deletion(self):
        for change in ('speaker', 'pause', 'field', 'commentary'):
            lines = dialogue()
            if change == 'speaker':
                lines[1]['speaker'] = 'phil'
            if change == 'pause':
                lines[1]['pause_after'] = True
            if change == 'field':
                lines[1]['analysis'] = 'Planning'
            raw = ('Planning first. ' if change == 'commentary' else '') + json.dumps(lines)
            with self.subTest(change=change), patch.object(writer, '_call_nvidia', return_value=raw):
                with self.assertRaises(RuntimeError):
                    writer.generate_episode_script('Context', sample=True)

    def test_numeric_zero_pause_preserved_and_short_full_episode_rejected(self):
        with patch.object(writer, '_call_nvidia', return_value=json.dumps(dialogue())):
            self.assertEqual(writer.generate_episode_script('Context', sample=True)[0]['pause_after'], 0)
            with self.assertRaisesRegex(RuntimeError, 'expected approximately'):
                writer.generate_episode_script('Context', target_words=4000)

    def test_voice_studio_profile_is_resolved(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.voices_config = {'phil': {'voicestudio_voice': 'canonical-phil-profile'}}
        self.assertEqual(worker._resolve_voice_name('phil', 'voicestudio'), 'canonical-phil-profile')

    def test_announcer_uses_voice_studio_worker_and_pause_markers(self):
        from app.services.production import intro_outro
        from pydub import AudioSegment
        worker = Mock(voices_config={'announcer_male': {'voicestudio_voice': 'echo'}})
        def render(text, speaker, emotion, target):
            AudioSegment.silent(duration=100).export(target, format='mp3').close()
        worker._synthesize_line.side_effect = render
        with tempfile.TemporaryDirectory() as folder, \
             patch('app.core.settings.load_project_config', return_value={'tts': {'primary_engine': 'voicestudio'}}), \
             patch('app.core.settings.load_qwen_tts_config', return_value={}), \
             patch('app.services.production.worker.HardenedPodcastWorker', return_value=worker), \
             patch.object(intro_outro, '_synthesize_tts_wsl') as legacy:
            output = Path(folder) / 'intro.mp3'
            intro_outro._synthesize_tts_edge_sync('Welcome.[pause]Meet the brothers.', 'am_eric', output, 200)
            legacy.assert_not_called()
            self.assertEqual(worker._synthesize_line.call_count, 2)
            self.assertTrue(all(call.args[1] == 'announcer_male' for call in worker._synthesize_line.call_args_list))
            self.assertGreaterEqual(len(AudioSegment.from_file(output)), 390)

    def test_context_builder_rejects_tampered_persona_instead_of_falling_back(self):
        from app.services.authoring import pack
        project = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(project / 'config/characters', root / 'config/characters')
            shutil.copy2(project / 'persona_canon.py', root / 'persona_canon.py')
            persona = root / 'config/characters/phil.persona.json'
            value = json.loads(persona.read_text(encoding='utf-8'))
            value['shared_family']['childhood_dog']['name'] = 'Tampered'
            persona.write_text(json.dumps(value), encoding='utf-8')
            with patch.object(pack, 'PROJECT_ROOT', root), self.assertRaisesRegex(ValueError, 'validation failed'):
                pack.show_bible()


class DraftWorkflow(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name, value in [('EPISODES_ROOT', self.root / 'episodes'),
                            ('DRAFTS_ROOT', self.root / 'episodes/.drafts'),
                            ('JOBS_ROOT', self.root / 'episodes/.drafts/jobs')]:
            self.stack.enter_context(patch.object(store, name, value))
        self.stack.enter_context(patch.object(ads, 'EPISODES_ROOT', store.EPISODES_ROOT))
        self.client = self.stack.enter_context(TestClient(create_app(runtime_root=self.root, recover_jobs=False)))
        created = self.client.post('/api/episodes/create', json={'episode_id': 'safe', 'title': 'Safe', 'topic': 'Facts', 'target_duration': 1500})
        self.job_id = created.json()['job_id']
        self.url = '/api/episodes/generate-script?job_id=' + self.job_id
        self.client.post('/api/episodes/safe/context/sources/text', json={'title': 'Facts', 'text': 'Only these approved facts.'})
        self.pack = self.client.post('/api/episodes/safe/context', json={'brief': 'Keep this brief.'}).json()
        store.save_script('safe', dialogue(4))
        self.script_before = (store.episode_dir('safe') / 'script.json').read_bytes()

    def generate(self, sample=False):
        with patch.object(writer, 'generate_episode_script', return_value=dialogue()):
            result = self.client.post(self.url, json={'context_version_id': self.pack['version_id'], 'sample': sample})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_saved_context_and_active_script_unchanged_until_acceptance(self):
        before = (store.episode_dir('safe') / 'context_packages/latest.json').read_bytes()
        draft = self.generate()
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)
        self.assertEqual((store.episode_dir('safe') / 'context_packages/latest.json').read_bytes(), before)
        self.assertEqual(draft['context_version_id'], self.pack['version_id'])
        accepted = self.client.post(f"/api/episodes/safe/writer-drafts/{draft['draft_id']}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(len(store.load_script('safe')['script']), 8)

    def test_samples_cannot_be_activated(self):
        draft = self.generate(sample=True)
        response = self.client.post(f"/api/episodes/safe/writer-drafts/{draft['draft_id']}/accept")
        self.assertEqual(response.status_code, 409)
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)

    def test_failed_generation_preserves_script_and_records_failure(self):
        with patch.object(writer, 'generate_episode_script', side_effect=RuntimeError('truncated')):
            response = self.client.post(self.url, json={'context_version_id': self.pack['version_id']})
        self.assertEqual(response.status_code, 502)
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)
        self.assertEqual(store.load_job(self.job_id)['status'], 'failed')
        self.assertIsNone(production._ACTIVE_GENERATION)

    def test_concurrent_generation_is_rejected_before_provider_call(self):
        production._GENERATION_LOCK.acquire()
        try:
            with patch.object(writer, 'generate_episode_script') as model:
                response = self.client.post(self.url, json={})
                self.assertEqual(response.status_code, 409)
                model.assert_not_called()
        finally:
            production._GENERATION_LOCK.release()

    def test_draft_cannot_overwrite_script_edited_after_generation(self):
        draft = self.generate()
        store.save_script('safe', dialogue(6))
        response = self.client.post(f"/api/episodes/safe/writer-drafts/{draft['draft_id']}/accept")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(store.load_script('safe')['script']), 6)

    def test_tampered_draft_cannot_be_activated(self):
        draft = self.generate()
        path = store.episode_dir('safe') / 'generated_drafts' / f"{draft['draft_id']}.json"
        value = json.loads(path.read_text())
        value['script'][0]['text'] = 'Changed after generation.'
        path.write_text(json.dumps(value))
        response = self.client.post(f"/api/episodes/safe/writer-drafts/{draft['draft_id']}/accept")
        self.assertEqual(response.status_code, 409)
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)

    def test_saved_context_is_used_without_source_reextraction(self):
        original = (store.episode_dir('safe') / 'context_packages/latest.json').read_bytes()
        with patch.object(production, 'build_context', side_effect=AssertionError('No rebuilding during generation')):
            self.generate(sample=True)
        self.assertEqual((store.episode_dir('safe') / 'context_packages/latest.json').read_bytes(), original)

    def test_cancel_discards_result_and_keeps_original_script(self):
        def cancelled(*args, **kwargs):
            kwargs['cancel_event'].set()
            return dialogue()
        with patch.object(writer, 'generate_episode_script', side_effect=cancelled):
            response = self.client.post(self.url, json={})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(store.load_job(self.job_id)['status'], 'cancelled')
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)

    def test_seven_reserved_slots_and_explicit_assignment(self):
        settings = self.client.get('/api/episodes/safe/ad-settings').json()
        self.assertEqual([slot['slot_id'] for slot in settings['slots']], list(AD_SLOT_IDS))
        original = dialogue()
        self.assertEqual(production._enforce_ads_and_structure(original, [], settings), production._reindex(original))
        ad = store.save_ad('safe', {'script': [{'speaker': 'announcer_male', 'text': 'Sponsor message.'}]})
        settings['slots'][0]['assigned_ad_id'] = ad['ad_id']
        self.assertEqual(self.client.post('/api/episodes/safe/ad-settings', json=settings).status_code, 200)
        assembled = production._enforce_ads_and_structure(original, [ad], settings)
        self.assertEqual(assembled[0]['ad_slot_id'], 'pre_roll_1')
        self.assertEqual(len(assembled), len(original) + 1)

    def test_reusing_audio_does_not_modify_source_or_host_script(self):
        self.client.post('/api/episodes/create', json={'episode_id': 'source', 'title': 'Commercials', 'topic': 'Ads'})
        path = store.ads_dir('source') / 'source.mp3'
        # Fixture bytes exercise file preservation only; this is not audio QC.
        path.write_bytes(b'fixture-recording')
        lines = [{'speaker': 'announcer_male', 'text': 'Sponsor message.'}]
        record = store.save_ad('source', {'script': lines, 'audio_file': str(path),
                                         'sponsor': 'Fixture', 'audio_script_fingerprint': ad_audio_fingerprint(lines)})
        source_json = (path.parent / f"{record['ad_id']}.json").read_bytes()
        response = self.client.post('/api/episodes/safe/ads/reuse', json={'source_episode_id': 'source', 'ad_id': record['ad_id']})
        self.assertEqual(response.status_code, 200, response.text)
        copied = response.json()['ad']
        self.assertNotEqual(copied['ad_id'], record['ad_id'])
        self.assertEqual(Path(copied['audio_file']).read_bytes(), path.read_bytes())
        self.assertEqual((path.parent / f"{record['ad_id']}.json").read_bytes(), source_json)
        self.assertEqual((store.episode_dir('safe') / 'script.json').read_bytes(), self.script_before)
        listed = self.client.get('/api/ads/library').json()['ads']
        self.assertEqual(len(listed), 2)

    def test_library_ignores_attached_asset_lists(self):
        self.client.post('/api/episodes/create', json={'episode_id': 'source', 'title': 'Commercials', 'topic': 'Ads'})
        path = store.ads_dir('source') / 'source.mp3'
        path.write_bytes(b'fixture-recording')
        lines = [{'speaker': 'announcer_male', 'text': 'Sponsor message.'}]
        record = store.save_ad('source', {'script': lines, 'audio_file': str(path),
                                         'audio_script_fingerprint': ad_audio_fingerprint(lines)})
        (store.ads_dir('source') / f"{record['ad_id']}_assets.json").write_text('[{"asset_id": "asset_x"}]', encoding='utf-8')
        response = self.client.get('/api/ads/library')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([ad['ad_id'] for ad in response.json()['ads']], [record['ad_id']])


if __name__ == '__main__':
    unittest.main()
