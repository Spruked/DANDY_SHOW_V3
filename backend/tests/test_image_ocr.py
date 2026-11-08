import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont

from app.services.authoring.context import extract_document
from app.services.authoring.ocr import ocr_status, extract_image


class ImageOCRTests(unittest.TestCase):
    def test_local_ocr_preserves_locations_and_machine_transcription_label(self):
        if not ocr_status()['available']:
            self.skipTest('Local Tesseract with English data is not installed')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.png'
            image = Image.new('RGB', (1400, 240), 'white')
            font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 64)
            ImageDraw.Draw(image).text((40, 65), 'DANDY SOURCE EVIDENCE 123', fill='black', font=font)
            image.save(path)
            records = extract_document(path)
        self.assertIn('DANDY SOURCE EVIDENCE 123', ' '.join(r['text'] for r in records))
        self.assertEqual(records[0]['evidence_type'], 'machine-transcribed')
        self.assertTrue(records[0]['needs_review'])
        self.assertIn('pixels', records[0]['location'])
        self.assertIsNotNone(records[0]['ocr_confidence'])

    def test_empty_image_never_invents_a_description(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.png'
            Image.new('RGB', (200, 100), 'white').save(path)
            with patch('app.services.authoring.ocr._run', return_value='level\ttext\n'):
                with self.assertRaisesRegex(ValueError, 'does not describe pictures'):
                    extract_image(path)
