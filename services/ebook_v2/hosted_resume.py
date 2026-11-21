"""One explicit retry of a saved manuscript after its prior task has stopped."""
import time

from .books import Conflict
from .recovery_handoff import WorkerUnavailable


def initialize(books):
    with books.units.transaction() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS ebook_v2_resume_dispatch (
            book_id TEXT NOT NULL REFERENCES ebook_v2_books(id),
            revision INTEGER NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL,
            run_id TEXT NOT NULL, created DOUBLE PRECISION NOT NULL,
            applied INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(book_id,revision))''')


def previous_run(books,owner,book_id):
    with books.units.transaction() as conn:
        row=conn.execute('''SELECT state,run_id FROM ebook_v2_resume_dispatch
            WHERE book_id=? AND owner=? ORDER BY revision DESC LIMIT 1''',
            (book_id,str(owner))).fetchone()
        if row is None:
            row=conn.execute('SELECT state,run_id FROM ebook_v2_dispatch WHERE book_id=? AND owner=?',
                             (book_id,str(owner))).fetchone()
    return dict(row) if row else None


def pending(books, owner, book_id, revision):
    with books.units.transaction() as conn:
        row = conn.execute('''SELECT state FROM ebook_v2_resume_dispatch
            WHERE book_id=? AND revision=? AND owner=?''',
            (book_id, revision, str(owner))).fetchone()
    return row['state'] if row else None


def terminal(run_id):
    from render import Render
    return Render().workflows.get_task_run(run_id).status.value in {
        'completed','succeeded','failed','canceled'}


def start(task,owner,book_id,revision):
    from render import Render
    return str(Render().workflows.start_task(task,[str(owner),book_id,revision]).id)


def queue(dispatch,owner,book_id,revision,*,finished=terminal,submit=start):
    books=dispatch.books
    book=books.get(owner,book_id)
    dispatch.validate(book)
    if type(revision) is not int or revision<1:raise ValueError('Reload the saved book.')
    initialize(books)
    with books.units.transaction() as conn:
        prior=conn.execute('''SELECT state FROM ebook_v2_resume_dispatch
            WHERE book_id=? AND revision=? AND owner=?''',(book_id,revision,str(owner))).fetchone()
    if prior:
        if prior['state']=='UNKNOWN':
            raise WorkerUnavailable('Your saved work is safe. The previous submission needs checking before another run.')
        return
    if book['revision']!=revision:raise Conflict('Reload the saved book before resuming.')
    if book['state']!='NEEDS_ATTENTION':raise ValueError('This book is not waiting to resume.')
    previous=previous_run(books,owner,book_id)
    if not previous or previous['state']!='SUBMITTED' or not previous['run_id']:
        raise WorkerUnavailable('The previous processing submission needs checking before another run.')
    try:stopped=finished(previous['run_id'])
    except Exception:
        raise WorkerUnavailable('Could not check the previous run. Your saved work is safe.') from None
    if not stopped:raise WorkerUnavailable('The previous run is still active. Refresh progress shortly.')
    with books.units.transaction() as conn:
        current=conn.execute('SELECT revision,state FROM ebook_v2_books WHERE id=? AND owner=?',
                             (book_id,str(owner))).fetchone()
        if current is None:raise LookupError('Book not found')
        if current['revision']!=revision:raise Conflict('Reload the saved book before resuming.')
        if current['state']!='NEEDS_ATTENTION':raise ValueError('This book is not waiting to resume.')
        claimed=conn.execute('''INSERT INTO ebook_v2_resume_dispatch
            (book_id,revision,owner,state,run_id,created) VALUES (?,?,?,'SUBMITTING','',?)
            ON CONFLICT(book_id,revision) DO NOTHING''',(book_id,revision,str(owner),time.time())).rowcount
    if not claimed:return
    try:
        run_id=submit(dispatch.task,str(owner),book_id,revision)
        if not run_id:raise ValueError('Missing run identity')
    except Exception:
        with books.units.transaction() as conn:
            conn.execute("UPDATE ebook_v2_resume_dispatch SET state='UNKNOWN' WHERE book_id=? AND revision=?",
                         (book_id,revision))
        raise WorkerUnavailable('Your saved work is safe. The processing submission needs checking before another run.') from None
    with books.units.transaction() as conn:
        conn.execute("UPDATE ebook_v2_resume_dispatch SET state='SUBMITTED',run_id=? WHERE book_id=? AND revision=?",
                     (run_id,book_id,revision))


def apply(books,owner,book_id,revision):
    """A retried task never resets the same saved revision twice."""
    from .workflow_recovery import Dispatch
    book=books.get(owner,book_id)
    Dispatch.validate(book)
    with books.units.transaction() as conn:
        row=conn.execute('''SELECT applied,state FROM ebook_v2_resume_dispatch
            WHERE book_id=? AND revision=? AND owner=?''',(book_id,revision,str(owner))).fetchone()
    if row is None or row['state'] not in {'SUBMITTING','SUBMITTED'}:
        raise ValueError('This saved revision has no resume request.')
    if row['applied']:return
    if book['revision']==revision:
        try:
            books.resume(owner,book_id,revision)
        except Conflict:
            if books.get(owner,book_id)['revision'] <= revision:
                raise
    elif book['revision']<revision:
        raise Conflict('The saved revision does not match this resume request.')
    # A process may exit after Books.resume commits but before this marker.
    # Later retries retain its newer checkpoints instead of resetting again.
    with books.units.transaction() as conn:
        conn.execute('UPDATE ebook_v2_resume_dispatch SET applied=1 WHERE book_id=? AND revision=? AND owner=?',
                     (book_id,revision,str(owner)))
