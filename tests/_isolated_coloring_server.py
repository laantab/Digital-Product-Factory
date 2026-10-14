"""Local browser fixture. All provider output is local; no network providers."""
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_coloring_background_build import art, plan
from app import app
from services.coloring_book import builder
from services.jobs import workflow_trigger
from services.jobs.workflow_runner import run_build
from services.storage import LocalFilesystemDriver
import services.storage
import services.storage.compat

root = Path(os.environ['COLORING_BROWSER_ROOT'])
driver = LocalFilesystemDriver(root / 'storage')
services.storage.get_storage = lambda: driver
services.storage.compat.get_storage = lambda: driver
builder.generate_visual_image = art
builder.chat_json = plan

def trigger(task, pid):
    threading.Thread(target=run_build, args=(int(pid),), daemon=True).start()
    return 'local-fixture-run'
workflow_trigger._start_task = trigger
app.run(host='127.0.0.1', port=int(os.environ['COLORING_BROWSER_PORT']), threaded=True, use_reloader=False)
