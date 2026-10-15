"""Local Saved Projects browser/memory fixtures; no provider calls."""
import base64
import io
import os
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reportlab.pdfgen import canvas
from app import app
import database


def seed(count=1, size=2_000_000):
    root = Path(os.environ['FACTORY_EXPORTS_DIR'])
    blob = io.BytesIO()
    pdf = canvas.Canvas(blob)
    pdf.drawString(72, 720, 'Saved ocean coloring page')
    pdf.save()
    original = blob.getvalue()
    ids = []
    for n in range(count):
        pkg = f'saved-ocean-{n}'
        folder = root / pkg
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'product.pdf').write_bytes(original)
        with zipfile.ZipFile(folder/'package.zip', 'w') as z:
            z.writestr('product.pdf', original)
        p = database.create_project(f'Saved Ocean {n}', 'product', {
            'title': f'Saved Ocean {n}', 'product_type': 'coloring_book',
            'stage': 'export_ready', 'status': 'export_ready', 'artifact_state': 'DRAFT',
            'qa_passed': True, 'generation_stage': 'full', 'needs_approval': False,
            'is_pdf': True, 'package_id': pkg, 'pdf_available': True,
            'pdf_bytes': base64.b64encode(original).decode(),
            'preview_html': '<h1>Recovered saved preview</h1><!--' + 'x'*size + '-->',
            'content': 'Original saved content', 'fields': {'pages': '2'},
            'pdf_path': str(folder/'product.pdf'),
            'product_exports': {'package_id': pkg, 'files': {
                'pdf': {'name': 'product.pdf', 'url': f'/download/{pkg}/product.pdf'},
                'zip': {'name': 'package.zip', 'url': f'/download/{pkg}/package.zip'}}},
        }, user_saved=True, user_confirmed_save=True)
        ids.append(p['id'])
    return ids


if __name__ == '__main__':
    seed()
    app.run(host='127.0.0.1', port=int(os.environ['SAVED_BROWSER_PORT']), threaded=True, use_reloader=False)
