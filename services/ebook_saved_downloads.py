"""Read-only links to a preserved draft package; never claim release approval."""
import hashlib
import re
import zipfile
from pathlib import Path


def saved_downloads(data):
    from services.packaging import EXPORTS_DIR

    package = str(data.get('export_package_id') or data.get('package_id') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', package):
        return {}
    folder = Path(EXPORTS_DIR) / package
    pdf = folder / 'ebook.pdf'
    archive = folder / 'package.zip'
    try:
        with pdf.open('rb') as source:
            if not source.read(5).startswith(b'%PDF'):
                return {}
            source.seek(0)
            digest = hashlib.file_digest(source, 'sha256').digest()
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                return {}
            if bundle.namelist().count('ebook.pdf') != 1:
                return {}
            with bundle.open('ebook.pdf') as embedded:
                if hashlib.file_digest(embedded, 'sha256').digest() != digest:
                    return {}
        return {'pdf': f'/download/{package}/ebook.pdf',
                'zip': f'/download/{package}/package.zip'}
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, RuntimeError):
        return {}
