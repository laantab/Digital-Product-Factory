"""Pin Factory Pro proxy (Phase B2, for Factory 1.8.5).

Proxy routes /pin-factory/* to Pin Factory Pro, adding:
  - X-Internal-API-Key  — the shared secret, injected server-side only.
  - X-Factory-User-ID   — the logged-in Factory user's id (current_user.id),
                          passed in by the route. Nothing the browser sends
                          is ever used as the user's identity.

NEVER forward: Cookie, Authorization, Host, X-Forwarded-For (browser-supplied),
or any other hop-by-hop / browser-authorization header.

Timeouts: 10 s connection, 20 s read.
Errors: controlled 502/503 JSON, no stack trace, no secret values.

The route is responsible for requiring a logged-in, active user
(auth.active_user_required) and for passing that user's id in.
"""

from __future__ import annotations

import json
import os
import urllib.parse

import requests

# How long the proxy waits for the upstream. Keep these short: a hanging proxy
# ties up a Flask worker and blocks the customer's next action.
_CONNECT_TIMEOUT_SECONDS = 10
_READ_TIMEOUT_SECONDS = 20

# Headers that must NEVER be forwarded from the browser request to PFP.
# These carry browser-managed credentials or internal routing that PFP must not see.
_FORBIDDEN_REQUEST_HEADERS = frozenset({
    # Auth / identity
    "authorization",
    "cookie",
    "x-api-key",
    # Internal routing — set by proxies/load balancers, not browsers
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "x-client-ip",
    # Hop-by-hop (RFC 9110 §7.6.2) — must not be forwarded
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
})

# Response headers that may be returned to the browser. An ALLOW list, not a
# deny list: anything else Pin Factory Pro sends is dropped. In particular
# Set-Cookie (would set cookies on the Factory's own domain), Location (would
# reveal Pin Factory Pro's internal address), Content-Encoding and
# Content-Length (requests has already decoded the body, so passing them on
# would corrupt the response), hop-by-hop headers and any X-Internal-* header.
_ALLOWED_RESPONSE_HEADERS = frozenset({
    "content-type",
    "content-disposition",
    "cache-control",
    "etag",
    "last-modified",
    "expires",
})


# Fields a browser might use to claim to be someone else. They are removed
# from the forwarded query string and from a JSON object body, so Pin Factory
# Pro only ever learns the user from X-Factory-User-ID.
_IDENTITY_FIELDS = frozenset({
    "user_id", "userid", "factory_user_id", "account_ref", "x-factory-user-id",
})


def _strip_identity_from_query(raw_qs: str) -> str:
    pairs = urllib.parse.parse_qsl(raw_qs, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k.strip().lower() not in _IDENTITY_FIELDS]
    return urllib.parse.urlencode(kept)


def _strip_identity_from_body(body: bytes, content_type: str) -> bytes:
    if not body or "json" not in (content_type or "").lower():
        return body
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(payload, dict):
        return body
    cleaned = {k: v for k, v in payload.items()
               if str(k).strip().lower() not in _IDENTITY_FIELDS}
    if len(cleaned) == len(payload):
        return body
    return json.dumps(cleaned).encode("utf-8")


def _is_safe_target_path(path: str) -> bool:
    """Reject paths that could escape the intended PFP API surface.

    Deliberately NOT os.path: on Windows, os.path.normpath turns "/etc/passwd"
    into "\\etc\\passwd", which no longer starts with "/" and slipped
    through (caught by the Windows run of the proxy tests). URL paths are
    checked as URL paths, identically on every operating system.
    """
    p = str(path or "")
    if not p:
        return False
    if p.startswith("/") or "\\" in p or ":" in p or "%" in p:
        return False
    segments = p.split("/")
    return all(seg not in ("", ".", "..") for seg in segments)


def _build_upstream_url(base_url: str, target_path: str) -> str:
    """Join base URL and target path, then validate."""
    # Strip any trailing slash from base so we get exactly one /
    base = base_url.rstrip("/")
    path = "/" + target_path.lstrip("/")
    upstream = base + path
    parsed = urllib.parse.urlparse(upstream)
    # Only http and https schemes are allowed.
    if parsed.scheme not in ("http", "https"):
        return ""
    if not parsed.hostname:
        return ""
    # The host is fixed by PIN_FACTORY_BASE_URL alone. target_path comes from
    # the route table (never from the browser), and must not change the host.
    base_host = urllib.parse.urlparse(base).hostname
    if parsed.hostname != base_host:
        return ""
    return upstream


class _UpstreamUnavailable(Exception):
    """Raised when PFP is unreachable or times out."""

    def __init__(self, reason: str):
        self.reason = reason


def _make_proxy_request(
    upstream_url: str,
    method: str,
    *,
    factory_user_id: str,
    request_body: bytes | None,
    request_headers: dict[str, str],
    log,
) -> requests.Response:
    """Send a proxied request to Pin Factory Pro.

    Adds X-Internal-API-Key and X-Factory-User-ID server-side.
    Strips forbidden browser headers.
    Raises _UpstreamUnavailable on connection / timeout failure.
    """
    internal_key = os.environ.get("PIN_FACTORY_INTERNAL_KEY", "").strip()

    # Build safe upstream headers: forward only Content-Type and Accept.
    upstream_headers: dict[str, str] = {}
    safe_forward = {"content-type", "accept", "user-agent", "accept-encoding"}
    for name, value in request_headers.items():
        if name.lower() in safe_forward:
            upstream_headers[name] = value

    # Inject internal auth — never log these in detail.
    upstream_headers["X-Internal-API-Key"] = internal_key
    upstream_headers["X-Factory-User-ID"] = factory_user_id

    try:
        response = requests.request(
            method.upper(),
            upstream_url,
            headers=upstream_headers,
            data=request_body,
            timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
            allow_redirects=False,  # never follow redirects (could leak the internal key)
        )
        return response
    except requests.ConnectionError as exc:
        log("pin factory upstream connection error (%s)", type(exc).__name__)
        raise _UpstreamUnavailable("Pin Factory Pro is unavailable.") from exc
    except requests.Timeout as exc:
        log("pin factory upstream timeout (%s)", type(exc).__name__)
        raise _UpstreamUnavailable("Pin Factory Pro did not respond in time.") from exc
    except requests.RequestException as exc:
        log("pin factory upstream request error (%s)", type(exc).__name__)
        raise _UpstreamUnavailable("Pin Factory Pro request failed.") from exc


def _json_error(message: str, status: int) -> tuple[bytes, int, dict]:
    """Return a safe JSON error as (bytes_body, status_code, headers)."""
    return json.dumps({"ok": False, "error": message}).encode(), status, {"Content-Type": "application/json"}


def proxy_pin_factory(
    flask_request,
    target_path: str,
    log,
    *,
    factory_user_id: str,
) -> tuple[bytes, int, dict]:
    """Proxy one request to Pin Factory Pro.

    Args:
        flask_request: the current Flask request object.
        target_path:   PFP path, e.g. "text" or "image". Must not contain "..".
        log:           callable like app.logger.info (receives a format str + args).
        factory_user_id: str(current_user.id), supplied by the route. Required.

    Returns:
        (bytes_body, status_code, response_headers) — all paths return 3 values.

    The route is responsible for requiring a logged-in, active user.
    """
    uid = str(factory_user_id or "").strip()
    if not uid.isdigit():
        # No trusted identity means no request. Never "anonymous".
        return _json_error("Please log in.", 401)

    base_url = os.environ.get("PIN_FACTORY_BASE_URL", "").strip()

    # Configured away: return a clear 503 so the caller knows the integration
    # is intentionally disabled rather than confused about why PFP isn't responding.
    if not base_url or not os.environ.get("PIN_FACTORY_INTERNAL_KEY", "").strip():
        return _json_error("Pin Factory Pro is not configured.", 503)

    if not _is_safe_target_path(target_path):
        return _json_error("Invalid path.", 400)

    upstream_url = _build_upstream_url(base_url, target_path)
    if not upstream_url:
        return _json_error("Invalid Pin Factory Pro URL.", 502)

    # Forward any query string from the original request to the upstream.
    raw_qs = flask_request.query_string
    if raw_qs:
        qs = raw_qs.decode("utf-8") if isinstance(raw_qs, bytes) else str(raw_qs)
        qs = _strip_identity_from_query(qs)
        if qs:
            upstream_url = upstream_url + "?" + qs

    body = _strip_identity_from_body(flask_request.get_data(),
                                     flask_request.headers.get("Content-Type", ""))
    upstream_headers = {k: v for k, v in flask_request.headers}

    try:
        response = _make_proxy_request(
            upstream_url=upstream_url,
            method=flask_request.method,
            factory_user_id=uid,
            request_body=body if body else None,
            request_headers=upstream_headers,
            log=log,
        )
    except _UpstreamUnavailable as exc:
        return _json_error(exc.reason, 503)

    # A redirect would hand the browser Pin Factory Pro's internal address
    # (and invite it to call PFP directly). Refuse it instead of passing it on.
    if 300 <= int(response.status_code) < 400:
        log("pin factory upstream answered with a redirect (%s)", response.status_code)
        return _json_error("Pin Factory Pro request failed.", 502)

    # Forward only allow-listed response headers.
    response_headers: dict[str, str] = {}
    for name, value in response.headers.items():
        if name.lower() in _ALLOWED_RESPONSE_HEADERS:
            response_headers[name] = value

    # PFP always returns JSON for /api/*; mirror the content type.
    ct = response.headers.get("Content-Type", "")
    if "json" in ct.lower():
        response_headers["Content-Type"] = "application/json"

    return response.content, response.status_code, response_headers
