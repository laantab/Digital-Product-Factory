"""Read-only links to a preserved draft package; never claim release approval."""
import hashlib
import io
import re
import zipfile
from pathlib import Path


def _reviewed_previous_downloads(data, project_id):
    """Prefer the exact reviewed pair when a later export replaced it."""
    review = data.get('release_review') or {}
    if project_id <= 0 or review.get('status') != 'Ready for approval':
        return {}
    try:
        import database
        from services.storage.compat import verified_asset_bytes

        found = {}
        for row in database.list_assets(project_id) or []:
            if row.get('kind') != 'export_previous':
                continue
            match = re.search(r'/previous/([0-9a-f]{16})/(ebook\.pdf|package\.zip)$', str(row.get('storage_key') or ''))
            if not match:
                continue
            kind = 'pdf' if match[2] == 'ebook.pdf' else 'zip'
            expected = review.get(f'{kind}_sha256')
            if not expected or row.get('checksum') != expected or match[1] != expected[:16]:
                continue
            raw = verified_asset_bytes(row['storage_key'])
            if raw and hashlib.sha256(raw).hexdigest() == expected:
                found[kind] = (raw, f'/ebook-workspace/{project_id}/previous-exports/{match[1]}/{match[2]}')
        if set(found) != {'pdf', 'zip'} or not found['pdf'][0].startswith(b'%PDF'):
            return {}
        with zipfile.ZipFile(io.BytesIO(found['zip'][0])) as bundle:
            if bundle.testzip() is not None or bundle.namelist().count('ebook.pdf') != 1:
                return {}
            if bundle.read('ebook.pdf') != found['pdf'][0]:
                return {}
        return {kind: value[1] for kind, value in found.items()}
    except Exception:
        # History/storage failure must still permit an intact local package.
        return {}


def saved_downloads(data, project_id=0):
    from services.packaging import EXPORTS_DIR

    previous = _reviewed_previous_downloads(data, project_id)
    if previous:
        return previous
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
        pass

    # A Render instance can lose its ephemeral export directory while the
    # approved, checksum-verified PDF and ZIP remain in persistent storage.
    # Preserve the existing disk path above. Never expose an unowned package
    # or trust stored metadata alone: verify BOTH bytes and the ZIP/PDF pair.
    if not isinstance(project_id, int) or project_id <= 0:
        return {}
    try:
        from services.storage.compat import read_export_or_legacy

        pdf_bytes = read_export_or_legacy(project_id, f'{package}/ebook.pdf')
        zip_bytes = read_export_or_legacy(project_id, f'{package}/package.zip')
        if not pdf_bytes or not zip_bytes or not pdf_bytes.startswith(b'%PDF'):
            return {}
        digest = hashlib.sha256(pdf_bytes).digest()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as bundle:
            if bundle.testzip() is not None or bundle.namelist().count('ebook.pdf') != 1:
                return {}
            with bundle.open('ebook.pdf') as embedded:
                if hashlib.file_digest(embedded, 'sha256').digest() != digest:
                    return {}
        return {'pdf': f'/download/{package}/ebook.pdf',
                'zip': f'/download/{package}/package.zip'}
    except Exception:
        # Unavailable or unverified storage must never advertise downloads.
        return {}
