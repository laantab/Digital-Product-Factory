"""Bound concurrent list reads; never alter stored products or export files."""
from functools import wraps
from threading import RLock

_lock = RLock()


def serialized_listing(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        # Production has one threaded web worker. Avoid several simultaneous
        # full-artifact validations consuming its 512 MiB memory allowance.
        with _lock:
            return function(*args, **kwargs)
    return guarded


_LIST_FIELDS = (
    'title', 'name', 'product_type', 'product_label', 'status', 'stage',
    'author_name', 'author', 'author_brand', 'artifact_state', 'artifact_id',
    'artifact_revision', 'revision', 'export_package_id', 'package_id',
    'ebook_ready', 'export_ready', 'pdf_available', 'zip_available',
    'release_status', 'status_label', 'next_action', 'customer_keep',
    'user_saved', 'user_confirmed_save', '_saved_at', 'system_test',
    'temporary', 'validation_only', 'archived', 'hidden_from_customer',
    'internal_record', 'quality_blocking', 'launch_package_generated',
)


def _metadata(source, names):
    """Copy only bounded scalar metadata, never nested content or images."""
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in names if key in source
            and (source[key] is None or isinstance(source[key], (bool, int, float))
                 or isinstance(source[key], str) and len(source[key]) <= 8192)}


def _export_links(source):
    if not isinstance(source, dict):
        return {}
    files = source.get('files')
    files = files if isinstance(files, dict) else {}
    summary = _metadata(source, ('package_id', 'artifact_id', 'pdf_available', 'zip_available'))
    summary['files'] = {kind: _metadata(files[kind], ('url', 'name', 'filename', 'kind', 'size', 'sha256'))
                        for kind in ('pdf', 'zip') if isinstance(files.get(kind), dict)}
    return summary


def compact_list_item(project):
    if project.get('type') not in ('ebook', 'product'):
        return project
    out = dict(project)
    source = project.get('data') or {}
    data = _metadata(source, _LIST_FIELDS)
    # List rows only need author/package metadata and existing download links.
    # Open fetches the unchanged full record. Copying the rest of the nested
    # document, cover variants and edit history can send megabytes per row.
    if isinstance(source.get('fields'), dict):
        data['fields'] = _metadata(source['fields'], ('author_brand', 'author', 'package_id'))
    for key in ('exports', 'product_exports'):
        if key in source:
            data[key] = _export_links(source[key])
    if source.get('ebook_project_workspace'):
        data['ebook_project_workspace'] = True
    if source.get('ebook_workspace'):
        data['ebook_workspace'] = _metadata(source['ebook_workspace'], ('next_action',))
        # Preserve workspace presence for the existing download eligibility rule.
        data['ebook_workspace'].setdefault('next_action', '')
    if isinstance(source.get('cover_design'), dict):
        data['cover_design'] = _metadata(source['cover_design'], ('author',))
    if '_launch_package' in source:
        data['_launch_package'] = bool(source['_launch_package'])
    for key in ('pdf_bytes', 'preview_html', 'ebook_preview_html', 'content',
                'ebook', 'cover_preview_b64', 'sample_preview_b64'):
        if key in source:
            data[key] = ''
    out['data'] = data
    out['_list_summary'] = True
    return out
