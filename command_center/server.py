"""The Command Center's own tiny web server.

Deliberately separate from ``app.py``. It has exactly two routes (a page,
and the form that saves it), imports nothing from ``services.product``,
``services.ad``, ``services.ebook``, any AI/API client, or ``database.py``,
and never touches ``projects.db`` or the exports directory. It cannot
generate a product, fetch from Pexels/Tavily, or call OpenAI, because it
does not import anything that can.

Run it directly (``python command_center/server.py``) or via the
"command-center" entry in ``.claude/launch.json``. Default port 5090 —
distinct from the owner's Factory window (5055) and Claude's Factory
window (5077), so it never competes with either.
"""
from __future__ import annotations

import os

from flask import Flask, redirect, render_template, request

from command_center import status

app = Flask(__name__, template_folder=str(status.HERE / "templates"), static_folder=None)


@app.route("/", methods=["GET"])
def home():
    return render_template("command_center.html", **status.build_context())


@app.route("/update", methods=["POST"])
def update():
    """Save the one canonical handoff record from the on-page form."""
    form = request.form
    completed_items = [
        line.strip() for line in form.get("completed_today", "").splitlines() if line.strip()
    ]
    existing = status.load_handoff()
    completed_log = [e for e in existing.get("completed_log", []) if e.get("date") != _today_iso()]
    if completed_items:
        completed_log.insert(0, {"date": _today_iso(), "items": completed_items})

    open_issue_text = form.get("open_issue", "").strip()
    open_issues = [{"title": open_issue_text, "detail": "", "status": "open"}] if open_issue_text else []

    status.save_handoff(
        {
            "current_task": form.get("current_task", "").strip(),
            "stopped_at": form.get("stopped_at", "").strip(),
            "next_step": form.get("next_step", "").strip(),
            "next_claude": form.get("next_claude", "code").strip() or "code",
            "open_issues": open_issues,
            "completed_log": completed_log,
            "notes": form.get("notes", "").strip(),
        }
    )
    return redirect("/")


def _today_iso() -> str:
    from datetime import date

    return date.today().isoformat()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("COMMAND_CENTER_PORT", "5090")))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
