import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.authoring.extractors import extract_document, REGISTRY


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_bytes(text.encode('utf-8'))
        return path

    def test_markdown_preserves_all_text_headings_and_exact_line_ranges(self):
        original = '# Topic\nEvidence.\n```python\n# not a heading\n```\nPricing\n=======\nTen dollars.\n'
        path = self.write('README.md', original)
        records = extract_document(path)
        self.assertEqual(''.join(r['text'] for r in records), original)
        self.assertEqual([r['heading'] for r in records], ['Topic', 'Pricing'])
        self.assertEqual(records[1]['location'], 'lines 6-8')
        self.assertEqual(records[0]['source_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(extract_document(path)[0]['record_id'], records[0]['record_id'])
        for record in records:
            lines = original.splitlines(keepends=True)
            self.assertEqual(record['text'], ''.join(lines[record['line_start']-1:record['line_end']]))

    def test_python_symbols_comments_and_docstrings_are_read_without_execution(self):
        marker = self.root / 'executed.txt'
        original = f'from pathlib import Path\nPath({str(marker)!r}).write_text("EXECUTED")\n# A comment\ndef explain():\n    """A source docstring."""\n    return 123\n'
        records = extract_document(self.write('source.py', original))
        self.assertFalse(marker.exists())
        self.assertEqual(''.join(r['text'] for r in records), original)
        symbol = next(symbol for r in records for symbol in r.get('symbols', []) if symbol['name'] == 'explain')
        self.assertTrue(symbol['has_docstring'])
        self.assertEqual(symbol['docstring_location'], 'lines 5-5')
        self.assertEqual(symbol['line_start'], 4)
        self.assertTrue(all(r['extraction_method'] == 'python_ast_and_text' for r in records))

    def test_invalid_python_keeps_full_text_with_a_parse_warning(self):
        original = 'def broken(:\n    pass\n'
        records = extract_document(self.write('broken.py', original))
        self.assertEqual(''.join(r['text'] for r in records), original)
        self.assertIn('parsing failed', records[0]['parse_warning'])

    def test_registry_extension_needs_no_pack_assembly_change(self):
        path = self.write('sample.custom', 'Source evidence.')
        with patch.dict(REGISTRY, {'.custom': lambda p: [{'text': p.read_text(), 'location': 'custom locator', 'extraction_method': 'test_extractor'}]}):
            record = extract_document(path)[0]
        self.assertEqual(record['schema_version'], 1)
        self.assertEqual(record['extraction_method'], 'test_extractor')
        self.assertTrue(record['record_id'].startswith('record_'))

    def test_long_text_is_chunked_without_dropping_or_repeating_lines(self):
        original = ''.join(f'Line {i}\n' for i in range(203))
        records = extract_document(self.write('source.txt', original))
        self.assertEqual(len(records), 3)
        self.assertEqual(''.join(r['text'] for r in records), original)
        self.assertEqual(records[-1]['line_end'], 203)
