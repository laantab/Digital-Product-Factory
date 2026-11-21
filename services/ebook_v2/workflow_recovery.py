"""On-demand saved-manuscript execution on the existing Render workflow.

A durable submission claim precedes the network request. An ambiguous failure
is retained for reconciliation, never automatically submitted a second time.
"""
import time

from .books import Conflict
from .recovery_handoff import WorkerUnavailable


class Dispatch:
    def __init__(self, books, task, start=None):
        self.books, self.task = books, task
        self.start = start or self._start

    @staticmethod
    def _start(task, owner, book_id):
        from render import Render
        return str(Render().workflows.start_task(task, [str(owner), book_id]).id)

    def initialize(self):
        with self.books.units.transaction() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS ebook_v2_dispatch (
                book_id TEXT PRIMARY KEY REFERENCES ebook_v2_books(id),
                owner TEXT NOT NULL, state TEXT NOT NULL, run_id TEXT NOT NULL,
                created DOUBLE PRECISION NOT NULL)''')
        from .hosted_resume import initialize
        initialize(self.books)

    def resume(self,owner,book_id,revision):
        from .hosted_resume import queue
        queue(self,owner,book_id,revision)

    @staticmethod
    def validate(book):
        if book['spec'].get('source') == 'ollama':
            raise ValueError('Hosted recovery accepts saved manuscripts only')

    def __call__(self, owner, book_id):
        book = self.books.get(owner, book_id)
        self.validate(book)
        if book['state'] != 'RUNNING':
            return
        with self.books.units.transaction() as conn:
            prior = conn.execute('SELECT state FROM ebook_v2_dispatch WHERE book_id=? AND owner=?',
                                 (book_id, str(owner))).fetchone()
            if prior:
                if prior['state'] == 'UNKNOWN':
                    raise WorkerUnavailable('Your manuscript is saved. Processing submission needs checking before another run can start.')
                return
            conn.execute('INSERT INTO ebook_v2_dispatch VALUES (?,?,\'SUBMITTING\',\'\',?)',
                         (book_id, str(owner), time.time()))
        try:
            run_id = self.start(self.task, str(owner), book_id)
            if not run_id:
                raise ValueError('Missing workflow run identity')
        except Exception as exc:
            with self.books.units.transaction() as conn:
                conn.execute("UPDATE ebook_v2_dispatch SET state='UNKNOWN' WHERE book_id=?", (book_id,))
            raise WorkerUnavailable('Your manuscript is saved. Processing submission needs checking before another run can start.') from exc
        with self.books.units.transaction() as conn:
            conn.execute("UPDATE ebook_v2_dispatch SET state='SUBMITTED',run_id=? WHERE book_id=?",
                         (run_id, book_id))


def run_saved_book(services, owner, book_id, *, budget=600, clock=time.monotonic, pause=time.sleep):
    """Resume one owned book, never scan or generate other customers' work."""
    from .shared_work_files import restore
    books, artifacts = services['books'], services['artifacts']
    book = books.get(owner, book_id)
    if book['spec'].get('source') == 'ollama' or not book['request_key'].startswith('snapshot:'):
        raise ValueError('Choose a preserved saved manuscript')
    deadline = clock() + budget
    while True:
        book = books.get(owner, book_id)
        if book['state'] in ('REVIEW', 'READY'):
            unit = books.units.get(owner, book['units'][-1])
            restore(books.root, unit['output'], artifacts.storage)
            with books.units.transaction() as conn:
                published = conn.execute('SELECT 1 FROM ebook_v2_artifacts WHERE book_id=? AND owner=?',
                                         (book_id, str(owner))).fetchone()
            if not published:
                # Publishing requires REVIEW; READY already has a verified receipt.
                artifacts.publish(owner, book_id)
            return {'book_id': book_id, 'state': book['state'], 'files': ['ebook.pdf', 'package.zip']}
        if book['state'] != 'RUNNING':
            return {'book_id': book_id, 'state': book['state'], 'files': []}
        if clock() >= deadline:
            raise RuntimeError('Saved book requires continuation from its durable checkpoints')
        try:
            books.advance(owner, book_id)
        except Conflict:
            pass
        pause(0.1)


def register(app, *, plan, retry):
    @app.task(timeout_seconds=900, plan=plan, retry=retry)
    def recover_saved_ebook(ctx, owner: str, book_id: str, resume_revision: int | None=None) -> dict:
        from .hosted_runtime import configured_services, initialize
        services = configured_services()
        initialize(services)
        if resume_revision is not None:
            from .hosted_resume import apply
            apply(services['books'],owner,book_id,resume_revision)
        return run_saved_book(services, owner, book_id)
    return recover_saved_ebook
