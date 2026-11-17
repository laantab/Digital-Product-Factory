"""Explicit shared-state web binding and an independent recovery worker.

The worker accepts saved manuscripts only. It never starts a text model.
"""
import os
import uuid
from pathlib import Path
from threading import Event, Thread

from .books import Books, Conflict
from .shared_artifacts import SharedArtifacts


def configure(app):
    if os.environ.get('FACTORY_V2_HOSTED_RECOVERY') != '1':
        return None
    existing = app.extensions.get('ebook_v2_hosted')
    if existing:
        return existing
    services = configured_services()
    app.extensions['ebook_v2_hosted'] = services
    return services


def configured_services():
    from services.storage.r2 import R2Driver
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ValueError('Hosted recovery requires PostgreSQL')
    root = os.environ.get('FACTORY_V2_WORK_DIR', '')
    if not root or not Path(root).is_absolute():
        raise ValueError('Hosted recovery requires an absolute worker directory')
    books = Books(Path(root)/'unused.sqlite', Path(root)/'objects', postgres_url=url)
    from .shared_work_files import install
    install(books)
    storage = R2Driver()
    return {'books': books, 'artifacts': SharedArtifacts(books, storage)}


def initialize(services):
    services['books'].initialize()
    services['artifacts'].initialize()


def tick(services):
    """One bounded pass; completed chapters are reused by the existing queue."""
    books, artifacts = services['books'], services['artifacts']
    with books.units.transaction() as conn:
        candidates = [dict(r) for r in conn.execute('''SELECT b.id,b.owner,b.state
            FROM ebook_v2_books b LEFT JOIN ebook_v2_artifacts a ON a.book_id=b.id
            WHERE b.state='RUNNING' OR (b.state='REVIEW' AND a.book_id IS NULL)
            ORDER BY b.created LIMIT 20''')]
    outcomes = []
    for row in candidates:
        try:
            book = books.get(row['owner'], row['id'])
            if book['spec'].get('source') == 'ollama':
                continue
            if book['state'] == 'RUNNING':
                book = books.advance(row['owner'], row['id'])
            if book['state'] == 'REVIEW':
                from .shared_work_files import restore
                unit = books.units.get(row['owner'], book['units'][-1])
                restore(books.root, unit['output'], artifacts.storage)
                artifacts.publish(row['owner'], row['id'])
            outcomes.append({'id':book['id'], 'state':book['state']})
        except Conflict:
            continue
    return outcomes


def run(services, stop=None):
    stop = stop or Event()
    books = services['books']
    worker_id = uuid.uuid4().hex
    def heartbeat():
        while not stop.is_set():
            books.record_worker(worker_id, local_text=False)
            stop.wait(3)
    monitor = Thread(target=heartbeat, daemon=True)
    monitor.start()
    try:
        while not stop.is_set():
            tick(services)
            stop.wait(1)
    finally:
        stop.set()
        monitor.join(4)
        with books.units.transaction() as conn:
            conn.execute('DELETE FROM ebook_v2_workers WHERE id=?', (worker_id,))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('init','worker'))
    args = parser.parse_args()
    services = configured_services()
    initialize(services)
    if args.action == 'worker':
        run(services)


if __name__ == '__main__':
    main()
