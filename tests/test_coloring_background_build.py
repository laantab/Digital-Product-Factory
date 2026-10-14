"""The failed live four-page path, with local provider fixtures and real exports."""
import io
import json
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app import app
import database
from services.coloring_book import background, builder
from services.jobs import store
from services.jobs.workflow_runner import run_build
from services.storage import LocalFilesystemDriver

FIELDS = {'coloring_title': 'Deep water sea creatures', 'theme': 'Deep water sea creatures',
          'author_brand': 'Lonnie Brown', 'output_format': 'Digital Book', 'pages': '12',
          'quality_mode': 'AI Image Coloring Page', 'art_style': 'Cartoon comic-book',
          'age_group': 'Children ages 8–12', 'include_captions': 'No'}

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('FACTORY_EXECUTION_MODE', 'workflow')
    monkeypatch.setenv('FACTORY_WORKFLOW_TASK', 'digital-product-factory-builder/build_ebook')
    monkeypatch.setenv('RENDER_API_KEY', 'test-fixture')
    monkeypatch.setenv('FACTORY_PUBLISH_EXPORTS', '1')
    monkeypatch.setattr('services.storage.get_storage', lambda: LocalFilesystemDriver(tmp_path / 'stored'))
    monkeypatch.setattr('services.storage.compat.get_storage', lambda: LocalFilesystemDriver(tmp_path / 'stored'))
    monkeypatch.setattr('services.jobs.workflow_trigger._start_task', lambda *a: 'fixture-run')
    app.config['TESTING'] = True
    client = app.test_client()
    yield client


def begin(client, fields=None):
    response = client.post('/generate-product', json={'product_type': 'coloring_book', 'fields': fields or FIELDS})
    assert response.status_code == 200, response.get_json()
    return response.get_json()['project_id']


def art(prompt, path, **kwargs):
    with Image.new('RGB', (1024, 1536), 'white') as image:
        draw = ImageDraw.Draw(image)
        draw.ellipse((220, 400, 760, 950), outline='black', width=12)
        draw.polygon([(760, 650), (880, 490), (880, 850)], outline='black', width=12)
        draw.ellipse((330, 580, 350, 600), outline='black', width=8)
        image.save(path)
    return True


def plan(**kwargs):
    return {'pages': [{'topic': f'Sea creature {i}', 'line_art_prompt': f'Draw a coloring page featuring fish {i} in the deep ocean, black outline, white background'} for i in range(1, 13)]}


def test_website_queues_and_duplicate_clicks_share_one_project(setup):
    with patch('app.generate_product', side_effect=AssertionError('website must not render artwork')):
        pid = begin(setup)
        again = begin(setup)
    assert pid == again
    assert store.get_for_project(pid)['status'] == store.QUEUED
    assert setup.get(f'/coloring/build/{pid}/status').get_json()['status'] == 'queued'
    assert app.test_client().get(f'/coloring/build/{pid}/status').status_code == 404


def test_real_twelve_page_pdf_zip_and_read_only_download_handoff(setup):
    pid = begin(setup)
    with patch.object(builder, 'chat_json', side_effect=plan) as chat, patch.object(builder, 'generate_visual_image', side_effect=art) as images:
        out = run_build(pid)
        assert out['finished'], out['message']
        count = images.call_count
        assert count == 13
        assert run_build(pid)['finished']
        assert begin(setup) == pid
        assert images.call_count == count
        assert chat.call_count == 1
    response = setup.get(f'/coloring/build/{pid}/status')
    payload = response.get_json()
    assert 'pdf_bytes' not in payload['result']
    data = database.get_project(pid)['data']
    # Metadata Save must preserve server checkpoints and the original PDF.
    saved_body = {k: v for k, v in payload['result'].items() if k not in ('_project_id', '_workflow_save_pending')}
    saved = setup.put(f'/projects/{pid}', json={'name': data['title'], 'type': 'product', 'data': saved_body, 'user_saved': True, 'user_confirmed_save': True})
    assert saved.status_code == 200, saved.get_json()
    assert database.get_project(pid)['data']['pdf_bytes'] == data['pdf_bytes']
    assert setup.get(f'/coloring/build/{pid}/status').get_json()['finished']
    # Website cannot access the Workflow container's filesystem.
    shutil.rmtree(Path(builder.EXPORTS_DIR) / data['package_id'])
    published = setup.get(f'/coloring/build/{pid}/status').get_json()['result']
    assert published['cover_preview_missing'] is False
    assert all(not p['missing'] for p in published['interior_previews'])
    assert setup.get(published['interior_previews'][0]['url']).status_code == 200
    exports = data['product_exports']
    pdf_url = exports['files']['pdf']['url']
    zip_url = exports['files']['zip']['url']
    # Use the real public downloads, not a synthetic response envelope.
    pdf = setup.get(pdf_url)
    package = setup.get(zip_url)
    assert pdf.status_code == 200, pdf.get_data(as_text=True)[:200] if not pdf.data.startswith(b'%PDF') else ''
    assert package.status_code == 200
    assert len(PdfReader(io.BytesIO(pdf.data)).pages) == 13
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        assert any(archive.read(n) == pdf.data for n in archive.namelist() if n.endswith('.pdf'))
    with patch('app.build_product_export', side_effect=AssertionError('no web rerender')):
        ex = setup.post('/export-product', json={'project_id': pid})
        assert ex.status_code == 200, ex.get_json()


def test_restart_restores_saved_artwork_and_plan_without_rebilling(setup):
    pid = begin(setup)
    def interrupted(prompt, path, **kwargs):
        if 'coloring_p02' in path:
            raise KeyboardInterrupt('simulated process death')
        return art(prompt, path, **kwargs)
    with patch.object(builder, 'chat_json', side_effect=plan), patch.object(builder, 'generate_visual_image', side_effect=interrupted):
        with pytest.raises(KeyboardInterrupt):
            background.advance(pid)
    data = database.get_project(pid)['data']
    assert data['coloring_build']['completed_images'] == ['coloring_p01.png']
    # Simulate a new Workflow container: remove only this test's ephemeral files.
    folder = Path(builder.EXPORTS_DIR) / data['package_id']
    shutil.rmtree(folder)
    with patch.object(builder, 'chat_json', side_effect=AssertionError('saved plan must be reused')), patch.object(builder, 'generate_visual_image', side_effect=AssertionError('ambiguous artwork must not be charged again')):
        failed = background.advance(pid)
    assert failed['failed']
    assert 'interrupted' in failed['message']
    assert (folder / 'coloring_p01.png').is_file()


def test_storage_failure_stops_before_next_artwork(setup):
    pid = begin(setup)
    with patch.object(builder, 'chat_json', side_effect=plan), patch.object(builder, 'generate_visual_image', side_effect=art) as images, patch('services.storage.publish.publish_file', return_value=False):
        out = background.advance(pid)
    assert out['failed']
    assert images.call_count == 1
    assert 'safely saved' in out['message']


def test_pixel_metrics_match_exact_rgb_thresholds(tmp_path):
    from services.coloring_book.line_art_layout import ink_bounding_box, measure_line_art_layout
    path = tmp_path / 'thresholds.png'
    with Image.new('RGB', (25, 31), 'white') as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle((3, 4, 8, 9), fill=(0, 0, 0))
        image.putpixel((15, 18), (240, 255, 255))
        image.putpixel((16, 19), (39, 39, 40))
        pixels = list(image.getdata())
        image.save(path)
        assert ink_bounding_box(image) == (3, 4, 16, 19)
    metrics = measure_line_art_layout(str(path))
    assert metrics['white_pct'] == round(100 * sum(min(p) > 240 for p in pixels) / len(pixels), 4)
    assert metrics['black_ink_pct'] == round(100 * sum(max(p) < 40 for p in pixels) / len(pixels), 4)


def test_four_page_request_is_not_silently_expanded_into_paid_artwork(setup):
    with patch('services.jobs.workflow_trigger._start_task', side_effect=AssertionError('no workflow for invalid count')):
        response = setup.post('/generate-product', json={'product_type': 'coloring_book', 'fields': dict(FIELDS, pages='4')})
    assert response.status_code == 400
    assert 'You entered 4' in str(response.get_json())


def test_concurrent_requests_create_only_one_durable_project(setup):
    from concurrent.futures import ThreadPoolExecutor
    # A fixed server-established customer and identical normalized request.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: background.start(FIELDS, 'concurrent-fixture')['project_id'], range(2)))
    assert results[0] == results[1]


def test_image_measurements_stay_within_memory_budget(tmp_path):
    import subprocess
    import sys
    script = r"""
import sys, os
from PIL import Image, ImageDraw
from services.coloring_book.line_art_layout import prepare_print_interior_300dpi
from pathlib import Path
root=Path(sys.argv[1])
with Image.new('RGB',(1024,1536),'white') as image:
    ImageDraw.Draw(image).ellipse((80,120,940,1400),outline='black',width=12)
    image.save(root/'source.png')
for i in range(12):
    metrics=prepare_print_interior_300dpi(str(root/'source.png'),str(root/f'page{i}.png'))
    assert metrics['width']==2250 and metrics['height']==3000
if sys.platform.startswith('linux'):
    # VmHWM belongs to this exec'd process. ru_maxrss also includes the
    # pre-exec fork's inherited pytest memory, which is unrelated to image work.
    rows = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    print(int(rows['VmHWM'].split()[0]))
elif sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    counters=Counters(); counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=wintypes.HANDLE
    read = ctypes.WinDLL('psapi').GetProcessMemoryInfo
    read.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    assert read(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb)
    print(counters.PeakWorkingSetSize//1024)
else:
    import resource
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(peak//1024 if sys.platform=='darwin' else peak)
"""
    output = subprocess.check_output([sys.executable, '-c', script, str(tmp_path)], text=True)
    peak_kib = int(output.strip())
    assert peak_kib < 256 * 1024, f'Print processing exceeded 256 MiB: {peak_kib / 1024:.1f}'


def test_expired_builder_lease_offers_recovery_instead_of_endless_polling(setup):
    pid = begin(setup)
    job = store.claim_for_project('dead-fixture-worker', pid)
    conn = database.get_conn()
    conn.execute('UPDATE jobs SET lease_expires_at=? WHERE id=?', ('2000-01-01T00:00:00+00:00', job['id']))
    conn.commit()
    conn.close()
    payload = setup.get(f'/coloring/build/{pid}/status').get_json()
    assert payload['failed'] and payload['status'] == 'interrupted'
    assert 'saved artwork' in payload['message']


def test_failed_workflow_handoff_is_visible_and_recoverable(setup):
    with patch('services.jobs.workflow_trigger._start_task', side_effect=RuntimeError('offline')):
        pid = begin(setup)
    assert setup.get(f'/coloring/build/{pid}/status').get_json()['failed']
    assert store.get_for_project(pid)['status'] == store.QUEUED


def test_preview_stage_reuses_the_same_plan_and_shared_cover(setup):
    fields = dict(FIELDS, generation_stage='cover_preview')
    pid = begin(setup, fields)
    with patch.object(builder, 'chat_json', side_effect=plan), patch.object(builder, 'generate_visual_image', side_effect=art):
        first = run_build(pid)
    assert first['finished'] and first['status'] == 'review'
    original = database.get_project(pid)['data']
    folder = Path(builder.EXPORTS_DIR) / original['package_id']
    shutil.rmtree(folder)
    next_fields = dict(FIELDS, generation_stage='sample_interior', package_id=original['package_id'], _coloring_source_project_id=pid, character_approved='true')
    next_pid = begin(setup, next_fields)
    with patch.object(builder, 'chat_json', side_effect=AssertionError('reuse the recorded plan')), patch.object(builder, 'generate_visual_image', side_effect=art) as images:
        second = run_build(next_pid)
    assert second['finished'] and second['status'] == 'review'
    assert images.call_count == 1  # a sample; the cover is restored, not regenerated
