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


def compact_list_item(project):
    if project.get('type') not in ('ebook', 'product'):
        return project
    out = dict(project)
    data = dict(project.get('data') or {})
    for key in ('pdf_bytes', 'preview_html', 'ebook_preview_html', 'content',
                'ebook', 'cover_preview_b64', 'sample_preview_b64'):
        if key in data:
            data[key] = ''
    out['data'] = data
    out['_list_summary'] = True
    return out
