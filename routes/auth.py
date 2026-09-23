"""Login routes (Phase A, forward-ported for Factory 1.8.5).

POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me,
and (Factory 1.8.6) GET /auth/signin, a plain page with the create-account
and sign-in forms. All of them sit behind the invite-code gate like every
other route.

Passwords are hashed with bcrypt (12 rounds) and never logged, echoed or
returned. A failed login says the same thing whether the email exists or
not.
"""
from __future__ import annotations

import threading
import time

import bcrypt
from flask import Blueprint, jsonify, make_response, request
from flask_login import current_user, login_user, logout_user

import database
from auth import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_BCRYPT_ROUNDS = 12
_BAD_LOGIN = "Invalid email or password."

# ---------------------------------------------------------------------------
# Rate limiting on failed sign-ins (Factory 1.9.1)
#
# /auth/login accepted unlimited attempts. bcrypt at 12 rounds makes each guess
# slow, which costs the attacker -- and also spends the web service's CPU, so a
# few hundred parallel guesses is a denial of service as well as a guessing run.
#
# TWO counters, because either alone is wrong:
#   * per address          -- stops one machine spraying one guess at every account.
#   * per address+account  -- stops one machine hammering one account.
# Keying on the account alone would let anybody lock a real customer out of
# their own login by failing on purpose, so the address is always part of the
# key.
#
# The counters live in this process. With more than one web worker the real
# ceiling is this limit times the number of workers; that is a looser bound than
# the numbers below, not a missing one, and it needs no new dependency and no
# shared store. If the service is ever scaled out, move this to the database or
# a cache and keep the same shape.
# ---------------------------------------------------------------------------
_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES_PER_ADDRESS = 20
_MAX_FAILURES_PER_ADDRESS_AND_ACCOUNT = 8
_MAX_TRACKED_KEYS = 20_000

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def reset_login_attempts() -> None:
    """Forget every recorded failure. For tests and for an operator's console."""
    with _attempts_lock:
        _attempts.clear()


def _client_address() -> str:
    """The caller's address, honouring the proxy header Render sets.

    X-Forwarded-For can be forged by anyone talking to the service directly, so
    this is a throttle, not an identity. It is never used for authorization.
    """
    forwarded = str(request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "unknown")


def _prune(now: float, hits: list[float]) -> list[float]:
    return [t for t in hits if now - t < _WINDOW_SECONDS]


def _retry_after(now: float, hits: list[float]) -> int:
    if not hits:
        return _WINDOW_SECONDS
    return max(1, int(_WINDOW_SECONDS - (now - min(hits))))


def _login_is_blocked(email: str) -> int | None:
    """Seconds to wait, or None when the attempt may go ahead."""
    now = time.time()
    address = _client_address()
    with _attempts_lock:
        for key, ceiling in (
            (f"ip:{address}", _MAX_FAILURES_PER_ADDRESS),
            (f"ip+email:{address}|{email}", _MAX_FAILURES_PER_ADDRESS_AND_ACCOUNT),
        ):
            hits = _prune(now, _attempts.get(key) or [])
            if hits:
                _attempts[key] = hits
            else:
                _attempts.pop(key, None)
            if len(hits) >= ceiling:
                return _retry_after(now, hits)
    return None


def _record_login_failure(email: str) -> None:
    now = time.time()
    address = _client_address()
    with _attempts_lock:
        if len(_attempts) > _MAX_TRACKED_KEYS:
            # Never let the throttle itself become the memory leak.
            for key in [k for k, v in _attempts.items() if not _prune(now, v)]:
                _attempts.pop(key, None)
            if len(_attempts) > _MAX_TRACKED_KEYS:
                _attempts.clear()
        for key in (f"ip:{address}", f"ip+email:{address}|{email}"):
            _attempts[key] = _prune(now, _attempts.get(key) or []) + [now]


def _clear_login_failures(email: str) -> None:
    address = _client_address()
    with _attempts_lock:
        _attempts.pop(f"ip:{address}", None)
        _attempts.pop(f"ip+email:{address}|{email}", None)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"),
                         bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:  # noqa: BLE001 -- a malformed hash is simply "no"
        return False


@auth_bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"ok": False, "error": "A valid email address is required."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400
    if database.get_user_by_email(email):
        return jsonify({"ok": False, "error": "An account with that email already exists."}), 409
    # Phase A rule: the first account becomes the admin; everyone after is a user.
    role = "admin" if database.count_users() == 0 else "user"
    try:
        row = database.create_user(email, _hash_password(password), role=role)
    except Exception:  # noqa: BLE001 -- a race on the unique email
        return jsonify({"ok": False, "error": "An account with that email already exists."}), 409
    user = User(row)
    login_user(user)
    return jsonify({"ok": True, "user": user.public()}), 201


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not email or not password:
        return jsonify({"ok": False, "error": "Email and password are required."}), 400
    wait = _login_is_blocked(email)
    if wait is not None:
        minutes = max(1, round(wait / 60))
        response = jsonify({
            "ok": False,
            "error": f"Too many sign-in attempts. Try again in about {minutes} minute"
                     f"{'s' if minutes != 1 else ''}.",
        })
        response.headers["Retry-After"] = str(wait)
        return response, 429
    row = database.get_user_by_email(email)
    if not row or not _check_password(password, row["password_hash"]):
        _record_login_failure(email)
        return jsonify({"ok": False, "error": _BAD_LOGIN}), 401
    if not row["active"]:
        return jsonify({"ok": False, "error": "This account has been deactivated."}), 403
    _clear_login_failures(email)
    user = User(row)
    login_user(user)
    return jsonify({"ok": True, "user": user.public()})


@auth_bp.post("/logout")
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.get("/me")
def me():
    if not getattr(current_user, "is_authenticated", False):
        return jsonify({"ok": False, "error": "Not logged in."}), 401
    return jsonify({"ok": True, "user": current_user.public()})


# ---------------------------------------------------------------------------
# Sign-in page (Factory 1.8.6)
#
# A static page: nothing from the request or the database is written into
# the HTML. The browser script sends JSON to the routes above, so the secret
# only travels in the request body over HTTPS and is never put in a URL.
# Everything the page shows back (email, role, error) is set with
# textContent, never innerHTML.
# ---------------------------------------------------------------------------
_SIGNIN_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in - Digital Product Factory</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f7f9;color:#1d2330;margin:0}
 main{max-width:420px;margin:48px auto;padding:0 16px}
 h1{font-size:1.5rem;margin:0 0 4px} p.sub{color:#5a6475;margin:0 0 24px}
 section{background:#fff;border:1px solid #dde1e7;border-radius:10px;padding:20px;margin-bottom:16px}
 h2{font-size:1.1rem;margin:0 0 12px}
 label{display:block;font-size:.9rem;margin:10px 0 4px}
 input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c5cbd5;border-radius:6px;font-size:1rem}
 button{margin-top:14px;padding:10px 16px;border:0;border-radius:6px;background:#2f6f4e;color:#fff;font-size:1rem;cursor:pointer}
 button.secondary{background:#5a6475}
 .msg{margin-top:10px;font-size:.95rem;min-height:1.2em}
 .msg.error{color:#b42318} .msg.ok{color:#2f6f4e}
 #signed-in{display:none}
</style></head>
<body><main>
<h1>Digital Product Factory</h1>
<p class="sub">Sign in to your account.</p>

<section id="signed-in">
 <h2>You are signed in</h2>
 <p>Account: <strong id="who"></strong> (<span id="role"></span>)</p>
 <a href="/">Go to the Factory</a>
 <div><button type="button" class="secondary" id="logout">Sign out</button></div>
</section>

<div id="forms">
<section>
 <h2>Sign in</h2>
 <form id="login-form" autocomplete="on">
  <label for="login-email">Email</label>
  <input id="login-email" name="email" type="email" autocomplete="username" required>
  <label for="login-password">Password</label>
  <input id="login-password" name="password" type="password" autocomplete="current-password" required>
  <button type="submit">Sign in</button>
  <div class="msg" id="login-msg" role="status"></div>
 </form>
</section>

<section>
 <h2>Create an account</h2>
 <form id="register-form" autocomplete="on">
  <label for="reg-email">Email</label>
  <input id="reg-email" name="email" type="email" autocomplete="username" required>
  <label for="reg-password">Password (at least 8 characters)</label>
  <input id="reg-password" name="password" type="password" autocomplete="new-password" minlength="8" required>
  <label for="reg-confirm">Type the password again</label>
  <input id="reg-confirm" name="confirm" type="password" autocomplete="new-password" minlength="8" required>
  <button type="submit">Create account</button>
  <div class="msg" id="register-msg" role="status"></div>
 </form>
</section>
</div>
</main>
<script>
(function () {
  function show(user) {
    var signedIn = document.getElementById("signed-in");
    var forms = document.getElementById("forms");
    if (user) {
      document.getElementById("who").textContent = user.email;
      document.getElementById("role").textContent = user.role;
      signedIn.style.display = "block"; forms.style.display = "none";
    } else {
      signedIn.style.display = "none"; forms.style.display = "block";
    }
  }
  function say(id, text, ok) {
    var el = document.getElementById(id);
    el.textContent = text; el.className = "msg " + (ok ? "ok" : "error");
  }
  function send(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json", "Accept": "application/json"},
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().catch(function () { return {ok: false}; });
    });
  }
  fetch("/auth/me", {credentials: "same-origin", headers: {"Accept": "application/json"}})
    .then(function (r) { return r.json(); })
    .then(function (d) { show(d && d.ok ? d.user : null); })
    .catch(function () { show(null); });

  document.getElementById("login-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var pw = document.getElementById("login-password");
    send("/auth/login", {email: document.getElementById("login-email").value, password: pw.value})
      .then(function (d) {
        pw.value = "";
        if (d.ok) { show(d.user); } else { say("login-msg", d.error || "Sign in failed.", false); }
      }).catch(function () { say("login-msg", "Could not reach the Factory. Try again.", false); });
  });

  document.getElementById("register-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var pw = document.getElementById("reg-password");
    var again = document.getElementById("reg-confirm");
    if (pw.value !== again.value) { say("register-msg", "The two passwords do not match.", false); return; }
    send("/auth/register", {email: document.getElementById("reg-email").value, password: pw.value})
      .then(function (d) {
        pw.value = ""; again.value = "";
        if (d.ok) { show(d.user); } else { say("register-msg", d.error || "Could not create the account.", false); }
      }).catch(function () { say("register-msg", "Could not reach the Factory. Try again.", false); });
  });

  document.getElementById("logout").addEventListener("click", function () {
    send("/auth/logout", {}).then(function () { show(null); });
  });
})();
</script>
</body></html>
"""


@auth_bp.get("/signin")
def signin_page():
    resp = make_response(_SIGNIN_PAGE)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
