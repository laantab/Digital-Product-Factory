"""One revision, one set of hashes, one customer package.

THE DEFECT THIS FIXES
---------------------
The Export panel showed a PDF and ZIP hash that did not match the files a
customer would actually download, and nothing on the screen said so.

The two came from different moments. `data["ebook_export_identity"]` is
stamped by services/ebook_design_export.py when design preflight last ran. The
downloadable files are written later, by a separate packaging pass, which
records its own hash in an unrelated top-level key and never refreshes the
identity block. Meanwhile `artifact_revision` is deliberately held constant
across packaging, so nothing anywhere changed to signal the divergence.

A second, worse failure: packaging called the design renderer again on every
export. That re-render is a verification copy. It is allowed to differ by a
byte from the certified package, and it overwrote the customer PDF/ZIP. Saved
Projects then served those new bytes while `preview_digest` still named the
certified PDF.

THE RULE
--------
A hash is only shown when it was taken from the bytes now on disk for the
current export package. Anything else is reported as unverified, never
silently displayed.

Customer download and re-export must reuse the certified package for this
revision. A later verification_copy render must not replace those bytes, and
must not be adopted as the stored identity.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any

_SAFE_PACKAGE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Every customer download endpoint must resolve to this one package.
CUSTOMER_PDF_NAME = "ebook.pdf"
CUSTOMER_ZIP_NAME = "package.zip"


@dataclass
class RevisionIdentity:
    """What can honestly be said about the current artifact revision."""

    package_id: str = ""
    pdf_sha256: str = ""
    zip_sha256: str = ""
    pdf_path: str = ""
    zip_path: str = ""
    verified: bool = False
    stale: bool = False
    findings: list[str] = field(default_factory=list)
    stored: dict[str, Any] = field(default_factory=dict)

    def as_public_dict(self) -> dict[str, Any]:
        """The identity block the workspace screen may display.

        Hashes appear only when they were read from the files on disk. When
        they were not, the fields are empty and `verified` is false — the
        screen shows "not yet verified" rather than a number that looks
        authoritative and is not.
        """
        base = {k: v for k, v in (self.stored or {}).items()
                if k not in {"pdf_sha256", "zip_sha256"}}
        base.update({
            "package_id": self.package_id,
            "pdf_sha256": self.pdf_sha256 if self.verified else "",
            "zip_sha256": self.zip_sha256 if self.verified else "",
            "verified": self.verified,
            "stale": self.stale,
            "findings": list(self.findings),
        })
        return base


def _sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 512), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exports_root() -> str:
    from services.ebook_package import EXPORTS_DIR

    return str(EXPORTS_DIR)


def current_package_id(data: dict) -> str:
    for key in ("export_package_id", "package_id", "artifact_id"):
        value = str((data or {}).get(key) or "").strip()
        if value and _SAFE_PACKAGE_ID.match(value):
            return value
    return ""


def customer_download_refs(data: dict) -> dict[str, str]:
    """The single artifact id and paths every customer download must use."""
    package_id = current_package_id(data)
    root = os.path.join(_exports_root(), package_id) if package_id else ""
    return {
        "artifact_id": str((data or {}).get("artifact_id") or package_id or ""),
        "package_id": package_id,
        "pdf_path": os.path.join(root, CUSTOMER_PDF_NAME) if root else "",
        "zip_path": os.path.join(root, CUSTOMER_ZIP_NAME) if root else "",
        "pdf_url": f"/download/{package_id}/{CUSTOMER_PDF_NAME}" if package_id else "",
        "zip_url": f"/download/{package_id}/{CUSTOMER_ZIP_NAME}" if package_id else "",
    }


def certified_pdf_sha256(data: dict) -> str:
    """The PDF hash this revision was certified under.

    `preview_digest` is stamped when the customer package is first accepted.
    Later packaging must not replace it with a verification re-render hash.
    """
    stored = (data or {}).get("ebook_export_identity")
    stored = stored if isinstance(stored, dict) else {}
    preview = str(stored.get("preview_digest") or "").strip().lower()
    if len(preview) == 64:
        return preview
    pdf = str(stored.get("pdf_sha256") or (data or {}).get("pdf_sha256") or "").strip().lower()
    return pdf if len(pdf) == 64 else ""


def workspace_export_action(data: dict) -> str:
    """reuse existing certified files, keep a diverged package, or render first.

    ``reuse`` — on-disk files match the certified identity; do not re-render.
    ``keep_existing`` — an APPROVED/LOCKED artifact's files no longer match
    the certified digest; do not overwrite an accepted package with another
    verification copy.
    ``render`` — no customer package yet, identity was cleared for a change,
    or this is a DRAFT whose on-disk files are stale.

    THE DEFECT THIS FIXES
    ----------------------
    A hash mismatch used to mean "keep_existing" unconditionally, with no
    regard for lifecycle state. That is the right call for an APPROVED/LOCKED
    artifact -- a re-render is a verification copy and must never silently
    replace bytes a customer may already have. It is the wrong call for a
    DRAFT: editing a DRAFT project (a caption, a photo, anything) legitimately
    changes its certified identity, and a customer who then downloaded the
    project would keep receiving the OLD PDF/ZIP forever while every screen
    reported the NEW hash as current -- a stale package the Factory itself
    could not detect, because reconcile()/approvals_match_current_revision()
    only compare stored hashes to bytes on disk, and those bytes were never
    refreshed. Found rebuilding Project 351 after a caption fix: preview and
    preflight both correctly recomputed the new identity, but export kept
    serving the pre-fix PDF because the mismatch alone triggered
    "keep_existing" regardless of DRAFT status.

    DRAFT + identity changed -> render (rebuild safely).
    APPROVED/LOCKED + identity changed -> keep_existing (preserve/block).
    """
    refs = customer_download_refs(data)
    pdf_path = refs["pdf_path"]
    zip_path = refs["zip_path"]
    if not refs["package_id"] or not os.path.isfile(pdf_path) or not os.path.isfile(zip_path):
        return "render"
    certified = certified_pdf_sha256(data)
    if not certified:
        return "render"
    try:
        live = _sha_file(pdf_path)
    except OSError:
        return "render"
    if live == certified:
        return "reuse"

    from services.quality.artifact_state import ArtifactState, ArtifactStateError, resolve_artifact_state

    try:
        state = resolve_artifact_state(data)
    except ArtifactStateError:
        # Conflicting lifecycle evidence: err toward protecting existing
        # bytes rather than guessing this is safe to overwrite.
        return "keep_existing"
    return "render" if state is ArtifactState.DRAFT else "keep_existing"


def reconcile(data: dict) -> RevisionIdentity:
    """Compare what is displayed against what is on disk. Reads only."""
    stored = data.get("ebook_export_identity")
    stored = dict(stored) if isinstance(stored, dict) else {}
    package_id = current_package_id(data)
    identity = RevisionIdentity(package_id=package_id, stored=stored)

    if not package_id:
        identity.findings.append("This book has no export package yet.")
        return identity

    root = os.path.join(_exports_root(), package_id)
    pdf_path = os.path.join(root, "ebook.pdf")
    zip_path = os.path.join(root, "package.zip")
    identity.pdf_path = pdf_path
    identity.zip_path = zip_path

    if not os.path.isfile(pdf_path) or not os.path.isfile(zip_path):
        identity.findings.append(
            "The files for this revision are not on disk, so their hashes "
            "cannot be shown."
        )
        if stored.get("pdf_sha256") or stored.get("zip_sha256"):
            identity.stale = True
            identity.findings.append(
                "The stored hashes belong to an earlier revision and are not "
                "displayed."
            )
        return identity

    try:
        identity.pdf_sha256 = _sha_file(pdf_path)
        identity.zip_sha256 = _sha_file(zip_path)
    except OSError as exc:
        identity.findings.append(f"The export files could not be read: {exc}")
        return identity

    identity.verified = True

    for label, live, was in (
        ("PDF", identity.pdf_sha256, str(stored.get("pdf_sha256") or "")),
        ("ZIP", identity.zip_sha256, str(stored.get("zip_sha256") or "")),
    ):
        if was and was != live:
            identity.stale = True
            identity.findings.append(
                f"The stored {label} hash was taken from an earlier revision; "
                "the hash shown is read from the current file."
            )
    return identity


def stamp_current_revision(data: dict) -> dict[str, Any]:
    """Write the on-disk hashes back into the identity block.

    Called at the end of packaging, so the stored identity describes the files
    that were just written rather than the ones design preflight last saw.
    A verification re-render that does not match the certified preview digest
    is not adopted as the customer identity.
    Returns the identity block that was stored.
    """
    identity = reconcile(data)
    stored = dict(data.get("ebook_export_identity") or {})
    if not identity.verified:
        return stored
    certified = certified_pdf_sha256(data)
    if certified and identity.pdf_sha256 and certified != identity.pdf_sha256:
        return stored
    block = stored
    block["pdf_sha256"] = identity.pdf_sha256
    block["zip_sha256"] = identity.zip_sha256
    block["package_id"] = identity.package_id
    if not str(block.get("preview_digest") or "").strip():
        block["preview_digest"] = identity.pdf_sha256
    block["verified_at_revision"] = data.get("artifact_revision")
    data["ebook_export_identity"] = block
    # The parallel key packaging used to write on its own, kept in step so the
    # two can never disagree again.
    data["pdf_sha256"] = identity.pdf_sha256
    data["zip_sha256"] = identity.zip_sha256
    return block


def approvals_match_current_revision(data: dict) -> tuple[bool, list[str]]:
    """True when the approved stages and the files on disk are the same revision.

    A book may legitimately show approved stages with no export yet. What it
    may never show is an approved, preflight-passed state beside files whose
    hashes do not match the identity those approvals were granted against.
    """
    findings: list[str] = []
    identity = reconcile(data)
    if not identity.package_id or not identity.verified:
        return True, findings  # nothing on disk to contradict; not a mismatch
    if identity.stale:
        findings.extend(identity.findings)
    stored_manuscript = str((identity.stored or {}).get("manuscript_digest") or "")
    if stored_manuscript:
        from services.ebook_design_workspace import manuscript_digest

        if manuscript_digest(data) != stored_manuscript:
            findings.append(
                "The manuscript has changed since these files were built, so "
                "the approvals refer to an earlier revision."
            )
    return not findings, findings
