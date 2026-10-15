"""Published files survive lost final writes, ACKs, restarts and concurrent edits."""
import base64
import hashlib
import io
import sqlite3
import uuid
import zipfile
from unittest.mock import patch

import pytest
from reportlab.pdfgen.canvas import Canvas

from app import app
import database
from services.coloring_book import completion_recovery as recovery
from services.jobs import store
from services.quality.artifact_identity import stamp_artifact_identity
from services.storage import LocalFilesystemDriver
from services.storage.publish import publish_export
from tests.test_coloring_background_build import setup, begin, art, FIELDS


@pytest.fixture
def saved(tmp_path, monkeypatch):
    driver = LocalFilesystemDriver(tmp_path / 'stored')
    monkeypatch.setenv('FACTORY_PUBLISH_EXPORTS', '1')
    monkeypatch.setattr('services.storage.get_storage', lambda: driver)
    monkeypatch.setattr('services.storage.compat.get_storage', lambda: driver)
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: None)
    monkeypatch.setattr(recovery, '_cursor', 0)
    raw = io.BytesIO()
    c = Canvas(raw)
    c.drawString(60, 700, 'Sea Creatures')
    c.showPage()
    c.drawString(60, 700, 'Fish')
    c.save()
    pdf = raw.getvalue()
    data = {'product_type': 'coloring_book', 'title': 'Sea Creatures', 'package_id': uuid.uuid4().hex,
            'filename': 'sea_creatures.pdf', 'pdf_bytes': base64.b64encode(pdf).decode(),
            'fields': {'pages': '1'}, 'pages': [{'topic': 'Fish'}], 'qa_passed': True,
            'generation_stage': 'full', 'artifact_state': 'DRAFT',
            'coloring_build': {'status': 'running', 'message': 'Saved artwork', 'customer': 'owner',
                               'completed_images': ['coloring_p01.png'], 'pending_image': ''}}
    stamp_artifact_identity(data)
    p = database.create_project('Sea Creatures', 'product', data, user_saved=False)
    pid, pkg = p['id'], data['package_id']
    monkeypatch.setattr(recovery, '_cursor', pid - 1)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, 'w') as z:
        z.writestr(data['filename'], pdf)
        z.writestr('ebook.txt', 'Sea Creatures')
    package = zipped.getvalue()
    assert publish_export(pid, pkg + '/' + data['filename'], payload=pdf)
    assert publish_export(pid, pkg + '/package.zip', payload=package)
    store.init_jobs_table()
    store.enqueue(pid)
    conn = database.get_conn()
    conn.execute('UPDATE jobs SET status=?, lease_owner=?, lease_expires_at=? WHERE project_id=?',
                 (store.RUNNING, 'dead-builder', '2000-01-01T00:00:00', pid))
    conn.commit()
    conn.close()
    return pid, pdf, package, driver


def test_boot_sweep_recovers_exact_exports_and_preserves_save_consent(saved):
    pid, pdf, package, driver = saved
    original = database.get_project(pid)['data']
    with patch('services.product.generate_product', side_effect=AssertionError('no generation')), \
         patch('services.packaging.build_product_export', side_effect=AssertionError('no re-export')), \
         patch.object(driver, 'put', side_effect=AssertionError('read only artifacts')):
        recovery.sweep()
        recovery.sweep()
    p = database.get_project(pid)
    assert p['data']['export_ready'] and p['data']['coloring_build']['status'] == 'complete'
    assert p['user_saved'] is False
    for key in ('pdf_bytes', 'fields', 'pages', 'artifact_id', 'artifact_revision', 'content_digest', 'asset_manifest_digest'):
        assert p['data'][key] == original[key]
    assert p['data']['export_files']['pdf']['sha256'] == hashlib.sha256(pdf).hexdigest()
    assert p['data']['export_files']['zip']['sha256'] == hashlib.sha256(package).hexdigest()
    assert store.get_for_project(pid)['status'] == store.SUCCEEDED
    # Real download routes serve the original bytes from another filesystem.
    with app.test_client() as client:
        for kind, payload in [('pdf', pdf), ('zip', package)]:
            response = client.get(p['data']['export_files'][kind]['url'])
            assert response.status_code == 200
            assert response.data == payload


@pytest.mark.parametrize('committed', [False, True])
def test_final_write_retries_with_fresh_reads_even_when_commit_ack_was_lost(saved, monkeypatch, committed):
    pid = saved[0]
    real = database.update_project
    calls = []
    def flaky(*a, **k):
        calls.append(a[2][database.ROW_VERSION_KEY])
        if len(calls) == 1:
            if committed:
                real(*a, **k)
            raise sqlite3.OperationalError('lost connection after export')
        return real(*a, **k)
    monkeypatch.setattr(database, 'update_project', flaky)
    assert recovery.recover(pid)
    assert database.get_project(pid)['data']['coloring_build']['status'] == 'complete'
    assert len(calls) == (1 if committed else 2)


def test_concurrent_customer_metadata_survives_fresh_read_retry(saved, monkeypatch):
    pid = saved[0]
    real = database.update_project
    called = []
    def conflict(*args, **kwargs):
        if not called:
            called.append(True)
            newer = database.get_project(pid)['data']
            newer['customer_note'] = 'Keep this note'
            real(pid, None, newer)
        return real(*args, **kwargs)
    monkeypatch.setattr(database, 'update_project', conflict)
    assert recovery.recover(pid)
    assert database.get_project(pid)['data']['customer_note'] == 'Keep this note'


def test_changed_revision_cannot_receive_an_old_completion_record(saved, monkeypatch):
    pid = saved[0]
    real = database.update_project
    called = []
    def conflict(*args, **kwargs):
        if not called:
            called.append(True)
            newer = database.get_project(pid)['data']
            newer['artifact_revision'] += 1
            real(pid, None, newer)
        return real(*args, **kwargs)
    monkeypatch.setattr(database, 'update_project', conflict)
    with pytest.raises(ValueError, match='changed'):
        recovery.recover(pid)
    assert not database.get_project(pid)['data'].get('export_ready')
    with pytest.raises(recovery.CompletionPending):
        recovery.recover(pid)


def test_active_builder_and_review_are_not_finalized(saved):
    pid = saved[0]
    conn = database.get_conn()
    conn.execute('UPDATE jobs SET lease_expires_at=? WHERE project_id=?', ('9999-01-01', pid))
    conn.commit()
    conn.close()
    assert not recovery.recover(pid)
    d = database.get_project(pid)['data']
    d['coloring_build']['status'] = 'review'
    database.update_project(pid, None, d)
    assert not recovery.recover(pid, under_lease=True)
    assert not database.get_project(pid)['data'].get('export_ready')


@pytest.mark.parametrize('fault', ['missing', 'corrupt', 'other_pdf', 'unapproved', 'wrong_owner'])
def test_unverifiable_package_is_preserved_and_never_claimed_finished(saved, fault):
    pid, _, _, driver = saved
    d = database.get_project(pid)['data']
    from services.storage.keys import export_object_key
    key = export_object_key(pid, d['package_id'] + '/package.zip')
    if fault == 'missing':
        driver.delete(key)
    elif fault == 'corrupt':
        driver.put(key, b'not a valid zip')
    elif fault == 'other_pdf':
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z:
            z.writestr(d['filename'], b'%PDF-other')
        assert publish_export(pid, d['package_id'] + '/package.zip', payload=raw.getvalue())
    else:
        row = database.get_asset_by_key(key)
        database.record_asset(pid + 999 if fault == 'wrong_owner' else pid, 'export_file', key,
                              byte_size=row['byte_size'], checksum=row['checksum'], approved=fault != 'unapproved')
    with pytest.raises(recovery.CompletionPending):
        recovery.recover(pid)
    assert not database.get_project(pid)['data'].get('export_ready')


def test_recovery_monitor_is_disabled_under_tests(monkeypatch):
    monkeypatch.setenv('FACTORY_TEST_MODE', '1')
    with patch.object(recovery.threading, 'Thread', side_effect=AssertionError('no background tests')):
        assert recovery.start() is False


def test_completion_receipt_binds_downloads_to_the_original_request(saved):
    pid = saved[0]
    data = database.get_project(pid)['data']
    exports = recovery._published_exports(pid, data)
    recovery.checkpoint_completion(pid, exports, recovery.identity(data))
    # A subsequent customer revision must not inherit completion for old files.
    data['fields']['age_group'] = 'Adults'
    database.update_project(pid, None, data)
    with pytest.raises(recovery.CompletionPending):
        recovery.recover(pid)
    assert not database.get_project(pid)['data'].get('export_ready')


def test_recovery_monitor_starts_once_without_dispatching_work(monkeypatch):
    monkeypatch.setenv('FACTORY_TEST_MODE', '0')
    monkeypatch.setattr(recovery, '_started', False)
    with patch.object(recovery.threading, 'Thread') as thread:
        assert recovery.start()
        assert recovery.start()
        assert thread.call_count == 1
        thread.return_value.start.assert_called_once()


def test_persistent_database_failure_is_rechecked_on_next_sweep(saved):
    pid = saved[0]
    with patch.object(database, 'update_project', side_effect=sqlite3.OperationalError('offline')) as writes:
        recovery.sweep()
        assert writes.call_count == 3
    assert not database.get_project(pid)['data'].get('export_ready')
    for _ in range(10):  # rotate past prior isolated tests' unavailable stores
        recovery.sweep()
        if database.get_project(pid)['data'].get('export_ready'):
            break
    assert database.get_project(pid)['data']['export_ready']


def test_status_checks_ownership_before_attempting_recovery(saved):
    pid = saved[0]
    with patch.object(recovery, 'recover', side_effect=AssertionError('must authorize first')):
        assert app.test_client().get(f'/coloring/build/{pid}/status').status_code == 404


def test_status_recovers_saved_package_without_a_new_workflow_task(saved):
    pid = saved[0]
    with app.test_client() as client:
        with client.session_transaction() as session:
            session['coloring_customer'] = 'owner'
        with patch('services.jobs.dispatch.hand_off', side_effect=AssertionError('no paid workflow')):
            result = client.get(f'/coloring/build/{pid}/status').get_json()
    assert result['finished'] and result['result']['export_ready']


def test_workflow_retry_uses_completed_files_without_generation_or_reexport(saved):
    from services.jobs.workflow_runner import run_build
    pid = saved[0]
    with patch('services.product.generate_product', side_effect=AssertionError('no provider')), \
         patch('services.packaging.build_product_export', side_effect=AssertionError('no exporter')):
        result = run_build(pid)
    assert result['finished']


def test_unverifiable_finished_file_cannot_fall_back_to_paid_work(saved):
    from services.coloring_book import background
    pid, _, _, driver = saved
    from services.storage.keys import export_object_key
    data = database.get_project(pid)['data']
    driver.delete(export_object_key(pid, data['package_id'] + '/package.zip'))
    with patch('services.product.generate_product', side_effect=AssertionError('no provider')):
        result = background.advance(pid)
    assert result['failed']
    assert not database.get_project(pid)['data'].get('export_ready')


def test_real_two_page_build_recovers_after_final_database_outage_and_container_loss(setup):
    import shutil
    from pathlib import Path
    from services.coloring_book import background, builder
    from services.jobs.workflow_runner import run_build
    fields = dict(FIELDS, pages='2')
    pid = begin(setup, fields)
    def plan(**kwargs):
        return {'pages': [{'topic': f'Fish {i}', 'line_art_prompt': f'Draw fish {i} in the ocean, bold black outlines, white background'} for i in range(2)]}
    real = database.update_project
    def offline_on_completion(*args, **kwargs):
        if args[2].get('export_ready'):
            raise sqlite3.OperationalError('connection lost after package publication')
        return real(*args, **kwargs)
    with patch.object(builder, 'chat_json', side_effect=plan), \
         patch.object(builder, 'generate_visual_image', side_effect=art) as provider, \
         patch.object(database, 'update_project', side_effect=offline_on_completion), \
         patch.object(recovery.time, 'sleep', return_value=None):
        with pytest.raises(sqlite3.OperationalError):
            run_build(pid)
        assert provider.call_count == 3
    data = database.get_project(pid)['data']
    assert not data.get('export_ready')
    assets = {a['storage_key']: a['checksum'] for a in database.list_assets(pid)}
    shutil.rmtree(Path(builder.EXPORTS_DIR) / data['package_id'])
    conn = database.get_conn()
    conn.execute('UPDATE jobs SET lease_expires_at=? WHERE project_id=?', ('2000-01-01', pid))
    conn.commit()
    conn.close()
    with patch('services.product.generate_product', side_effect=AssertionError('no new artwork')), \
         patch('services.packaging.build_product_export', side_effect=AssertionError('keep original PDF and ZIP')):
        assert recovery.recover(pid)
        assert run_build(pid)['finished']
    result = setup.get(f'/coloring/build/{pid}/status').get_json()
    assert result['finished']
    final = database.get_project(pid)['data']
    assert final['fields']['pages'] == '2'
    for kind in ('pdf', 'zip'):
        file = final['export_files'][kind]
        response = setup.get(file['url'])
        assert response.status_code == 200
        assert hashlib.sha256(response.data).hexdigest() == file['sha256']
    assert {a['storage_key']: a['checksum'] for a in database.list_assets(pid)} == assets
