"""Isolated Flask server for real-browser ebook acceptance. No paid providers."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["EBOOK_CUSTOMER_PATH_FIXTURE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

CALL_LOG = Path(os.environ.get("FACTORY_CALL_LOG") or (ROOT / "test-results" / "ebook_call_log.json"))


def _bump(kind: str) -> None:
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {"paid": 0, "pexels_http": 0}
    if CALL_LOG.is_file():
        try:
            payload.update(json.loads(CALL_LOG.read_text(encoding="utf-8")))
        except Exception:
            pass
    payload[kind] = int(payload.get(kind) or 0) + 1
    CALL_LOG.write_text(json.dumps(payload), encoding="utf-8")


def _paid(*_a, **_k):
    _bump("paid")
    raise RuntimeError("Paid provider calls are blocked in the isolated ebook server.")


def _pexels(*_a, **_k):
    _bump("pexels_http")
    raise RuntimeError("Live Pexels is blocked in the isolated ebook server.")


from app import app  # noqa: E402
import services.ebook_package as ebook_package  # noqa: E402
import services.ebook_pexels as ebook_pexels  # noqa: E402
import services.product as product  # noqa: E402
import ai_client  # noqa: E402

product.chat = _paid
ebook_package.chat_json = _paid
ai_client.chat = _paid
ai_client.chat_json = _paid
ai_client.get_client = _paid
ebook_pexels._http_get = _pexels
CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
if not CALL_LOG.is_file():
    CALL_LOG.write_text(json.dumps({"paid": 0, "pexels_http": 0}), encoding="utf-8")


if __name__ == "__main__":
    port = int(os.environ.get("FACTORY_PORT") or "5065")
    print("FACTORY_STARTED", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
