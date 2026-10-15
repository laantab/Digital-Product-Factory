"""Durable coloring builds on the existing leased Workflow executor.

No new service, schema or credentials. The website records an intention only.
Artwork is published before the next paid request; ambiguous interrupted calls
stop rather than automatically charging for a replacement.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextvars import ContextVar
from pathlib import Path

import database
from services.jobs import mode, store

class ColoringCheckpointError(RuntimeError):
    pass


_active = ContextVar('coloring_background_project', default=None)


def _change(pid, **changes):
    project = database.get_project(pid)
    data = project['data']
    data['coloring_build'].update(changes)
    database.update_project(pid, None, data)
    return data


def start(fields, customer):
    fields = dict(fields)
    from services.coloring_book.prompt_engine import resolve_coloring_book_author
    from services.ebook_package import _PACKAGE_ID_OK
    from services.quality.user_instruction_controller import build_coloring_book_contract
    build_coloring_book_contract(fields)
    raw_count = str(fields.get('pages') if fields.get('pages') is not None else '').strip()
    try:
        requested = int(raw_count) if raw_count else None
    except ValueError:
        requested = None
    # Validate before handing off; small previews must never expand into
    # additional paid artwork. One page retains the existing Single Sheet rule.
    if raw_count and (requested is None or not 1 <= requested <= 100):
        raise ValueError('Enter a whole number from 1 to 100 coloring pages. Small previews, such as 2 pages, are supported.')
    if not str(fields.get('theme') or fields.get('coloring_title') or '').strip():
        raise ValueError('Enter a theme for your coloring book.')
    if fields.get('package_id') and not _PACKAGE_ID_OK(str(fields['package_id'])):
        raise ValueError('Invalid coloring package.')
    key = hashlib.sha256(json.dumps([customer, fields], sort_keys=True).encode()).hexdigest()
    request_kind = 'coloring_request:' + key
    store.init_jobs_table()
    conn = database.get_conn()
    try:
        # Cross-process serialization, covering both the lookup and both inserts.
        if database._use_postgres():
            lock = int(key[:16], 16) - (1 << 63)
            conn.execute('SELECT pg_advisory_xact_lock(?)', (lock,))
        else:
            conn.execute('BEGIN IMMEDIATE')
        prior = conn.execute('SELECT project_id FROM jobs WHERE kind=?', (request_kind,)).fetchone()
        if prior:
            pid = prior['project_id']
        else:
            pkg = str(fields.get('package_id') or uuid.uuid4().hex)
            title = str(fields.get('coloring_title') or fields.get('product_title') or fields.get('theme'))[:200]
            source_pid = None
            if fields.get('package_id'):
                # Only reuse a package recorded for this customer. Old inline
                # previews continue inline; new workflow previews carry a project.
                source_hint = fields.get('_coloring_source_project_id')
                old = database.get_project(int(source_hint)) if source_hint else None
                d = old['data'] if old else {}
                if d.get('package_id') == pkg and (d.get('coloring_build') or {}).get('customer') == customer:
                    source_pid = old['id']
                if source_pid is None:
                    raise ValueError('Open the saved coloring preview before continuing this package.')
            if str(fields.get('force_image_regen') or '').lower() in ('true', '1', 'yes'):
                pkg = uuid.uuid4().hex
                source_pid = None
            fields['package_id'] = pkg
            fields.pop('reference_image_path', None)  # local builder paths are restored from verified assets
            data = {'product_type': 'coloring_book', 'title': title, 'fields': fields,
                    'package_id': pkg, 'artifact_state': 'DRAFT', 'artifact_revision': 1,
                    'author_brand': resolve_coloring_book_author(fields.get('author_brand'), fields.get('author')),
                    'coloring_build': {'customer': customer, 'idempotency_key': key, 'status': 'queued',
                        'message': 'Your coloring book is queued.', 'completed_images': [], 'pending_image': '',
                        'source_project_id': source_pid, 'plan': ((database.get_project(source_pid)['data'].get('coloring_build') or {}).get('plan') if source_pid else None)}}
            now = database._now()
            cur = conn.execute('INSERT INTO projects (name,type,data,user_saved,system_test,temporary,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                               (title, 'product', database._encode_project_data(data), 0, 0, 0, now, now))
            pid = cur.lastrowid
            conn.execute('INSERT INTO jobs (project_id,kind,status,created_at,updated_at) VALUES (?,?,?,?,?)',
                         (pid, request_kind, store.SUCCEEDED, now, now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    project = database.get_project(pid)
    if project['data']['coloring_build']['status'] not in ('complete', 'review', 'failed'):
        from services.jobs.dispatch import hand_off
        dispatched = hand_off(pid)
        if not dispatched.get('triggered') and not store.trigger_info(pid).get('workflow_run_id'):
            _change(pid, status='failed', message='The background builder could not start. Your request is saved; Continue saved build will retry the handoff.')
    return status(pid, customer)


def status(pid, customer=None):
    project = database.get_project(int(pid))
    if not project or not isinstance(project['data'].get('coloring_build'), dict):
        raise ValueError('Coloring build not found.')
    data = project['data']
    state = data['coloring_build']
    if customer is not None and state.get('customer') != customer:
        raise ValueError('Coloring build not found.')
    out = {'coloring_build': True, 'project_id': int(pid), 'status': state['status'],
           'message': state['message'], 'completed_images': len(state.get('completed_images') or []),
           'finished': state['status'] in ('complete', 'review'), 'failed': state['status'] == 'failed'}
    job = store.get_for_project(int(pid))
    if not out['finished'] and not out['failed'] and job and job['status'] == store.RUNNING and str(job.get('lease_expires_at') or '') <= store._now():
        out.update(failed=True, status='interrupted', message='The builder stopped. Continue from your saved artwork.')
    if out['finished']:
        # Small response: binaries already live in verified export storage.
        result = {k: v for k, v in data.items() if k not in ('pdf_bytes', 'cover_preview_b64', 'sample_preview_b64', 'coloring_build', database.ROW_VERSION_KEY)}
        result['_project_id'] = int(pid)
        result['_workflow_save_pending'] = True
        from services.coloring_book.preview_assets import attach_coloring_preview_urls
        out['result'] = attach_coloring_preview_urls(result, project_id=int(pid))
        from services.storage.keys import export_object_key
        for preview in result.get('interior_previews', []):
            asset = database.get_asset_by_key(export_object_key(int(pid), data['package_id'] + '/' + preview['filename']))
            if asset and asset.get('approved'):
                preview['missing'] = False
        cover = database.get_asset_by_key(export_object_key(int(pid), data['package_id'] + '/cover_page_preview.png'))
        if cover and cover.get('approved'):
            result['cover_preview_missing'] = False
    return out


def planner(raw=None):
    pid = _active.get()
    if pid is None:
        return None
    state = database.get_project(pid)['data']['coloring_build']
    if raw is None:
        return state.get('plan')
    try:
        _change(pid, plan=raw, message='Planning your coloring pages.')
    except Exception as exc:
        raise ColoringCheckpointError('The page plan could not be safely saved.') from exc
    return raw


def _restore(pid, path):
    from services.storage.compat import read_export_or_legacy
    from services.coloring_book.builder import EXPORTS_DIR
    rel = os.path.relpath(path, EXPORTS_DIR).replace(os.sep, '/')
    payload = read_export_or_legacy(pid, rel)
    if payload:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(payload)
        return True
    return False


def image_call(path, generate):
    pid = _active.get()
    if pid is None:
        return generate()
    name = Path(path).name
    state = database.get_project(pid)['data']['coloring_build']
    if not Path(path).is_file():
        _restore(pid, path)
        if not Path(path).is_file() and state.get('source_project_id'):
            _restore(state['source_project_id'], path)
    if name in state.get('completed_images', []) and not Path(path).is_file():
        raise RuntimeError('Saved artwork is temporarily unavailable. No replacement was charged.')
    if state.get('pending_image') == name and not Path(path).is_file():
        raise RuntimeError('The last artwork request was interrupted. It needs review before another paid request.')
    if not Path(path).is_file():
        _change(pid, pending_image=name, message=f'Creating {name}. Completed artwork is saved.')
        if not generate():
            # Explicit provider failure: stop, do not automatically retry paid work.
            raise RuntimeError('Artwork generation failed. Completed pages are saved; no automatic paid retry.')
    from services.storage.publish import publish_file
    from services.coloring_book.builder import EXPORTS_DIR
    if not publish_file(pid, EXPORTS_DIR, path, content_type='image/png'):
        raise RuntimeError('Artwork was created but could not be safely saved. No further images were requested.')
    completed = list(state.get('completed_images') or [])
    if name not in completed:
        completed.append(name)
    _change(pid, pending_image='' if state.get('pending_image') in ('', name) else state.get('pending_image', ''), completed_images=completed,
            message=f'Saved {len(completed)} artwork image(s).')
    return True


def advance(pid):
    project = database.get_project(pid)
    data = project['data']
    state = data['coloring_build']
    if state['status'] in ('complete', 'review', 'failed'):
        return status(pid)
    _change(pid, status='running', message='Creating your coloring book in the background.')
    token = _active.set(pid)
    try:
        from services.product import generate_product
        from services.quality.artifact_identity import stamp_artifact_identity
        result = generate_product('coloring_book', dict(data['fields']))
        stamp_artifact_identity(result)
        result['artifact_state'] = 'DRAFT'
        # Publish one file at a time, including source artwork and print-ready
        # images. Workflow disks disappear; storage is the checkpoint authority.
        from services.coloring_book.builder import EXPORTS_DIR
        from services.storage.publish import publish_file
        folder = Path(EXPORTS_DIR) / data['package_id']
        for path in sorted(folder.rglob('*')):
            if path.is_file() and not publish_file(pid, EXPORTS_DIR, path):
                raise RuntimeError('Your files could not be safely saved. Completed artwork is preserved.')
        fresh = database.get_project(pid)['data']
        fresh.update(result)
        database.update_project(pid, None, fresh)
        review = bool(result.get('needs_approval'))
        if not review:
            from services.packaging import build_product_export
            exports = build_product_export(database.get_project(pid))
            for path in sorted(folder.rglob('*')):
                if path.is_file() and not publish_file(pid, EXPORTS_DIR, path):
                    raise RuntimeError('The finished package could not be safely saved.')
            fresh = database.get_project(pid)['data']
            fresh['product_exports'] = exports['exports']
            fresh['export_package_id'] = exports['package_id']
            fresh['stage'] = 'export_ready'
            fresh['export_files'] = exports['exports']['files']
            fresh['pdf_sha256'] = exports['exports']['files']['pdf']['sha256']
            fresh['export_ready'] = True
            database.update_project(pid, None, fresh)
        _change(pid, status='review' if review else 'complete', message='Ready for your review.' if review else 'Your coloring book is ready.')
        return status(pid)
    except Exception as exc:
        _change(pid, status='failed', message=str(exc)[:500])
        return status(pid)
    finally:
        _active.reset(token)


def run_build(pid):
    from services.jobs.executor import _advance_under_lease
    from services.jobs.workflow_runner import builder_version
    existing = store.get_for_project(pid)
    if existing and existing['status'] == store.SUCCEEDED:
        return status(pid)
    job = store.claim_for_project(store.executor_id(), pid)
    if not job:
        return {'claimed': False, 'project_id': pid}
    owner = job['lease_owner']
    store.record_builder_version(job['id'], builder_version())
    out, lost = _advance_under_lease(job, owner, advance, pid)
    if lost:
        return {'lease_lost': True, 'project_id': pid}
    store.finish(job['id'], owner, status=store.FAILED if out['failed'] else store.SUCCEEDED)
    return out
