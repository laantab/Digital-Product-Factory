"""Session-local dev server on 5077 (see SESSION_HANDOFF notes on 5055)."""
import os
os.environ.setdefault("FACTORY_PORT", "5077")
from app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5077, debug=False, use_reloader=False)
