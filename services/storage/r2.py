"""Cloudflare R2 driver — Upgrade 0, Phase 0B-3B1.

R2 speaks the S3 API, so this is an S3 client pointed at R2's endpoint
with `region_name="auto"`. It implements the same five operations as the
local driver, so nothing that stores an artifact needs to know which one
it is talking to.

CONFIGURATION (environment variables / Render secrets only)
-----------------------------------------------------------
    FACTORY_R2_ACCOUNT_ID          <account>  -> endpoint is derived
    FACTORY_R2_BUCKET              private bucket name
    FACTORY_R2_ACCESS_KEY_ID       scoped to this bucket, Object Read & Write
    FACTORY_R2_SECRET_ACCESS_KEY
    FACTORY_R2_ENDPOINT            optional, overrides the derived endpoint
    FACTORY_R2_REGION              optional, defaults to "auto"

Credentials are read from the environment and nowhere else. They are
never written to a file, never logged, never returned in an error, and
never sent to the browser -- the browser talks to Flask, and Flask talks
to R2. The bucket is private: this driver never sets an ACL, never
requests public access, and never produces a public URL.

FAIL CLOSED
-----------
Missing or incomplete configuration raises at construction. It must never
silently fall back to some other bucket or to anonymous access, the same
discipline that fixed the provider-routing defect in v1.7.8.

SAFETY
------
Nothing in Phase 0B-3B1 uploads a customer artifact. This driver exists,
is tested against a fake S3 client, and stays unused in production until
0B-3B2 is approved.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from services.storage.base import (
    StorageDriver,
    StorageError,
    StorageKeyNotFound,
    StorageStat,
    sha256_hex,
)
from services.storage.keys import is_valid_key

#: Checksum is stored as object metadata so `stat()` can answer without
#: downloading. It is always re-verified against the bytes on readback.
CHECKSUM_META_KEY = "sha256"

_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Substrings that must never appear in an error surfaced to a caller.
_SECRET_ENV_VARS = ("FACTORY_R2_SECRET_ACCESS_KEY", "FACTORY_R2_ACCESS_KEY_ID")


class R2ConfigurationError(StorageError):
    """R2 is selected but not fully configured. Deliberately fatal."""


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def r2_endpoint(account_id: str) -> str:
    """The S3-compatible endpoint for an R2 account."""
    account = str(account_id or "").strip()
    if not _ACCOUNT_RE.match(account):
        raise R2ConfigurationError("R2 account id is missing or malformed")
    return f"https://{account}.r2.cloudflarestorage.com"


def _redact(text: object) -> str:
    """Strip anything secret out of a message before it can be surfaced.

    Belt and braces: the SDK should not put a secret in an exception, but
    a credential must not reach a log even if some layer decides to.
    """
    out = str(text)
    for var in _SECRET_ENV_VARS:
        value = _env(var)
        if value and len(value) >= 4:
            out = out.replace(value, "***redacted***")
    return out


class R2Driver(StorageDriver):
    """Cloudflare R2 behind the Factory's storage contract."""

    name = "r2"

    def __init__(
        self,
        *,
        account_id: str | None = None,
        bucket: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
        region: str | None = None,
        client: object | None = None,
    ) -> None:
        self.bucket = (bucket if bucket is not None else _env("FACTORY_R2_BUCKET"))
        account = account_id if account_id is not None else _env("FACTORY_R2_ACCOUNT_ID")
        key_id = (
            access_key_id if access_key_id is not None else _env("FACTORY_R2_ACCESS_KEY_ID")
        )
        secret = (
            secret_access_key
            if secret_access_key is not None
            else _env("FACTORY_R2_SECRET_ACCESS_KEY")
        )
        self.region = (region or _env("FACTORY_R2_REGION") or "auto")
        endpoint = endpoint_url or _env("FACTORY_R2_ENDPOINT")

        # An injected client is how the test suite exercises this driver
        # without credentials or a network. It still requires a bucket.
        if client is not None:
            if not self.bucket:
                raise R2ConfigurationError("R2 bucket name is not configured")
            self.endpoint_url = endpoint or "https://injected.invalid"
            self._client = client
            return

        missing = [
            label
            for label, value in (
                ("FACTORY_R2_BUCKET", self.bucket),
                ("FACTORY_R2_ACCESS_KEY_ID", key_id),
                ("FACTORY_R2_SECRET_ACCESS_KEY", secret),
            )
            if not value
        ]
        if not endpoint and not account:
            missing.append("FACTORY_R2_ACCOUNT_ID")
        if missing:
            # Names only. Never the values.
            raise R2ConfigurationError(
                "R2 storage is selected but not configured: missing "
                + ", ".join(sorted(missing))
            )

        self.endpoint_url = endpoint or r2_endpoint(account)

        try:
            import boto3  # noqa: PLC0415  (optional dependency, imported on use)
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise R2ConfigurationError(
                "R2 storage requires the boto3 package to be installed"
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    # -- helpers ----------------------------------------------------------

    def _check(self, key: str) -> str:
        if not is_valid_key(key):
            raise StorageError(f"invalid storage key: {key!r}")
        return key

    def _is_missing(self, exc: Exception) -> bool:
        code = getattr(getattr(exc, "response", None), "get", lambda *_: None)("Error") or {}
        if isinstance(code, dict) and str(code.get("Code")) in ("404", "NoSuchKey", "NotFound"):
            return True
        return exc.__class__.__name__ in ("NoSuchKey", "404", "ClientError") and "404" in str(exc)

    def _fail(self, action: str, key: str, exc: Exception) -> StorageError:
        return StorageError(f"R2 {action} failed for {key!r}: {_redact(exc)}")

    # -- contract ---------------------------------------------------------

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageStat:
        self._check(key)
        payload = bytes(data)
        checksum = sha256_hex(payload)
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=payload,
                ContentType=content_type,
                Metadata={CHECKSUM_META_KEY: checksum},
            )
        except Exception as exc:
            raise self._fail("put", key, exc) from None

        # Verify what was written before reporting success, exactly as the
        # local driver does. A put that cannot be read back is a failure.
        stored = self.stat(key)
        if stored is None or int(stored.size) != len(payload) or stored.checksum != checksum:
            raise StorageError(f"R2 put verification failed for {key!r}")
        return stored

    def get(self, key: str) -> bytes:
        self._check(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._is_missing(exc):
                raise StorageKeyNotFound(f"no object at {key!r}") from None
            raise self._fail("get", key, exc) from None
        body = response.get("Body")
        raw = body.read() if hasattr(body, "read") else bytes(body or b"")
        return raw if isinstance(raw, bytes) else bytes(raw)

    def exists(self, key: str) -> bool:
        return self.stat(key) is not None

    def delete(self, key: str) -> bool:
        self._check(key)
        if self.stat(key) is None:
            return False
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise self._fail("delete", key, exc) from None
        return True

    def stat(self, key: str) -> StorageStat | None:
        self._check(key)
        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if self._is_missing(exc):
                return None
            raise self._fail("stat", key, exc) from None
        meta = head.get("Metadata") or {}
        modified = head.get("LastModified")
        if isinstance(modified, datetime):
            modified = modified.astimezone(timezone.utc).isoformat()
        return StorageStat(
            key=key,
            size=int(head.get("ContentLength") or 0),
            checksum=str(meta.get(CHECKSUM_META_KEY) or ""),
            content_type=str(head.get("ContentType") or "application/octet-stream"),
            modified_at=str(modified) if modified else None,
        )

    # -- connectivity -----------------------------------------------------

    def probe(self, *, prefix: str = "_factory_probe") -> dict:
        """Round-trip a tiny synthetic object to prove connectivity.

        Deliberately writes bytes the Factory generates here and now. It
        must never be handed a customer artifact -- a connectivity check
        is not a migration.
        """
        key = f"{prefix}/connectivity.txt"
        payload = b"digital-product-factory connectivity probe\n"
        stat = self.put(key, payload, content_type="text/plain")
        readback = self.get(key)
        ok = readback == payload and stat.checksum == sha256_hex(payload)
        self.delete(key)
        return {
            "ok": ok,
            "bucket": self.bucket,
            "endpoint": self.endpoint_url,
            "region": self.region,
            "bytes": len(payload),
        }
