"""Approve only the exact shared review edition; never invoke a worker."""
import hashlib
import io
import json
import zipfile

from .books import Conflict
from .publishing import inspect
from .recovery import CorruptCheckpoint


def approve(books,artifacts,owner,book,revision,*,recheck_owner=None):
    if type(revision) is not int or revision!=book['revision']:
        raise Conflict('This book has newer saved changes. Reload before reviewing it.')
    if book['state']!='REVIEW':raise ValueError('This edition is not waiting for review.')
    if book['spec'].get('source')=='ollama':
        from .topics import data
        export_id=data(books,book)['units']['export']
    else:export_id=book['units'][-1]
    unit=books.units.get(owner,export_id)
    if unit['stage']!='export' or unit['state']!='COMPLETE':
        raise ValueError('The completed review files are not ready.')
    output=unit['output']
    pdf,_=artifacts.download(owner,book['id'],'ebook.pdf',preview=True)
    package,_=artifacts.download(owner,book['id'],'package.zip',preview=True)
    for name,body in [('ebook.pdf',pdf),('package.zip',package)]:
        expected=output['files'][name]
        if len(body)!=expected['size'] or hashlib.sha256(body).hexdigest()!=expected['sha256']:
            raise CorruptCheckpoint('Shared review files do not match the saved edition.')
    integrity=inspect(pdf,package)
    if integrity!=output['integrity']:raise CorruptCheckpoint('Review file verification failed.')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for name,expected in output['files'].items():
            if name=='package.zip':continue
            body=archive.read(name)
            if len(body)!=expected['size'] or hashlib.sha256(body).hexdigest()!=expected['sha256']:
                raise CorruptCheckpoint('A packaged edition file failed verification.')
        if 'page_quality' in output:
            report=output['page_quality']
            if (json.loads(archive.read('quality-report.json'))!=report
                    or report.get('pdf_sha256')!=integrity['pdf_sha256']
                    or report.get('pages')!=integrity['pages']):
                raise CorruptCheckpoint('The page review does not match this edition.')
    # CAS preserves the revision checked before reading shared objects. Neither
    # source projects, work-unit records nor artifacts are edited by approval.
    if recheck_owner is not None:recheck_owner()
    return books.save(book,state='READY')
