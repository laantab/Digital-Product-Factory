"""Signed preservation, queued recovery and private shared downloads.

Explicit shared-service injection enables recovery; web requests never run a worker.
"""
import secrets
import json
import io
from contextlib import closing

from flask import Blueprint, current_app, jsonify, request, session, send_file
from flask_login import current_user
from werkzeug.exceptions import BadRequest

from .legacy_snapshot import Snapshots
from .recovery import CorruptCheckpoint, InputConflict
from .recovery_handoff import preserve_and_queue, WorkerUnavailable


def blueprint(connection_factory):
    bp = Blueprint("ebook_recovery", __name__, url_prefix="/api/ebook-recovery")
    store = Snapshots(connection_factory)

    @bp.before_request
    def protect():
        if not current_user.is_authenticated or not current_user.is_active:
            return jsonify(error="Please sign in."), 401
        if request.method == "POST":
            token = request.headers.get("X-CSRF-Token", "")
            expected = session.get("ebook_recovery_csrf", "")
            if not token or not expected or not secrets.compare_digest(token, expected):
                return jsonify(error="Reload the saved book before preserving it."), 403
            if not request.is_json:
                return jsonify(error="Send a saved book version."), 400

    @bp.after_request
    def private(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def owned(project_id):
        # The public Saved Projects serializer deliberately omits owner/version.
        # Read both identities and the source body atomically from the row;
        # never infer them from client input or from transient JSON stamps.
        with closing(connection_factory()) as conn:
            row=conn.execute("""SELECT id,user_id,type,name,version,data FROM projects
                WHERE id=? AND user_id=?""",(project_id,current_user.id)).fetchone()
        if row is None:
            raise LookupError("Book not found")
        project=dict(row)
        project["data"]=json.loads(project["data"])
        if project.get("type") != "ebook":
            raise ValueError("Choose a saved ebook")
        return project

    @bp.get("/projects/<int:project_id>")
    def source(project_id):
        project = owned(project_id)
        session.setdefault("ebook_recovery_csrf", secrets.token_urlsafe(32))
        return jsonify(project_id=project["id"], name=project.get("name", ""),
                       source_version=project["version"],
                       csrf_token=session["ebook_recovery_csrf"],
                       generation_started=False)

    @bp.post("/projects/<int:project_id>/snapshots")
    def preserve(project_id):
        body = request.get_json()
        if not isinstance(body, dict) or set(body) not in ({"source_version"}, {"source_version", "recovery"}):
            raise ValueError("Send only the saved book version")
        version = body["source_version"]
        if type(version) is not int or version < 0:
            raise ValueError("Choose a valid saved book version")
        project = owned(project_id)
        if project.get("version") != version:
            raise InputConflict("This book has newer saved changes. Reload before preserving it.")
        if "recovery" in body:
            books, _ = hosted()
            snapshot_id, book = preserve_and_queue(store, books, project, current_user.id, body["recovery"])
            return jsonify(snapshot_id=snapshot_id, book_id=book["id"],
                           state=books.status(current_user.id, book["id"])["state"],
                           queued=True, generation_started=False), 202
        # DDL runs only on an explicitly authenticated save, never at import,
        # startup, listing or source inspection. No legacy row is updated.
        store.initialize()
        snapshot_id = store.save(project, current_user.id)
        return jsonify(snapshot_id=snapshot_id, project_id=project_id,
                       source_version=version, generation_started=False), 201

    @bp.get("/snapshots/<snapshot_id>")
    def reopen(snapshot_id):
        if len(snapshot_id) != 32 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise LookupError("Book not found")
        payload = store.reopen(current_user.id, snapshot_id)
        # Recheck current ownership too: a transferred source never exposes
        # its previously saved customer data to the former owner.
        owned(payload["project_id"])
        return jsonify(snapshot_id=snapshot_id, snapshot=payload,
                       generation_started=False)

    def hosted():
        services = current_app.extensions.get("ebook_v2_hosted")
        if not services:
            from .hosted_runtime import configure
            services = configure(current_app)
        if not services:
            raise RuntimeError("Hosted recovery is not configured")
        return services["books"], services["artifacts"]

    def recovery_book(book_id):
        books, artifacts = hosted()
        book = books.get(current_user.id, book_id)
        key = book["request_key"]
        if not key.startswith("snapshot:"):
            raise LookupError("Book not found")
        snapshot = store.reopen(current_user.id, key.removeprefix("snapshot:"))
        owned(snapshot["project_id"])
        return books, artifacts, book

    @bp.get("/books/<book_id>")
    def book_status(book_id):
        books, _, book = recovery_book(book_id)
        result = books.status(current_user.id, book["id"])
        with books.units.transaction() as conn:
            row = conn.execute("SELECT 1 FROM ebook_v2_artifacts WHERE book_id=? AND owner=?",
                               (book_id, str(current_user.id))).fetchone()
        result["files"] = ["ebook.pdf", "package.zip"] if row else []
        return jsonify(result)

    @bp.get("/books/<book_id>/files/<name>")
    def book_file(book_id, name):
        _, artifacts, _ = recovery_book(book_id)
        preview = request.args.get("preview") == "1"
        data, checksum = artifacts.download(current_user.id, book_id, name, preview=preview)
        response = send_file(io.BytesIO(data),
                             mimetype="application/pdf" if name == "ebook.pdf" else "application/zip",
                             as_attachment=not preview, download_name=name)
        response.headers["X-Content-SHA256"] = checksum
        return response

    @bp.errorhandler(WorkerUnavailable)
    def worker_unavailable(error):
        return jsonify(error=str(error)), 503

    @bp.errorhandler(LookupError)
    def missing(error):
        return jsonify(error="Book not found."), 404

    @bp.errorhandler(InputConflict)
    def conflict(error):
        return jsonify(error=str(error)), 409

    @bp.errorhandler(CorruptCheckpoint)
    def corrupt(error):
        return jsonify(error="The saved recovery copy failed verification."), 409

    @bp.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @bp.errorhandler(BadRequest)
    def malformed(error):
        return jsonify(error="Send a valid saved book request."), 400

    @bp.errorhandler(Exception)
    def unavailable(error):
        # Database errors never expose connection details or the saved text.
        current_app.logger.error("Book recovery storage unavailable: %s", type(error).__name__)
        return jsonify(error="Saved-book recovery is temporarily unavailable. Your original book is unchanged."), 503

    return bp
