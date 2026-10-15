"""Recover a published coloring package; never generate or write artifact bytes."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sqlite3
import threading
import time
import zipfile

import database
from services.jobs import store
from services.saved_project_listing import serialized_listing

log = logging.getLogger(__name__)
_started = False
_start_lock = threading.Lock()
_cursor = 0


class CompletionPending(RuntimeError):
    """An existing finished file must not be replaced by a new build."""


def transient(exc):
    """Only connection failures and optimistic conflicts can retry a fresh read."""
    if isinstance(exc, (sqlite3.OperationalError, database.StaleProjectWrite)):
        return True
    return (type(exc).__module__.split('.')[0] in ('psycopg', 'psycopg2')
            and type(exc).__name__ in ('OperationalError', 'InterfaceError'))


def retry_metadata(operation):
    for attempt in range(3):
        try:
            return operation()
        except Exception as exc:
            if not transient(exc) or attempt == 2:
                raise
            time.sleep(0.25 * (attempt + 1))


def identity(data):
    return json.dumps({k: data.get(k) for k in (
        'package_id', 'filename', 'content_digest', 'asset_manifest_digest',
        'artifact_id', 'artifact_revision', 'fields', 'needs_approval',
        'qa_passed', 'qa_result', 'generation_stage')}, sort_keys=True)


def checkpoint_completion(pid, exports, expected_identity):
    """Small durable receipt tying the final exports to this exact request."""
    from services.storage.publish import publish_export, publishing_enabled
    if not publishing_enabled():
        return
    receipt = {'project_id': int(pid), 'identity': expected_identity,
               'pdf_sha256': exports['exports']['files']['pdf']['sha256'],
               'zip_sha256': exports['exports']['files']['zip']['sha256']}
    if not publish_export(pid, exports['package_id'] + '/coloring_completion.json',
                          payload=json.dumps(receipt, sort_keys=True).encode(),
                          kind='coloring_completion', content_type='application/json'):
        raise CompletionPending('Your finished files are preserved. Their completion receipt could not be safely saved; the Factory will check again.')


def finalize(pid, exports, expected_identity):
    """One atomic metadata save, including completion. Preserve current consent."""
    def save():
        project = database.get_project(pid)
        if not project:
            return False
        data = project['data']
        if identity(data) != expected_identity:
            raise ValueError('The saved book changed during completion; its files were kept.')
        state = data['coloring_build']
        if state.get('status') == 'complete' and data.get('export_ready'):
            return True
        data.update(product_exports=exports['exports'], export_package_id=exports['package_id'],
                    stage='export_ready', export_files=exports['exports']['files'],
                    pdf_sha256=exports['exports']['files']['pdf']['sha256'], export_ready=True)
        data['coloring_build'] = {**state, 'status': 'complete', 'message': 'Your coloring book is ready.'}
        database.update_project(pid, None, data)
        return True
    return retry_metadata(save)


def _published_exports(pid, data):
    """Require approved, readable assets and the exact original PDF inside ZIP."""
    from services.ebook_package import _PACKAGE_ID_OK, is_allowed_download
    from services.quality.artifact_identity import asset_manifest_digest
    from services.storage.compat import verified_asset_bytes
    from services.storage.keys import export_object_key

    pkg, filename = str(data.get('package_id') or ''), str(data.get('filename') or '')
    digest = str(data.get('content_digest') or '')
    if (not _PACKAGE_ID_OK(pkg) or not filename.lower().endswith('.pdf') or not is_allowed_download(filename)
            or any(x in filename for x in ('/', '\\', '..')) or len(digest) != 64):
        return None
    if (data.get('needs_approval') or data.get('quality_blocking')
            or data.get('qa_passed') is False
            or data.get('generation_stage') in ('cover_preview', 'sample_interior')):
        return None
    qa = data.get('qa_result') or {}
    if qa.get('blocked_export') or qa.get('all_passed') is False:
        return None
    if not data.get('asset_manifest_digest') or asset_manifest_digest(data) != data['asset_manifest_digest']:
        return None
    receipt_key = export_object_key(pid, pkg + '/coloring_completion.json')
    if database.get_asset_by_key(receipt_key):
        raw = verified_asset_bytes(receipt_key)
        try:
            receipt = json.loads(raw) if raw else {}
            if receipt.get('project_id') != pid or receipt.get('identity') != identity(data):
                return None
        except (ValueError, TypeError):
            return None
    else:
        # Pre-receipt builds are recoverable only for their first stamped
        # revision with the original page count, such as the interrupted live
        # build. A later revision must carry its own completion receipt.
        receipt = None
        if data.get('artifact_revision') != 1:
            return None
        pages = data.get('pages')
        if not isinstance(pages, list) or str((data.get('fields') or {}).get('pages')) != str(len(pages)):
            return None
    records = {}
    for name in (filename, 'package.zip'):
        key = export_object_key(pid, pkg + '/' + name)
        row = database.get_asset_by_key(key)
        if not row or not row.get('approved') or row.get('project_id') != pid:
            return None
        if int(row.get('byte_size') or 0) > 64 * 1024 * 1024:
            return None
        records[name] = row
    # Do not load either large object when the recorded PDF belongs to a
    # different revision. Never fall back to an unverified local export.
    if records[filename]['checksum'] != digest:
        return None
    if receipt and (receipt.get('pdf_sha256') != digest
                    or receipt.get('zip_sha256') != records['package.zip']['checksum']):
        return None
    pdf = verified_asset_bytes(records[filename]['storage_key'])
    if not pdf or not pdf.startswith(b'%PDF') or hashlib.sha256(pdf).hexdigest() != digest:
        return None
    del pdf
    package = verified_asset_bytes(records['package.zip']['storage_key'])
    if not package:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            entries = archive.infolist()
            if (len(entries) > 1000 or sum(e.file_size for e in entries) > 512 * 1024 * 1024
                    or archive.namelist().count(filename) != 1):
                return None
            # Reading every member checks its CRC, without extracting anything.
            for entry in entries:
                member_digest = hashlib.sha256()
                with archive.open(entry) as member:
                    for chunk in iter(lambda: member.read(65536), b''):
                        member_digest.update(chunk)
                if entry.filename == filename and member_digest.hexdigest() != digest:
                    return None
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        return None
    files = {}
    for kind, name in (('pdf', filename), ('zip', 'package.zip')):
        files[kind] = {'name': name, 'url': f'/download/{pkg}/{name}',
                       'sha256': records[name]['checksum']}
    return {'package_id': pkg, 'exports': {'pdf_available': True, 'files': files,
            'meta': {'package_id': pkg, 'artifact_id': data.get('artifact_id'),
                     'artifact_revision': data.get('artifact_revision'), 'content_digest': digest}}}


@serialized_listing
def recover(pid, *, under_lease=False):
    """Metadata-only recovery; active builders keep exclusive ownership."""
    project = database.get_project(int(pid))
    if not project or not isinstance(project['data'].get('coloring_build'), dict):
        return False
    data = project['data']
    if data['coloring_build'].get('status') == 'review':
        return False
    if data['coloring_build'].get('status') == 'complete' and data.get('export_ready'):
        return True
    job = store.get_for_project(int(pid))
    if (not under_lease and job and job['status'] == store.RUNNING
            and str(job.get('lease_expires_at') or '') > store._now()):
        return False
    exports = _published_exports(int(pid), data)
    if exports is None:
        from services.storage.keys import export_object_key
        from services.ebook_package import _PACKAGE_ID_OK
        pkg, name = str(data.get('package_id') or ''), str(data.get('filename') or '')
        if _PACKAGE_ID_OK(pkg) and name and not any(x in name for x in ('/', '\\', '..')):
            if any(database.get_asset_by_key(export_object_key(int(pid), pkg + '/' + file))
                   for file in (name, 'package.zip')):
                raise CompletionPending('Your existing files are preserved. The Factory is checking the finished package before reconnecting it; no new artwork was requested.')
        return False
    expected_identity = identity(data)
    del data, project  # Release the large embedded preview before the fresh save.
    result = finalize(int(pid), exports, expected_identity)
    if result:
        log.info('Recovered existing coloring package for project %s; no generation or artifact writes', pid)
    return result


def sweep():
    """Bounded, rotating scan of expired/failed jobs; never dispatch work."""
    global _cursor
    conn = database.get_conn()
    try:
        rows = conn.execute(
            'SELECT p.id FROM projects p JOIN jobs j ON j.project_id=p.id '
            'WHERE p.id>? AND p.type=? AND j.kind=? '
            'AND (j.status=? OR (j.status=? AND j.lease_expires_at<=?)) '
            'AND p.data LIKE ? ORDER BY p.id LIMIT 10',
            (_cursor, 'product', store.KIND_EBOOK_BUILD, store.FAILED, store.RUNNING,
             store._now(), '%"coloring_build"%')).fetchall()
    finally:
        conn.close()
    if not rows:
        _cursor = 0
    for row in rows:
        pid = int(row['id'])
        _cursor = pid
        try:
            if not recover(pid):
                continue
            # Reconcile a lost finish ACK too. Never steal a current lease.
            conn = database.get_conn()
            try:
                conn.execute('UPDATE jobs SET status=?, lease_owner=\'\', lease_expires_at=\'\', '
                             'last_error=\'\', updated_at=? WHERE project_id=? AND kind=? '
                             'AND (status=? OR (status=? AND lease_expires_at<=?))',
                             (store.SUCCEEDED, store._now(), pid, store.KIND_EBOOK_BUILD,
                              store.FAILED, store.RUNNING, store._now()))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            log.exception('Completion recovery will check project %s again', pid)


def start():
    global _started
    if os.environ.get('FACTORY_TEST_MODE', '').lower() in ('1', 'true', 'yes'):
        return False
    with _start_lock:
        if _started:
            return True
        def loop():
            while True:
                try:
                    sweep()
                except Exception:
                    log.exception('Completion recovery check postponed')
                time.sleep(60)
        threading.Thread(target=loop, name='factory-completion-recovery', daemon=True).start()
        _started = True
        return True
