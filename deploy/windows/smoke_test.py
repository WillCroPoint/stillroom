"""Headless packaged-resource and spawned-worker check; never sends to a frame."""
import io
import json
from pathlib import Path
import tempfile
import time
import traceback


def run_check(report):
    result = {}
    try:
        from PIL import Image
        from gui import ROOT, Studio
        for asset in ('index.html', 'app.js', 'style.css'):
            assert (ROOT / 'web' / asset).is_file(), f'Missing asset: {asset}'
        with tempfile.TemporaryDirectory() as directory:
            studio = Studio(Path(directory) / 'frames.json')
            try:
                studio.save_config({'version': 1, 'frames': [{
                    'id': 'test', 'name': 'Build test', 'host': 'test.invalid',
                    'screen': '133', 'orientation': 'portrait'}]})
                image = io.BytesIO()
                Image.new('RGB', (120, 160), 'red').save(image, format='PNG')
                source = studio.add_image(image.getvalue(), 'test.png')
                job = studio.start_conversion({'source_id': source['id'],
                    'frame_id': 'test', 'settings': {}})
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    with studio.lock:
                        current = dict(studio.jobs[job['id']])
                    if current['status'] != 'converting':
                        break
                    time.sleep(0.1)
                assert current['status'] == 'ready', current
                assert current['bytes'] == 960000, current
                result = {'ok': True, 'bytes': current['bytes']}
            finally:
                studio.close()
    except Exception:
        result = {'ok': False, 'error': traceback.format_exc()}
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
