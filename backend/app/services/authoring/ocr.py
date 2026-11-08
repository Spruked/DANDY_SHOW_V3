"""Local Tesseract OCR; results are machine transcription, never verified fact."""
import csv
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from ...core.paths import PROJECT_ROOT


def tesseract_path():
    settings_path = PROJECT_ROOT / 'config/runtime.local.json'
    settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
    candidates = [os.getenv('DANDY_TESSERACT_PATH'), settings.get('tesseract_path'),
                  shutil.which('tesseract'), r'C:\Program Files\Tesseract-OCR\tesseract.exe']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('Tesseract is not installed. Set DANDY_TESSERACT_PATH or runtime.local.json tesseract_path.')


def _run(arguments, timeout=90):
    result = subprocess.run([tesseract_path(), *arguments], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Tesseract OCR failed: ' + (result.stderr.strip() or f'exit {result.returncode}')[:800])
    return result.stdout


def ocr_status():
    try:
        version = _run(['--version'], timeout=5).splitlines()[0]
        languages = _run(['--list-langs'], timeout=5).splitlines()[1:]
        return {'available': 'eng' in languages, 'version': version, 'languages': languages,
                'engine': 'tesseract', 'local_only': True}
    except Exception as exc:
        return {'available': False, 'engine': 'tesseract', 'error': str(exc), 'local_only': True}


def extract_image(path: Path):
    sections = []
    with Image.open(path) as image, tempfile.TemporaryDirectory(prefix='dandy-ocr-') as directory:
        frames = getattr(image, 'n_frames', 1)
        if frames > 20:
            raise ValueError('Image exceeds 20 frames; split the document before OCR')
        for frame in range(frames):
            image.seek(frame)
            if image.width * image.height > 30_000_000:
                raise ValueError('Image exceeds 30 million pixels; resize it before OCR')
            oriented = ImageOps.exif_transpose(image)
            rgba = oriented.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            prepared = Path(directory) / 'frame.png'
            ImageOps.autocontrast(ImageOps.grayscale(background)).save(prepared)
            tsv = _run([str(prepared), 'stdout', '-l', 'eng', 'tsv'])
            groups = {}
            for word in csv.DictReader(io.StringIO(tsv), delimiter='\t'):
                text = word.get('text', '').strip()
                if word.get('level') != '5' or not text:
                    continue
                key = (word['block_num'], word['par_num'], word['line_num'])
                groups.setdefault(key, []).append(word)
            for words in groups.values():
                x = min(int(w['left']) for w in words); y = min(int(w['top']) for w in words)
                right = max(int(w['left']) + int(w['width']) for w in words)
                bottom = max(int(w['top']) + int(w['height']) for w in words)
                confidences = [float(w['conf']) for w in words if float(w['conf']) >= 0]
                sections.append({'location': f'frame {frame + 1}, pixels ({x},{y},{right-x},{bottom-y})',
                    'text': ' '.join(w['text'] for w in words), 'extraction_method': 'tesseract_ocr',
                    'evidence_type': 'machine-transcribed', 'needs_review': True,
                    'ocr_confidence': round(sum(confidences) / len(confidences), 2) if confidences else None,
                    'bounding_box': {'x': x, 'y': y, 'width': right-x, 'height': bottom-y},
                    'coordinate_system': 'EXIF-oriented image pixels', 'frame': frame + 1})
    if not sections:
        raise ValueError('OCR found no readable text. Tesseract does not describe pictures; try a clearer image.')
    return sections
