"""Preserve and queue one owned source version without invoking a builder.

Snapshots and books each have durable uniqueness keys. If execution stops
between those writes, repeating the request reuses the snapshot and book.
"""
from .snapshot_import import prepare


class WorkerUnavailable(RuntimeError):
    pass


def preserve_and_queue(snapshots, books, project, owner, settings, *, dispatch=None):
    if not isinstance(settings, dict) or set(settings) != {
            "title", "author", "theme", "require_photos"}:
        raise ValueError("Send the title, author, design and photograph choice")
    # Validate completeness/settings before creating any recovery state.
    from .legacy_snapshot import snapshot
    spec = prepare(snapshot(project, owner), **settings)
    if dispatch is None and not books.available():
        raise WorkerUnavailable("Book processing is temporarily unavailable. Your manuscript is saved.")
    snapshots.initialize()
    snapshot_id = snapshots.save(project, owner)
    book = books.create(owner, "snapshot:" + snapshot_id, spec)
    if dispatch is not None:
        dispatch(owner, book["id"])
    return snapshot_id, book
