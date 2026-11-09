"""Local extractors emit one source-record schema. Uploaded code is never run."""
import ast
import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
REGISTRY = {}


def register(*suffixes):
    def decorate(function):
        REGISTRY.update({suffix: function for suffix in suffixes})
        return function
    return decorate


def read_text(path):
    raw = path.read_bytes()
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')


@register('.txt', '.md', '.markdown', '.rst', '.csv', '.json', '.log')
def text_records(path):
    text = read_text(path)
    lines = text.splitlines(keepends=True)
    headings = markdown_headings(lines) if path.suffix.lower() in {'.md', '.markdown'} or path.name.lower().endswith('readme') else {}
    return line_records(lines, headings, 'direct_text')


def markdown_headings(lines):
    headings, fence = {}, None
    for i, line in enumerate(lines):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        if re.match(r'^#{1,6}\s+', line):
            headings[i] = line.strip().lstrip('#').strip()
        elif i and re.match(r'^\s*(?:=+|-+)\s*$', line) and lines[i-1].strip():
            headings[i-1] = lines[i-1].strip()
    return headings


def line_records(lines, headings, method, symbols=None, parse_warning=None):
    starts = sorted({0, *headings})
    records = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        for offset in range(start, end, 80):
            finish = min(offset + 80, end)
            record = {'location': f'lines {offset + 1}-{finish}', 'line_start': offset + 1,
                      'line_end': finish, 'text': ''.join(lines[offset:finish]), 'extraction_method': method}
            if headings.get(start):
                record['heading'] = headings[start]
            if symbols is not None:
                record['symbols'] = [s for s in symbols if offset < s['line_start'] <= finish]
            if parse_warning:
                record['parse_warning'] = parse_warning
            records.append(record)
    return records


@register('.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.html', '.css',
          '.ps1', '.sh', '.sql', '.go', '.rs', '.java', '.c', '.cpp', '.h', '.cs',
          '.yaml', '.yml', '.toml', '.xml', '.ini')
def code_records(path):
    text = read_text(path)
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError('Document exceeds one million extracted characters; split it into smaller sources')
    lines = text.splitlines(keepends=True)
    symbols, warning = [], None
    method = 'code_text'
    if path.suffix.lower() in {'.py', '.pyi'}:
        try:
            tree = ast.parse(text)
            method = 'python_ast_and_text'
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbol = {'name': node.name, 'kind': type(node).__name__, 'line_start': node.lineno,
                              'line_end': node.end_lineno, 'has_docstring': ast.get_docstring(node) is not None}
                    if symbol['has_docstring']:
                        symbol['docstring_location'] = f'lines {node.body[0].lineno}-{node.body[0].end_lineno}'
                    symbols.append(symbol)
        except SyntaxError as exc:
            warning = f'Python structure parsing failed at line {exc.lineno}; full source retained as text.'
    elif path.suffix.lower() in {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}:
        method = 'javascript_text_with_heuristic_symbols'
        for i, line in enumerate(lines, 1):
            match = re.match(r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class)\s+([\w$]+)', line)
            if match:
                symbols.append({'name': match.group(2), 'kind': match.group(1), 'line_start': i,
                                'heuristic': True})
    headings = {s['line_start'] - 1: f"{s['kind']} {s['name']}" for s in symbols}
    return line_records(lines, headings, method, symbols, warning)


@register('.pdf')
def pdf_records(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('Export an unencrypted PDF before importing it')
    return [{'location': f'page {i}', 'page': i, 'text': page.extract_text() or '',
             'extraction_method': 'pdf_text_layer'} for i, page in enumerate(reader.pages, 1)]


@register('.docx')
def word_records(path):
    with zipfile.ZipFile(path) as doc:
        entry = doc.getinfo('word/document.xml')
        if entry.file_size > MAX_SOURCE_BYTES:
            raise ValueError('Expanded Word document exceeds 20 MiB')
        tree = ElementTree.fromstring(doc.read(entry))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    records = []
    for i, paragraph in enumerate(tree.findall('.//w:p', ns), 1):
        text = ''.join((node.text or '') if node.tag.endswith('}t') else '\t' if node.tag.endswith('}tab')
                       else '\n' if node.tag.endswith('}br') else '' for node in paragraph.iter())
        record = {'location': f'paragraph {i}', 'paragraph': i, 'text': text, 'extraction_method': 'docx_body'}
        style = paragraph.find('w:pPr/w:pStyle', ns)
        if style is not None and style.get(f"{{{ns['w']}}}val", '').lower().startswith('heading'):
            record['heading'] = text
        records.append(record)
    return records


@register('.pptx')
def powerpoint_records(path):
    """Extract visible slide text without executing embedded content."""
    with zipfile.ZipFile(path) as deck:
        slides = sorted(name for name in deck.namelist()
                        if re.fullmatch(r'ppt/slides/slide\d+\.xml', name))
        records = []
        ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
        for number, name in enumerate(slides, 1):
            tree = ElementTree.fromstring(deck.read(name))
            text = ' '.join(node.text or '' for node in tree.findall('.//a:t', ns)).strip()
            records.append({'location': f'slide {number}', 'slide': number, 'text': text,
                            'extraction_method': 'pptx_text'})
        return records


@register('.xlsx')
def spreadsheet_records(path):
    """Extract spreadsheet cell values using the OOXML package directly."""
    with zipfile.ZipFile(path) as workbook:
        shared = []
        if 'xl/sharedStrings.xml' in workbook.namelist():
            tree = ElementTree.fromstring(workbook.read('xl/sharedStrings.xml'))
            ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            shared = [''.join(node.text or '' for node in item.findall('.//x:t', ns))
                      for item in tree.findall('.//x:si', ns)]
        records = []
        ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for sheet in sorted(name for name in workbook.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', name)):
            tree = ElementTree.fromstring(workbook.read(sheet))
            values = []
            for cell in tree.findall('.//x:c', ns):
                value = cell.find('x:v', ns)
                if value is None or not (value.text or '').strip():
                    continue
                raw = value.text.strip()
                if cell.get('t') == 's' and raw.isdigit() and int(raw) < len(shared):
                    raw = shared[int(raw)]
                values.append(f"{cell.get('r', '?')}={raw}")
            records.append({'location': sheet.replace('xl/worksheets/', ''), 'text': '\n'.join(values),
                            'extraction_method': 'xlsx_cells'})
        return records


@register('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp', '.gif')
def image_records(path):
    from .ocr import extract_image
    return extract_image(path)


def extract_document(path: Path):
    path = Path(path)
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('Document exceeds the 20 MiB context limit')
    extractor = REGISTRY.get(path.suffix.lower())
    if extractor is None and path.name.lower().endswith('readme'):
        extractor = text_records
    if extractor is None:
        raise ValueError('Unsupported document. Use text, code, Markdown, PDF, DOCX, PPTX, XLSX or an OCR image.')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    records = extractor(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError('Source changed during extraction. Retry with a stable file.')
    if not any(r['text'].strip() for r in records):
        raise ValueError('No readable text found. Scanned documents need OCR first.')
    if sum(len(r['text']) for r in records) > MAX_TEXT_CHARS:
        raise ValueError('Document exceeds one million extracted characters; split it into smaller sources')
    for record in records:
        record.update(schema_version=1, source_sha256=before, source_name=path.name)
        record.setdefault('evidence_type', 'direct-extracted')
        record.setdefault('needs_review', False)
        identity = f"{before}\n{record['extraction_method']}\n{record['location']}\n{record['text']}"
        record['record_id'] = 'record_' + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return records
