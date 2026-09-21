"""Login routes (Phase A, forward-ported for Factory 1.8.5).

POST /auth/register, POST /auth/login, POST /auth/logout, GET /auth/me.
All of them sit behind the invite-code gate like every other route.

Passwords are hashed with bcrypt (12 rounds) and never logged, echoed or
returned. A failed login says the same thing whether the email exists or
not.
"""
from __future__ import annotations

import bcrypt
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user

import database
from auth import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_BCRYPT_ROUNDS = 12
_BAD_LOGIN = "Invalid email or password."


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
    row = database.get_user_by_email(email)
    if not row or not _check_password(password, row["password_hash"]):
        return jsonify({"ok": False, "error": _BAD_LOGIN}), 401
    if not row["active"]:
        return jsonify({"ok": False, "error": "This account has been deactivated."}), 403
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
