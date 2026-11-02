"""Standalone authenticated loopback Book Studio; no legacy executor import."""
import hashlib
import io
import os
from pathlib import Path
import secrets
from flask import Flask,request,session,jsonify,render_template,redirect,send_file
from flask_login import LoginManager,current_user
from .books import Conflict
from .recovery import CorruptCheckpoint,InputConflict


def create_app(books):
    import database
    from auth import load_user
    from routes.auth import auth_bp
    root=Path(__file__).resolve().parents[2]
    app=Flask("book_studio",template_folder=str(root/"templates"))
    location=Path(books.units.path).parent/"studio-session.key"
    try:
        descriptor=os.open(location,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,"w") as stream:stream.write(secrets.token_hex(32))
    except FileExistsError:pass
    secret=location.read_text().strip()
    if len(secret)<32:raise ValueError("Saved session key is invalid")
    app.config.update(SECRET_KEY=secret,MAX_CONTENT_LENGTH=1_000_000,
        SESSION_COOKIE_NAME="ebook_v2_session",SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",REMEMBER_COOKIE_NAME="ebook_v2_remember")
    manager=LoginManager(app);manager.user_loader(load_user)
    database.init_db();app.register_blueprint(auth_bp)

    @app.before_request
    def protect():
        if request.path.startswith("/auth/") or request.path=="/health":return
        if not current_user.is_authenticated:
            if request.path=="/":return redirect("/auth/signin")
            return jsonify(error="Sign in to Book Studio"),401
        if not current_user.is_active:return jsonify(error="Account unavailable"),403
        if request.method=="POST":
            token=request.headers.get("X-CSRF-Token","")
            if not token or not secrets.compare_digest(token,session.get("ebook_v2_csrf","")):
                return jsonify(error="Reload this page before saving"),403
            if not request.is_json:return jsonify(error="Send a valid book request"),400

    @app.after_request
    def private(response):
        response.headers["Cache-Control"]="no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="same-origin"
        return response

    @app.get("/health")
    def health():return jsonify(service="factory-book-studio",worker_online=books.available(),local_text=books.available(local_text=True))

    @app.get("/")
    def home():
        session.setdefault("ebook_v2_csrf",secrets.token_urlsafe(32))
        return render_template("ebook_v2.html",csrf=session["ebook_v2_csrf"])

    @app.get("/api/books")
    def listing():return jsonify(books=books.listing(str(current_user.id)))

    @app.post("/api/books")
    def create():
        if not books.available():return jsonify(error="Start the Book Studio worker before creating a book. No book attempt was started."),503
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError("Send valid book settings")
        raw=body.get("spec")
        if isinstance(raw,dict) and raw.get("source")=="ollama" and not books.available(local_text=True):
            return jsonify(error="Start the local writing service and install the selected model before creating a topic book. No book attempt was started."),503
        book=books.create(str(current_user.id),body.get("request_key"),body.get("spec"))
        return jsonify(books.status(str(current_user.id),book["id"])),202

    @app.get("/api/books/<book_id>")
    def status(book_id):return jsonify(books.status(str(current_user.id),book_id))

    @app.get("/api/books/<book_id>/editable")
    def editable(book_id):
        from .editions import editable
        return jsonify(editable(books,str(current_user.id),book_id))

    @app.post("/api/books/<book_id>/<action>")
    def decide(book_id,action):
        actions={"approve":books.approve,"resume":books.resume}
        body=request.get_json()
        if not isinstance(body,dict):raise ValueError("Send a valid book decision")
        if action=="edit":
            from .editions import edit
            book=edit(books,str(current_user.id),book_id,body.get("revision"),body.get("request_key"),body.get("spec"))
            return jsonify(books.status(str(current_user.id),book["id"])),202
        if action=="decision":books.decide(str(current_user.id),book_id,body.get("revision"),body.get("action"),body.get("value"))
        elif action in actions:actions[action](str(current_user.id),book_id,body.get("revision"))
        else:raise LookupError("Action not found")
        return jsonify(books.status(str(current_user.id),book_id))

    @app.get("/api/books/<book_id>/covers/<theme>.jpg")
    def cover_preview(book_id,theme):
        from .topics import data
        from .publishing import verified_file
        book=books.get(str(current_user.id),book_id)
        if book["spec"].get("source")!="ollama" or book["state"] not in {"WAITING_COVER","REVIEW","READY"}:
            raise LookupError("Cover not found")
        unit_id=data(books,book)["units"].get("visuals")
        if not unit_id:raise LookupError("Cover not found")
        unit=books.units.get(str(current_user.id),unit_id)
        if unit["state"]!="COMPLETE" or theme not in unit["output"]["covers"]:raise LookupError("Cover not found")
        response=send_file(io.BytesIO(verified_file(books.root,unit["output"]["covers"][theme])),mimetype="image/jpeg")
        return response

    @app.get("/api/books/<book_id>/files/<name>")
    def download(book_id,name):
        preview=request.args.get("preview")=="1"
        data,checksum=books.download(str(current_user.id),book_id,name,preview=preview)
        mime={"ebook.pdf":"application/pdf","package.zip":"application/zip","print-pack.zip":"application/zip","manuscript.md":"text/markdown",
              "manuscript.docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "ebook.epub":"application/epub+zip","cover.jpg":"image/jpeg"}.get(name)
        if mime is None:raise LookupError("File not found")
        response=send_file(io.BytesIO(data),mimetype=mime,as_attachment=not preview,download_name=name)
        response.headers["X-Content-SHA256"]=checksum
        return response

    @app.errorhandler(LookupError)
    def missing(error):return jsonify(error="Book or file not found"),404
    @app.errorhandler(Conflict)
    @app.errorhandler(InputConflict)
    def conflict(error):return jsonify(error=str(error)),409
    @app.errorhandler(CorruptCheckpoint)
    def corrupt(error):return jsonify(error="Saved work failed its integrity check. Files were preserved for review."),409
    @app.errorhandler(ValueError)
    def invalid(error):return jsonify(error=str(error)),400
    return app
