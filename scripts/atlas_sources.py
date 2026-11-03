"""Inventory source files and OCR map pages. Never alter source documents."""
import csv
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
WORK = Path('/workspace/amp-atlas-work')
OUT = ROOT / 'outputs'


def inspect_file(filename):
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    path = Path(filename)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cache = WORK / 'source_pages' / digest
    cache.mkdir(parents=True, exist_ok=True)
    result_file = cache / 'inspection.json'
    if result_file.exists():
        result = json.loads(result_file.read_text())
        result['source'] = str(path.relative_to(SOURCE))
        return result
    result = {'source': str(path.relative_to(SOURCE)), 'sha256': digest,
              'bytes': len(raw), 'pages': [], 'geospatial_objects': [], 'errors': []}
    try:
        doc = pymupdf.open(path)
        if path.suffix.lower() == '.pdf':
            for xref in range(1, doc.xref_length()):
                try:
                    if '/GPTS' in doc.xref_object(xref):
                        result['geospatial_objects'].append(xref)
                except Exception:
                    pass
        for i in range(len(doc)):
            page_result = {'page': i + 1}
            image_file = cache / f'page_{i + 1:03d}.jpg'
            text_file = cache / f'page_{i + 1:03d}.txt'
            try:
                page = doc[i]
                try:
                    text = page.get_text()
                except Exception:
                    text = ''
                if not image_file.exists():
                    scale = min(150/72, 3200/max(page.rect.width, page.rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    pix.save(image_file, jpg_quality=88)
                # OCR scans or broken font encodings; preserve native text separately.
                useful = len(re.findall(r'[A-Za-z]{3,}', text))
                if useful < 25:
                    if not text_file.exists():
                        proc = subprocess.run(
                            ['tesseract', str(image_file), str(text_file.with_suffix('')), '--psm', '3'],
                            capture_output=True, timeout=120,
                            env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
                        )
                        if proc.returncode:
                            raise RuntimeError('OCR failed: ' + proc.stderr.decode(errors='replace')[-200:])
                    text = text_file.read_text()
                    page_result['text_method'] = 'OCR; identifiers require confirmation'
                else:
                    text_file.write_text(text)
                    page_result['text_method'] = 'PDF text'
                page_result.update({'image_file': str(image_file), 'text_file': str(text_file),
                                    'width_points': page.rect.width, 'height_points': page.rect.height,
                                    'text': text})
                page_result['farm_ids_detected'] = sorted(set(re.findall(
                    r'\bFarm\s*(?:Number|No\.?|#)?\s*[:#]?\s*(\d{1,6})\b', text, flags=re.I)))
                page_result['tract_ids_detected'] = sorted(set(re.findall(
                    r'\bTract\s*(?:Number|No\.?|#)?\s*[:#]?\s*(\d{1,6})\b', text, flags=re.I)))
                page_result['map_like'] = bool(re.search(
                    r'\bNHEL\b|map\s+created|tract\s+cropland|common\s+land\s+unit|\bFeet\b|\bFSA\b', text, re.I))
            except Exception as exc:
                page_result['error'] = str(exc)
                result['errors'].append(f'page {i + 1}: {exc}')
            result['pages'].append(page_result)
    except Exception as exc:
        result['errors'].append(str(exc))
    result_file.write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    (OUT / 'qa').mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in SOURCE.rglob('*') if p.is_file())
    inventory = [{'source_file': str(p.relative_to(SOURCE)), 'extension': p.suffix.lower(),
                  'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    with (OUT / 'qa/source_file_inventory.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inventory[0]))
        writer.writeheader()
        writer.writerows(inventory)
    print('Source file types:', dict(Counter(p.suffix.lower() for p in files)), flush=True)
    media = [p for p in files if p.suffix.lower() in ('.pdf', '.jpg', '.jpeg')]
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(inspect_file, str(p)): p for p in media}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            if index % 10 == 0 or index == len(media):
                print(f'Inspected {index}/{len(media)} sources', flush=True)
    results.sort(key=lambda r: r['source'])
    (WORK / 'source_inspections.json').write_text(json.dumps(results, indent=2))
    public = [{'source_file': r['source'], 'sha256': r['sha256'], 'pages': len(r['pages']),
               'geospatial_objects': len(r['geospatial_objects']),
               'map_like_pages': sum(p.get('map_like', False) for p in r['pages']),
               'page_errors': '; '.join(r['errors'])} for r in results]
    with (OUT / 'qa/source_map_inspection.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(public[0]))
        writer.writeheader()
        writer.writerows(public)
    print('Finished:', len(results), 'map/image sources;', sum(len(r['pages']) for r in results), 'pages', flush=True)
