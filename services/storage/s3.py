"""External S3-compatible driver CONTRACT — not implemented in 0B-3A.

NOTHING IS PROVISIONED BY THIS FILE. No bucket, no account, no provider
choice, no credentials, and no `boto3` dependency. Importing it is safe;
instantiating it raises, deliberately and loudly.

WHY IT EXISTS NOW
-----------------
Phase 0B-3A's job is to prove the storage boundary is the right shape
before anything moves through it. Writing the remote contract down while
the local driver is being built is what keeps the interface honest: if a
method could not be implemented against object storage, that is a design
flaw worth discovering now rather than in 0B-3B.

WHAT A REAL IMPLEMENTATION MUST HONOUR
--------------------------------------
* put(key, data, content_type) -> StorageStat
    Single PutObject for the sizes involved (largest measured artifact is
    ~56 MB; multipart is not required below the provider's threshold).
    Must verify the stored object before reporting success -- compare the
    returned ETag/checksum, or re-read -- because the migration's safety
    contract depends on a put that never lies.
* get(key) -> bytes
    Raise StorageKeyNotFound on a 404-equivalent, StorageError otherwise.
    A network failure must never be reported as "absent": absent means
    the caller may fall back to legacy, and a false absent could later be
    read as permission to discard a legacy copy.
* exists(key) -> bool
    HeadObject. Same rule: a transport failure is an error, not a False.
* delete(key) -> bool
    False when already absent. Idempotent.
* stat(key) -> StorageStat | None
    HeadObject mapped to size/checksum/content-type. If the provider's
    checksum is not SHA-256, either store the SHA-256 as object metadata
    at put time or have stat read the object; StorageStat.checksum must
    be the same SHA-256 the rest of the layer compares against.

OPERATIONAL REQUIREMENTS (decide in 0B-3B, not here)
----------------------------------------------------
* Provider, region and egress terms -- still an open decision. Render's
  own object storage was alpha at the time of the §26 verification, so
  the target is an external S3-compatible service.
* Credentials are storage-only and separate from every product-generation
  provider key, per the blueprint's per-domain credential rule.
* Both the web service and the future worker need read access; only the
  worker and migration tooling need write access.
* Customer downloads stream through the app or a short-lived signed URL.
  The bucket is never public.
* A startup health check performs a write/read/delete probe and refuses
  to boot on failure.
"""
from __future__ import annotations

from services.storage.base import StorageDriver, StorageStat


class S3CompatibleDriver(StorageDriver):
    """Placeholder for the external object-storage driver.

    Instantiating this is an error until Phase 0B-3B selects a provider
    and the owner approves creating a bucket. It exists so the contract
    is reviewable and so `get_storage()` has a real name to reject.
    """

    name = "s3"

    def __init__(self, *_args, **_kwargs):
        raise NotImplementedError(
            "The S3-compatible storage driver is a written contract only. "
            "Phase 0B-3A does not provision external storage, choose a "
            "provider, or add an SDK dependency. See this module's "
            "docstring for what an implementation must honour."
        )

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> StorageStat:  # noqa: D102
        raise NotImplementedError

    def get(self, key: str) -> bytes:  # noqa: D102
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # noqa: D102
        raise NotImplementedError

    def delete(self, key: str) -> bool:  # noqa: D102
        raise NotImplementedError

    def stat(self, key: str) -> StorageStat | None:  # noqa: D102
        raise NotImplementedError
