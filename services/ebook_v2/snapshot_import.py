"""Prepare an immutable saved manuscript for the existing Studio workflow."""
from .books import clean_spec


def prepare(snapshot, *, title, author, theme, require_photos=True):
    workspace = snapshot["data"].get("ebook_workspace")
    if not isinstance(workspace, dict):
        raise ValueError("This saved book has no chapter workspace")
    pipeline = workspace.get("chapter_pipeline")
    chapters = workspace.get("accepted_chapters")
    if (not isinstance(pipeline, dict) or pipeline.get("assembled_complete") is not True
            or not isinstance(chapters, list) or not 2 <= len(chapters) <= 20):
        raise ValueError("This saved manuscript still needs chapters before it can be exported")
    by_order = {}
    for chapter in chapters:
        if not isinstance(chapter, dict) or type(chapter.get("order")) is not int:
            raise ValueError("Saved chapter order is missing")
        order = chapter["order"]
        if order in by_order:
            raise ValueError("Saved chapter order contains duplicates")
        by_order[order] = {"title": chapter.get("title"), "text": chapter.get("body")}
    if set(by_order) != set(range(1, len(chapters) + 1)):
        raise ValueError("Saved chapter order has gaps")
    raw = {"title": title, "author": author, "theme": theme,
           "require_photos": require_photos,
           "chapters": [by_order[order] for order in sorted(by_order)]}
    return clean_spec(raw)


def import_saved_book(snapshots, books, owner, snapshot_id, **settings):
    """Queue a separate Studio book from a verified owner-scoped snapshot."""
    snapshot = snapshots.reopen(owner, snapshot_id)
    spec = prepare(snapshot, **settings)
    return books.create(owner, "snapshot:" + snapshot_id, spec)
