"""Factory user login (Phase A, forward-ported for Factory 1.8.5).

Flask-Login wraps a database user row. The session cookie Flask-Login uses
is signed with the app's SECRET_KEY, so the user id in it cannot be forged
by a browser. `current_user.id` is therefore the ONLY trusted source of who
is making a request: never a query string, form field, JSON body, custom
header or iframe message.

This is additive. No existing route requires a login because of this
module; the invite-code gate still runs first on every request.
"""
from __future__ import annotations

from functools import wraps

from flask import jsonify
from flask_login import UserMixin, current_user

import database


class User(UserMixin):
    """A logged-in Factory user. Never carries the password hash outward."""

    def __init__(self, row: dict):
        self.id = int(row["id"])
        self.email = str(row.get("email") or "")
        self.role = str(row.get("role") or "user")
        self._active = bool(row.get("active"))

    @property
    def is_active(self) -> bool:  # Flask-Login refuses inactive users
        return self._active

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def get_id(self) -> str:
        return str(self.id)

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "role": self.role}

    @classmethod
    def get(cls, user_id) -> "User | None":
        row = database.get_user(user_id)
        return cls(row) if row else None


def load_user(user_id: str) -> "User | None":
    """Flask-Login user_loader. Re-reads the row on every request, so a user
    deactivated in the database loses access on their next request."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    user = User.get(uid)
    if user is None or not user.is_active:
        return None
    return user


def _refuse(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def active_user_required(f):
    """Require a logged-in, active user. JSON 401 otherwise (never a redirect)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not getattr(current_user, "is_authenticated", False):
            return _refuse("Please log in.", 401)
        if not getattr(current_user, "is_active", False):
            return _refuse("This account is not active.", 403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require a logged-in, active admin. 401 if not logged in, 403 if not admin."""
    @wraps(f)
    @active_user_required
    def decorated(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            return _refuse("Admin access required.", 403)
        return f(*args, **kwargs)
    return decorated
