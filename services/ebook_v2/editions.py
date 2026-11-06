"""Owner edits create a new edition; original requests and exports stay intact."""
import time
import uuid
from .recovery import digest,encode,InputConflict
from .publishing import export_valid


def export_id(books,book):
    if book['spec'].get('source')=='ollama':
        from .topics import data
        return data(books,book)['units'].get('export')
    return book['units'][-1] if book['units'] else None


def editable(books,owner,book_id):
    book=books.get(owner,book_id)
    if book['state'] not in {'REVIEW','READY'}:raise ValueError('Finish the current edition before editing')
    unit=books.units.get(owner,export_id(books,book))
    if unit['state']!='COMPLETE' or not export_valid(unit['output']):
        raise ValueError('Verify the current edition before editing')
    source=unit['payload']['book']
    return {'id':book_id,'revision':book['revision'],
        'spec':{key:source[key] for key in ('title','author','theme','chapters')},
        'editions':history(books,owner,book_id)}


def history(books,owner,book_id):
    books.get(owner,book_id)
    with books.units.transaction() as conn:
        link=conn.execute('SELECT root_id FROM ebook_v2_editions WHERE book_id=?',(book_id,)).fetchone()
        root=link['root_id'] if link else book_id
        rows=conn.execute('''SELECT b.id,b.state,b.revision,b.created,
            coalesce(e.number,1) AS number,json_extract(b.spec,'$.title') AS title
            FROM ebook_v2_books b LEFT JOIN ebook_v2_editions e ON e.book_id=b.id
            WHERE b.owner=? AND (b.id=? OR e.root_id=?) ORDER BY number''',
            (str(owner),root,root)).fetchall()
    return [dict(row) for row in rows]


def edit(books,owner,book_id,revision,key,raw):
    from .books import clean_spec,Conflict
    if not isinstance(key,str) or not 8<=len(key)<=100:raise ValueError('Use a valid edit request key')
    parent=books.get(owner,book_id)
    if parent['spec'].get('require_photos') and isinstance(raw,dict) and 'require_photos' not in raw:
        raw={**raw,'require_photos':True}
    spec=clean_spec(raw)
    if spec.get('source')=='ollama':raise ValueError('Edits must supply the exact revised manuscript')
    request='edit:'+digest({'parent':book_id,'key':key})
    # Retry lookup precedes the revision check so a lost HTTP response is safe.
    with books.units.transaction() as conn:
        prior=conn.execute('SELECT * FROM ebook_v2_books WHERE owner=? AND request_key=?',
            (str(owner),request)).fetchone()
    if prior:
        prior=books.checked(prior)
        if prior['spec_sha']!=digest(spec):raise InputConflict('Edit request already used with different text')
        return prior
    parent=books.get(owner,book_id)
    if type(revision) is not int or revision!=parent['revision']:raise Conflict('Reload the saved edition')
    editable(books,owner,book_id)
    new_id=uuid.uuid4().hex;now=time.time()
    with books.units.transaction() as conn:
        count=conn.execute('UPDATE ebook_v2_books SET revision=revision+1 WHERE id=? AND owner=? AND revision=?',
            (book_id,str(owner),revision)).rowcount
        if count!=1:raise Conflict('This edition has newer saved changes')
        link=conn.execute('SELECT root_id FROM ebook_v2_editions WHERE book_id=?',(book_id,)).fetchone()
        root=link['root_id'] if link else book_id
        number=conn.execute('SELECT coalesce(max(number),1)+1 FROM ebook_v2_editions WHERE root_id=?',
            (root,)).fetchone()[0]
        conn.execute("INSERT INTO ebook_v2_books VALUES (?,?,?,?,?,?,'RUNNING',1,?,?)",
            (new_id,str(owner),request,encode(spec),digest(spec),'[]',now,now))
        conn.execute('INSERT INTO ebook_v2_editions VALUES (?,?,?,?,?)',
            (new_id,book_id,root,number,now))
    return books.get(owner,new_id)
