"""Combined KDP preflight validator (Pass 2).

Orchestrates Pass 1 foundations plus Factory artifact/QA/export identity checks.
Pure validation and gate helpers — no Amazon APIs, no paid calls, no content regen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from services.kdp.ai_disclosure import AiDisclosureError, AiProvenance, build_ai_disclosure
from services.kdp.classification import ContentClass, classify_content
from services.kdp.geometry import GeometryError, geometry_bundle
from services.kdp.metadata import MetadataError, validate_book_metadata
from services.kdp.print_profile import BindingType, PrintProfileError, build_print_profile
from services.quality.artifact_identity import (
    content_digest_from_pdf_bytes,
    decode_pdf_bytes,
    verify_artifact_identity,
)
from services.quality.artifact_state import (
    ArtifactState,
    ArtifactStateError,
    current_revision,
    resolve_artifact_state,
)

RESULT_PASS = "PASS — Ready for Amazon Previewer"
RESULT_WARNING = "WARNING — Human review required"
RESULT_FAIL = "FAIL — KDP export blocked"

SEVERITY_FAIL = "FAIL"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTODO\b", re.I),
    re.compile(r"\bTBD\b", re.I),
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"\bplaceholder\b", re.I),
    re.compile(r"\bexample\.com\b", re.I),
    re.compile(r"\[insert[^\]]*\]", re.I),
    re.compile(r"\{\{[^{}]+\}\}"),
)

_SUPPORTED_PUBLICATION_FORMATS = frozenset({"ebook", "paperback"})
_PRINT_PRODUCT_TYPES = frozenset(
    {
        "coloring_book",
        "word_search",
        "crossword",
        "math_worksheet",
        "spelling_worksheet",
        "planner",
    }
)


@dataclass
class PreflightFinding:
    rule_id: str
    severity: str
    product_format: str
    affected: str
    explanation: str
    required_correction: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "product_format": self.product_format,
            "affected": self.affected,
            "explanation": self.explanation,
            "required_correction": self.required_correction,
            "evidence": self.evidence,
        }


@dataclass
class KdpPreflightResult:
    overall: str
    product_type: str | None
    publication_format: str
    artifact_state: str | None
    artifact_revision: int | None
    content_digest: str | None
    asset_manifest_digest: str | None
    findings: list[PreflightFinding] = field(default_factory=list)
    print_profile: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    classification: dict[str, Any] | None = None
    ai_disclosure: dict[str, Any] | None = None
    preflight_token: str = ""
    preflighted_at: str = ""
    warnings_require_ack: bool = False
    package_allowed: bool = False

    @property
    def ok_for_package(self) -> bool:
        return self.package_allowed

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "product_type": self.product_type,
            "publication_format": self.publication_format,
            "artifact_state": self.artifact_state,
            "artifact_revision": self.artifact_revision,
            "content_digest": self.content_digest,
            "asset_manifest_digest": self.asset_manifest_digest,
            "findings": [f.as_dict() for f in self.findings],
            "print_profile": self.print_profile,
            "geometry": self.geometry,
            "metadata": self.metadata,
            "classification": self.classification,
            "ai_disclosure": self.ai_disclosure,
            "preflight_token": self.preflight_token,
            "preflighted_at": self.preflighted_at,
            "warnings_require_ack": self.warnings_require_ack,
            "package_allowed": self.package_allowed,
            "label": "Ready for Amazon Previewer"
            if self.overall == RESULT_PASS
            else self.overall,
            "amazon_approval_claim": None,
            "note": "Never labeled Guaranteed Amazon Approved.",
        }


class KdpPreflightError(ValueError):
    """KDP preflight or prepare-package gate failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _finding(
    findings: list[PreflightFinding],
    *,
    rule_id: str,
    severity: str,
    product_format: str,
    affected: str,
    explanation: str,
    required_correction: str,
    evidence: str,
) -> None:
    findings.append(
        PreflightFinding(
            rule_id=rule_id,
            severity=severity,
            product_format=product_format,
            affected=affected,
            explanation=explanation,
            required_correction=required_correction,
            evidence=evidence,
        )
    )


def _merge_settings(
    project_data: Mapping[str, Any],
    *,
    print_settings: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None,
    ai_disclosure: Mapping[str, Any] | None,
    publication_format: str | None,
) -> dict[str, Any]:
    data = dict(project_data or {})
    stored = data.get("kdp_settings") if isinstance(data.get("kdp_settings"), dict) else {}
    fmt = (
        publication_format
        or (print_settings or {}).get("publication_format")
        or stored.get("publication_format")
        or data.get("publication_format")
        or ("ebook" if str(data.get("product_type") or "").lower() == "ebook" else "paperback")
    )
    merged_print = {
        **(stored.get("print") if isinstance(stored.get("print"), dict) else {}),
        **(data.get("kdp_print_settings") if isinstance(data.get("kdp_print_settings"), dict) else {}),
        **(dict(print_settings) if print_settings else {}),
    }
    merged_meta = {
        "title": data.get("title") or data.get("listing_title") or "",
        "subtitle": data.get("subtitle") or "",
        "author": data.get("author_name") or data.get("author") or data.get("author_brand") or "",
        "authors": data.get("authors"),
        "description": data.get("listing_description") or data.get("description") or "",
        "language": data.get("language") or "en",
        "imprint": data.get("imprint") or "",
        "isbn": data.get("isbn"),
        "isbn_option": data.get("isbn_option") or "none",
        "product_type": data.get("product_type"),
        "content_class": data.get("content_class") or data.get("kdp_content_class"),
        **(stored.get("metadata") if isinstance(stored.get("metadata"), dict) else {}),
        **(data.get("kdp_metadata") if isinstance(data.get("kdp_metadata"), dict) else {}),
        **(dict(metadata) if metadata else {}),
    }
    merged_ai = {
        **(stored.get("ai_disclosure") if isinstance(stored.get("ai_disclosure"), dict) else {}),
        **(data.get("kdp_ai_disclosure") if isinstance(data.get("kdp_ai_disclosure"), dict) else {}),
        **(dict(ai_disclosure) if ai_disclosure else {}),
    }
    return {
        "publication_format": str(fmt).strip().lower(),
        "print": merged_print,
        "metadata": merged_meta,
        "ai_disclosure": merged_ai,
    }


def _resolve_page_count(data: Mapping[str, Any], print_settings: Mapping[str, Any]) -> int | None:
    for key in ("page_count", "final_page_count", "pages"):
        if key in print_settings and print_settings.get(key) not in (None, ""):
            try:
                return int(print_settings[key])
            except (TypeError, ValueError):
                return None
    if data.get("page_count") not in (None, ""):
        try:
            return int(data["page_count"])
        except (TypeError, ValueError):
            return None
    pages = data.get("pages")
    if isinstance(pages, list) and pages:
        return len(pages)
    pdf_bytes = decode_pdf_bytes(dict(data))
    if pdf_bytes:
        try:
            import fitz  # type: ignore

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                return int(doc.page_count)
            finally:
                doc.close()
        except Exception:
            try:
                from pypdf import PdfReader  # type: ignore

                return len(PdfReader(__import__("io").BytesIO(pdf_bytes)).pages)
            except Exception:
                return None
    return None


def _qa_blocked(data: Mapping[str, Any]) -> tuple[bool, str]:
    if data.get("qa_blocked") or data.get("blocked_export"):
        return True, "qa_blocked/blocked_export flag set"
    for key in ("quality_result", "qa_result"):
        qr = data.get(key)
        if isinstance(qr, dict) and (
            qr.get("blocked_export") or qr.get("qa_blocked") or qr.get("passed") is False
        ):
            return True, f"{key} indicates failed/blocked QA"
    qa_status = str(data.get("qa_status") or "").strip().lower()
    if qa_status in {"failed", "blocked", "rejected"}:
        return True, f"qa_status={qa_status}"
    return False, ""


def _scan_placeholders(data: Mapping[str, Any]) -> list[str]:
    hits: list[str] = []
    blobs: list[str] = []
    for key in ("title", "subtitle", "listing_title", "listing_description", "description"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            blobs.append(val)
    ebook = data.get("ebook")
    if isinstance(ebook, str) and ebook.strip():
        blobs.append(ebook[:20000])
    for text in blobs:
        for pat in _PLACEHOLDER_PATTERNS:
            if pat.search(text):
                hits.append(f"{pat.pattern} in content/metadata")
                break
    return hits


def _export_hash_issues(data: Mapping[str, Any], repo_root: Path) -> list[str]:
    issues: list[str] = []
    exports = data.get("product_exports")
    if not isinstance(exports, dict):
        return issues
    files = exports.get("files") if isinstance(exports.get("files"), dict) else exports
    package_id = str(
        data.get("export_package_id") or data.get("package_id") or data.get("artifact_id") or ""
    ).strip()
    if not package_id:
        return issues
    exports_root = Path(os.environ.get("FACTORY_EXPORTS_DIR") or (repo_root / "exports"))
    folder = exports_root / package_id
    for kind in ("pdf", "zip"):
        meta = files.get(kind) if isinstance(files, dict) else None
        if not isinstance(meta, dict):
            continue
        expected = str(meta.get("sha256") or "").strip().lower()
        name = str(meta.get("name") or "").strip()
        path = folder / name if name else None
        if path is None or not path.is_file():
            # URL-only refs without local file: treat as orphan when digest-bound
            if expected or data.get("content_digest"):
                issues.append(f"missing_export_file:{kind}:{name or '(unnamed)'}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and actual != expected.lower():
            issues.append(f"sha256_mismatch:{kind}")
        if kind == "pdf" and data.get("content_digest"):
            # Optional cross-check when PDF bytes also live on the project
            pdf_bytes = decode_pdf_bytes(dict(data))
            if pdf_bytes:
                disk_digest = content_digest_from_pdf_bytes(path.read_bytes())
                if disk_digest != str(data.get("content_digest")).lower():
                    issues.append("export_pdf_digest_mismatch")
    return issues


def _token_payload(result: KdpPreflightResult, settings: Mapping[str, Any]) -> dict[str, Any]:
    # Intentionally exclude timestamps so prepare can re-validate the same
    # revision/settings without treating clock skew as a stale preflight.
    return {
        "overall": result.overall,
        "artifact_revision": result.artifact_revision,
        "content_digest": result.content_digest,
        "asset_manifest_digest": result.asset_manifest_digest,
        "publication_format": result.publication_format,
        "print": settings.get("print") or {},
        "metadata": {
            "title": (settings.get("metadata") or {}).get("title"),
            "isbn": (settings.get("metadata") or {}).get("isbn"),
            "isbn_option": (settings.get("metadata") or {}).get("isbn_option"),
            "author": (settings.get("metadata") or {}).get("author")
            or (settings.get("metadata") or {}).get("authors"),
            "description": (settings.get("metadata") or {}).get("description"),
        },
        "ai_disclosure": settings.get("ai_disclosure") or {},
        "finding_severities": sorted(
            {f"{f.rule_id}:{f.severity}" for f in result.findings}
        ),
    }


def _make_token(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run_kdp_preflight(
    project_data: Mapping[str, Any],
    *,
    print_settings: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    ai_disclosure: Mapping[str, Any] | None = None,
    publication_format: str | None = None,
    repo_root: Path | None = None,
) -> KdpPreflightResult:
    """Run all 20 KDP validation areas. Never mutates project_data."""
    data = dict(project_data or {})
    root = repo_root or Path(__file__).resolve().parents[2]
    settings = _merge_settings(
        data,
        print_settings=print_settings,
        metadata=metadata,
        ai_disclosure=ai_disclosure,
        publication_format=publication_format,
    )
    pub_fmt = settings["publication_format"]
    product_type = str(data.get("product_type") or settings["metadata"].get("product_type") or "") or None
    product_format = f"{product_type or 'unknown'}/{pub_fmt}"
    findings: list[PreflightFinding] = []

    # --- 1 Artifact state / identity ---
    artifact_state_value: str | None = None
    revision: int | None = None
    try:
        state = resolve_artifact_state(data)
        artifact_state_value = state.value
        revision = current_revision(data)
        if state is ArtifactState.DRAFT:
            _finding(
                findings,
                rule_id="KDP-ARTIFACT-DRAFT",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="artifact_state",
                explanation="Artifact is DRAFT; KDP packaging requires an approved authoritative revision.",
                required_correction="Approve the finished artifact (or open a controlled revision, finish QA, and approve) before KDP preflight readiness.",
                evidence=f"resolved_state={state.value}, revision={revision}",
            )
        else:
            _finding(
                findings,
                rule_id="KDP-ARTIFACT-STATE",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="artifact_state",
                explanation=f"Artifact state is {state.value}.",
                required_correction="None.",
                evidence=f"resolved_state={state.value}, revision={revision}",
            )
    except ArtifactStateError as exc:
        artifact_state_value = "CONFLICT"
        _finding(
            findings,
            rule_id="KDP-ARTIFACT-CONFLICT",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="artifact_state",
            explanation="Conflicting artifact state evidence blocks KDP packaging.",
            required_correction="Resolve the DRAFT/lock/approval conflict before preparing a KDP package.",
            evidence=str(exc),
        )

    content_digest = str(data.get("content_digest") or "").strip() or None
    asset_digest = str(data.get("asset_manifest_digest") or "").strip() or None
    try:
        verify_artifact_identity(data)
        if content_digest or asset_digest:
            _finding(
                findings,
                rule_id="KDP-ARTIFACT-IDENTITY",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="content_digest/asset_manifest_digest",
                explanation="Stored digests match the authoritative artifact content.",
                required_correction="None.",
                evidence=f"content_digest={content_digest}, asset_manifest_digest={asset_digest}",
            )
        elif str(product_type or "") in _PRINT_PRODUCT_TYPES or data.get("is_pdf"):
            _finding(
                findings,
                rule_id="KDP-ARTIFACT-IDENTITY-MISSING",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="content_digest/asset_manifest_digest",
                explanation="Print product is missing verified artifact digests.",
                required_correction="Generate, preview, and save so content_digest and asset_manifest_digest are stamped.",
                evidence="digests empty",
            )
    except ValueError as exc:
        _finding(
            findings,
            rule_id="KDP-ARTIFACT-IDENTITY-MISMATCH",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="content_digest/pdf_bytes",
            explanation="Artifact identity verification failed; content may be stale or tampered.",
            required_correction="Do not regenerate silently for KDP. Re-open a draft revision, rebuild deliberately, then re-approve.",
            evidence=str(exc),
        )

    # --- 2 Product QA ---
    blocked, qa_evidence = _qa_blocked(data)
    if blocked:
        _finding(
            findings,
            rule_id="KDP-PRODUCT-QA",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="qa_status/blocked_export",
            explanation="Product QA failed or export is blocked.",
            required_correction="Resolve QA failures before Prepare KDP Package.",
            evidence=qa_evidence,
        )
    else:
        _finding(
            findings,
            rule_id="KDP-PRODUCT-QA",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="qa_status",
            explanation="No QA block flags detected.",
            required_correction="None.",
            evidence=f"qa_status={data.get('qa_status')!r}",
        )

    # --- 3 Publication format support ---
    if pub_fmt == "hardcover":
        _finding(
            findings,
            rule_id="KDP-FORMAT-HARDCOVER",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="publication_format",
            explanation="Hardcover is unsupported until the full hardcover wrap specification is implemented.",
            required_correction="Choose paperback or ebook. Do not approximate hardcover geometry.",
            evidence="hardcover fail-closed policy",
        )
    elif pub_fmt not in _SUPPORTED_PUBLICATION_FORMATS:
        _finding(
            findings,
            rule_id="KDP-FORMAT-UNSUPPORTED",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="publication_format",
            explanation=f"Publication format {pub_fmt!r} is not supported for KDP preflight.",
            required_correction="Select ebook or paperback.",
            evidence=f"publication_format={pub_fmt}",
        )
    else:
        _finding(
            findings,
            rule_id="KDP-FORMAT-SUPPORT",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="publication_format",
            explanation=f"Publication format {pub_fmt} is supported.",
            required_correction="None.",
            evidence=f"publication_format={pub_fmt}",
        )

    # --- 16 Classification (needed early for ISBN/metadata) ---
    classification = classify_content(
        product_type=product_type,
        explicit_class=settings["metadata"].get("content_class")
        or data.get("content_class")
        or data.get("kdp_content_class"),
    )
    _finding(
        findings,
        rule_id="KDP-CLASSIFICATION",
        severity=SEVERITY_INFO
        if classification.content_class is not ContentClass.UNKNOWN
        else SEVERITY_WARNING,
        product_format=product_format,
        affected="content_class",
        explanation=(
            f"Classified as {classification.content_class.value}. "
            "Coloring/puzzle activity books are not treated as low-content."
        ),
        required_correction=(
            "Supply an explicit content_class if this product is low-content (planner/notebook) "
            "or confirm activity/standard classification."
            if classification.content_class is ContentClass.UNKNOWN
            else "None."
        ),
        evidence=json.dumps(classification.as_dict(), sort_keys=True),
    )

    # --- 4–10 Print geometry (paperback only; ebook skips as N/A info) ---
    print_profile_dict = None
    geometry = None
    page_count = _resolve_page_count(data, settings["print"])

    if pub_fmt == "paperback":
        print_in = dict(settings["print"])
        print_in.setdefault("binding", "paperback")
        if page_count is not None:
            print_in["page_count"] = page_count
        if str(print_in.get("binding") or "").lower() == "hardcover":
            _finding(
                findings,
                rule_id="KDP-FORMAT-HARDCOVER",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="binding",
                explanation="Hardcover binding is fail-closed until full wrap spec exists.",
                required_correction="Use paperback binding.",
                evidence=f"binding={print_in.get('binding')}",
            )
        if page_count is None:
            _finding(
                findings,
                rule_id="KDP-PAGE-COUNT-MISSING",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="page_count",
                explanation="Final page count is missing and could not be measured from the PDF.",
                required_correction="Provide page_count or ensure an authoritative PDF is present.",
                evidence="page_count unresolved",
            )
        else:
            try:
                profile = build_print_profile(print_in)
                if profile.binding is BindingType.HARDCOVER:
                    raise PrintProfileError("Hardcover fail-closed in KDP preflight")
                print_profile_dict = profile.as_dict()
                geometry = geometry_bundle(profile)
                _finding(
                    findings,
                    rule_id="KDP-TRIM-INTERIOR",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="trim/interior",
                    explanation="Trim and interior page size validated.",
                    required_correction="None.",
                    evidence=json.dumps(geometry["interior_page_size"], sort_keys=True),
                )
                _finding(
                    findings,
                    rule_id="KDP-BLEED",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="bleed",
                    explanation=f"Bleed mode {profile.bleed.value} applied.",
                    required_correction="None.",
                    evidence=f"bleed={profile.bleed.value}",
                )
                _finding(
                    findings,
                    rule_id="KDP-MARGINS-GUTTER",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="margins/gutter",
                    explanation="Outside margins and page-count gutter validated.",
                    required_correction="None.",
                    evidence=json.dumps(geometry["margins"], sort_keys=True),
                )
                _finding(
                    findings,
                    rule_id="KDP-PAGE-COUNT",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="page_count",
                    explanation=f"Final page count {profile.page_count} is within catalog range.",
                    required_correction="None.",
                    evidence=f"page_count={profile.page_count}",
                )
                _finding(
                    findings,
                    rule_id="KDP-PAPER-INK",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="paper/ink",
                    explanation="Paper and ink combination is catalog-compatible.",
                    required_correction="None.",
                    evidence=f"ink={profile.ink.value}, paper={profile.paper.value}",
                )
                _finding(
                    findings,
                    rule_id="KDP-SPINE-COVER",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="spine/cover_size",
                    explanation="Spine width and full-cover dimensions calculated from verified coefficients.",
                    required_correction="None.",
                    evidence=json.dumps(
                        {"spine": geometry["spine"], "cover_size": geometry["cover_size"]},
                        sort_keys=True,
                    ),
                )
                # Cover safe areas: not measurable here — guidance only (not a defect).
                _finding(
                    findings,
                    rule_id="KDP-COVER-SAFE-AREAS",
                    severity=SEVERITY_INFO,
                    product_format=product_format,
                    affected="cover_safe_areas",
                    explanation="Cover barcode/safe-area placement should be confirmed in Amazon Previewer (not auto-measurable here).",
                    required_correction="Confirm barcode and text clearances on the full wrap before publishing.",
                    evidence="no_automated_safe_area_measurement",
                )
            except (PrintProfileError, GeometryError, MetadataError, ValueError, TypeError) as exc:
                msg = str(exc)
                rule = "KDP-PRINT-PROFILE"
                affected = "print_profile"
                if "trim" in msg.lower():
                    rule, affected = "KDP-TRIM-INTERIOR", "trim"
                elif "bleed" in msg.lower():
                    rule, affected = "KDP-BLEED", "bleed"
                elif "gutter" in msg.lower() or "margin" in msg.lower():
                    rule, affected = "KDP-MARGINS-GUTTER", "margins/gutter"
                elif "spine" in msg.lower() or "cover" in msg.lower():
                    rule, affected = "KDP-SPINE-COVER", "spine/cover"
                elif "page count" in msg.lower() or "page_count" in msg.lower():
                    rule, affected = "KDP-PAGE-COUNT", "page_count"
                elif "paper" in msg.lower() or "ink" in msg.lower() or "color" in msg.lower():
                    rule, affected = "KDP-PAPER-INK", "paper/ink"
                _finding(
                    findings,
                    rule_id=rule,
                    severity=SEVERITY_FAIL,
                    product_format=product_format,
                    affected=affected,
                    explanation=f"Print/geometry validation failed: {msg}",
                    required_correction="Correct trim, bleed, margins, gutter, paper/ink, or page count using KDP catalog values.",
                    evidence=msg,
                )
    else:
        for rule_id, affected, explanation in (
            ("KDP-TRIM-INTERIOR", "trim", "Trim/interior checks N/A for ebook format."),
            ("KDP-BLEED", "bleed", "Bleed checks N/A for ebook format."),
            ("KDP-MARGINS-GUTTER", "margins/gutter", "Margin/gutter checks N/A for ebook format."),
            ("KDP-PAGE-COUNT", "page_count", "Print page-count catalog checks N/A for ebook format."),
            ("KDP-PAPER-INK", "paper/ink", "Paper/ink checks N/A for ebook format."),
            ("KDP-SPINE-COVER", "spine/cover", "Spine/cover wrap checks N/A for ebook format."),
            ("KDP-COVER-SAFE-AREAS", "cover_safe_areas", "Print cover safe-area checks N/A for ebook format."),
        ):
            _finding(
                findings,
                rule_id=rule_id,
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected=affected,
                explanation=explanation,
                required_correction="None for ebook format.",
                evidence=f"publication_format={pub_fmt}",
            )

    # --- 11 Fonts ---
    _finding(
        findings,
        rule_id="KDP-FONTS",
        severity=SEVERITY_INFO,
        product_format=product_format,
        affected="embedded_fonts/min_font_size",
        explanation="Embedded fonts and minimum font size are not fully measurable from current Factory metadata.",
        required_correction="Confirm fonts are embedded and body text meets KDP readability expectations in Amazon Previewer.",
        evidence="font_metrics_unavailable",
    )

    # --- 12 Images / missing assets ---
    pdf_bytes = decode_pdf_bytes(data)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_ref = (
        cover.get("local_image_path")
        or cover.get("asset_url")
        or cover.get("image_url")
        or data.get("cover_image")
        or ""
    )
    if str(product_type or "") in _PRINT_PRODUCT_TYPES or data.get("is_pdf"):
        if not pdf_bytes:
            _finding(
                findings,
                rule_id="KDP-IMAGES-PDF-MISSING",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="pdf_bytes",
                explanation="Authoritative PDF bytes are missing or unreadable.",
                required_correction="Restore the approved PDF artifact; do not invent a new one for KDP.",
                evidence="pdf_bytes empty/invalid",
            )
        else:
            _finding(
                findings,
                rule_id="KDP-IMAGES-PDF",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="pdf_bytes",
                explanation="Authoritative PDF bytes are present.",
                required_correction="None.",
                evidence=f"pdf_bytes_len={len(pdf_bytes)}",
            )
        if data.get("include_cover") in (True, "Yes", "yes", "1") and not cover_ref:
            _finding(
                findings,
                rule_id="KDP-IMAGES-COVER-MISSING",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="cover_image",
                explanation="Cover is required but no cover asset reference is present.",
                required_correction="Attach the approved cover asset.",
                evidence="include_cover set, cover_ref empty",
            )
        else:
            _finding(
                findings,
                rule_id="KDP-IMAGES-RESOLUTION",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="image_resolution",
                explanation="Per-image DPI cannot be fully proven from current metadata; confirm in Amazon Previewer.",
                required_correction="Confirm interior/cover images meet KDP print resolution guidance in Previewer.",
                evidence=f"cover_ref={cover_ref or '(none)'}",
            )
    elif product_type == "ebook":
        if not (data.get("ebook") or data.get("html") or pdf_bytes):
            _finding(
                findings,
                rule_id="KDP-IMAGES-EBOOK-MISSING",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="ebook/html/pdf",
                explanation="Ebook manuscript/export content is missing.",
                required_correction="Restore the authoritative ebook artifact.",
                evidence="ebook/html/pdf empty",
            )
        else:
            _finding(
                findings,
                rule_id="KDP-IMAGES-EBOOK",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="ebook",
                explanation="Ebook content payload is present.",
                required_correction="None.",
                evidence="ebook payload present",
            )

    # --- 13 Blank / missing / dup / misordered pages ---
    pages = data.get("pages") if isinstance(data.get("pages"), list) else None
    if pages is not None:
        ids = [str(p.get("id") or p.get("page") or idx) for idx, p in enumerate(pages) if isinstance(p, dict)]
        if len(ids) != len(set(ids)):
            _finding(
                findings,
                rule_id="KDP-PAGES-DUPLICATE",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="pages",
                explanation="Duplicate page identifiers detected.",
                required_correction="Remove or renumber duplicate pages in a new draft revision.",
                evidence=f"page_ids={ids}",
            )
        empty = [
            i
            for i, p in enumerate(pages)
            if isinstance(p, dict)
            and not (
                p.get("image")
                or p.get("image_path")
                or p.get("png")
                or p.get("content")
                or p.get("text")
            )
        ]
        if empty:
            _finding(
                findings,
                rule_id="KDP-PAGES-BLANK",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="pages",
                explanation="One or more pages appear blank/missing content.",
                required_correction="Fill or remove blank pages before KDP packaging.",
                evidence=f"blank_indexes={empty[:20]}",
            )
        else:
            _finding(
                findings,
                rule_id="KDP-PAGES-ORDER",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="pages",
                explanation="Page list present without detected blank/duplicate IDs.",
                required_correction="None.",
                evidence=f"page_count={len(pages)}",
            )
    else:
        _finding(
            findings,
            rule_id="KDP-PAGES-UNMEASURED",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="pages",
            explanation="Structured page list unavailable; confirm blank/duplicate/order visually in Amazon Previewer.",
            required_correction="Visually confirm page order and that no blank/misordered pages ship.",
            evidence="pages list absent",
        )

    # --- 14 Metadata matching ---
    meta_in = dict(settings["metadata"])
    meta_in["product_type"] = product_type
    meta_in["is_ebook"] = pub_fmt == "ebook" or product_type == "ebook"
    meta_in["binding"] = "ebook" if pub_fmt == "ebook" else settings["print"].get("binding", "paperback")
    # Do not force content_class into metadata validation — that would re-classify
    # as an "explicit" label and emit noisy warnings. Only pass caller-supplied class.
    if not meta_in.get("content_class") and not meta_in.get("kdp_content_class"):
        meta_in.pop("content_class", None)
        meta_in.pop("kdp_content_class", None)
    meta_result = validate_book_metadata(meta_in)
    project_title = str(data.get("title") or data.get("listing_title") or "").strip()
    if project_title and meta_result.title and project_title != meta_result.title:
        _finding(
            findings,
            rule_id="KDP-METADATA-TITLE-MISMATCH",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="title",
            explanation="KDP metadata title does not match the project title.",
            required_correction="Align listing title with the authoritative project title.",
            evidence=f"project_title={project_title!r}, kdp_title={meta_result.title!r}",
        )
    if not meta_result.ok:
        _finding(
            findings,
            rule_id="KDP-METADATA",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="metadata",
            explanation="Book metadata validation failed.",
            required_correction="; ".join(meta_result.errors) or "Fix metadata errors.",
            evidence=json.dumps(meta_result.as_dict(), sort_keys=True),
        )
    else:
        _finding(
            findings,
            rule_id="KDP-METADATA",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="metadata",
            explanation="Title/author metadata validated.",
            required_correction="None.",
            evidence=f"title={meta_result.title!r}, authors={list(meta_result.authors)}",
        )
    _classification_note_markers = (
        "Factory product mapped",
        "Explicit activity classification",
        "Explicit low-content classification",
        "No verified KDP mapping",
        "Missing product_type",
        "Amazon states these are not generally low-content",
    )
    for w in meta_result.warnings:
        if "ISBN" in w or "isbn" in w:
            continue  # ISBN warnings handled in area 15
        if any(m in w for m in _classification_note_markers):
            # Classification notes are informational; area 16 already reports class.
            continue
        _finding(
            findings,
            rule_id="KDP-METADATA-WARN",
            severity=SEVERITY_WARNING,
            product_format=product_format,
            affected="metadata",
            explanation=w,
            required_correction="Review and complete metadata fields as needed.",
            evidence=w,
        )

    # --- 15 ISBN ---
    isbn = meta_result.isbn
    if not isbn.ok:
        _finding(
            findings,
            rule_id="KDP-ISBN-INVALID",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="isbn",
            explanation="ISBN validation failed.",
            required_correction="; ".join(isbn.errors) or "Provide a valid caller-supplied ISBN or eligible option.",
            evidence=json.dumps(isbn.as_dict(), sort_keys=True),
        )
    else:
        _finding(
            findings,
            rule_id="KDP-ISBN",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="isbn",
            explanation="ISBN option/number accepted for this content class and format.",
            required_correction="None.",
            evidence=json.dumps(isbn.as_dict(), sort_keys=True),
        )
    for w in isbn.warnings:
        _finding(
            findings,
            rule_id="KDP-ISBN-WARN",
            severity=SEVERITY_WARNING,
            product_format=product_format,
            affected="isbn",
            explanation=w,
            required_correction="Confirm ISBN applicability for this title before publishing.",
            evidence=w,
        )

    # --- 17 AI disclosure ---
    try:
        ai_rec = build_ai_disclosure(settings["ai_disclosure"] or None)
    except AiDisclosureError as exc:
        ai_rec = None
        _finding(
            findings,
            rule_id="KDP-AI-DISCLOSURE",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="ai_disclosure",
            explanation=f"AI disclosure record invalid: {exc}",
            required_correction="Provide valid text/images/translations provenance values.",
            evidence=str(exc),
        )
    if ai_rec is not None:
        if ai_rec.errors or ai_rec.has_unknown_provenance:
            _finding(
                findings,
                rule_id="KDP-AI-DISCLOSURE",
                severity=SEVERITY_FAIL,
                product_format=product_format,
                affected="ai_disclosure",
                explanation="AI disclosure is incomplete or unknown provenance blocks readiness.",
                required_correction="Set each channel to none, ai_assisted, or ai_generated; unknown is not allowed for package readiness.",
                evidence=json.dumps(ai_rec.as_dict(), sort_keys=True),
            )
        elif ai_rec.requires_kdp_ai_generated_disclosure:
            _finding(
                findings,
                rule_id="KDP-AI-DISCLOSURE-GENERATED",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="ai_disclosure",
                explanation="AI-generated content recorded; disclosure completeness accepted for preflight.",
                required_correction="Disclose AI-generated text/images/translations in KDP as required.",
                evidence=json.dumps(ai_rec.as_dict(), sort_keys=True),
            )
        else:
            assisted = any(
                p is AiProvenance.AI_ASSISTED
                for p in (ai_rec.text, ai_rec.images, ai_rec.translations)
            )
            _finding(
                findings,
                rule_id="KDP-AI-DISCLOSURE",
                severity=SEVERITY_INFO,
                product_format=product_format,
                affected="ai_disclosure",
                explanation=(
                    "AI-assisted only (disclosure not required) recorded."
                    if assisted
                    else "No AI-generated content asserted."
                ),
                required_correction="None.",
                evidence=json.dumps(ai_rec.as_dict(), sort_keys=True),
            )
        for w in ai_rec.warnings:
            if "unknown" in w.lower():
                continue
            _finding(
                findings,
                rule_id="KDP-AI-DISCLOSURE-WARN",
                severity=SEVERITY_WARNING,
                product_format=product_format,
                affected="ai_disclosure",
                explanation=w,
                required_correction="Review AI disclosure answers before publishing.",
                evidence=w,
            )

    # --- 18 Stale/orphan/mismatch + 19 PDF/ZIP hash ---
    hash_issues = _export_hash_issues(data, root)
    if hash_issues:
        _finding(
            findings,
            rule_id="KDP-EXPORT-HASH",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="product_exports",
            explanation="Export files are missing, orphaned, or hash-mismatched versus the authoritative record.",
            required_correction="Restore the exact approved export files; do not regenerate to cure KDP preflight.",
            evidence=";".join(hash_issues),
        )
    else:
        _finding(
            findings,
            rule_id="KDP-EXPORT-HASH",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="product_exports",
            explanation="No stale/orphan/hash mismatch detected for recorded export files (or no digest-bound exports yet).",
            required_correction="None.",
            evidence=f"export_package_id={data.get('export_package_id')!r}",
        )

    # --- 20 Product-specific + placeholders ---
    placeholders = _scan_placeholders({**data, **settings["metadata"]})
    if placeholders:
        _finding(
            findings,
            rule_id="KDP-PLACEHOLDER",
            severity=SEVERITY_FAIL,
            product_format=product_format,
            affected="content/metadata",
            explanation="Placeholder or fallback text detected.",
            required_correction="Remove placeholder/fallback content before KDP packaging.",
            evidence="; ".join(placeholders[:10]),
        )

    pt = (product_type or "").lower()
    if pt == "coloring_book":
        _finding(
            findings,
            rule_id="KDP-PRODUCT-COLORING",
            severity=SEVERITY_INFO
            if classification.content_class is ContentClass.ACTIVITY
            else SEVERITY_WARNING,
            product_format=product_format,
            affected="product_type",
            explanation="Coloring books are activity products, not low-content.",
            required_correction="Do not mark as low-content unless explicitly a notebook/planner.",
            evidence=classification.content_class.value,
        )
    elif pt in {"word_search", "crossword", "math_worksheet"}:
        _finding(
            findings,
            rule_id="KDP-PRODUCT-ACTIVITY",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="product_type",
            explanation=f"{pt} is classified as an activity book for KDP ISBN/low-content rules.",
            required_correction="None.",
            evidence=classification.content_class.value,
        )
    elif pt == "ebook":
        _finding(
            findings,
            rule_id="KDP-PRODUCT-EBOOK",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="product_type",
            explanation="Ebook/nonfiction path supported; ISBN not required for ebook format.",
            required_correction="None.",
            evidence=f"publication_format={pub_fmt}",
        )
    elif pt == "planner" or classification.content_class is ContentClass.LOW_CONTENT:
        _finding(
            findings,
            rule_id="KDP-PRODUCT-LOW-CONTENT",
            severity=SEVERITY_INFO,
            product_format=product_format,
            affected="content_class",
            explanation="Low-content/planner rules apply (free KDP ISBN ineligible).",
            required_correction="Use own ISBN or publish-without where eligible.",
            evidence=classification.content_class.value,
        )
    else:
        _finding(
            findings,
            rule_id="KDP-PRODUCT-UNKNOWN",
            severity=SEVERITY_WARNING,
            product_format=product_format,
            affected="product_type",
            explanation="Product-specific KDP mapping is incomplete.",
            required_correction="Confirm product family and content class before packaging.",
            evidence=f"product_type={product_type!r}",
        )

    has_fail = any(f.severity == SEVERITY_FAIL for f in findings)
    has_warn = any(f.severity == SEVERITY_WARNING for f in findings)
    if has_fail:
        overall = RESULT_FAIL
    elif has_warn:
        overall = RESULT_WARNING
    else:
        overall = RESULT_PASS

    result = KdpPreflightResult(
        overall=overall,
        product_type=product_type,
        publication_format=pub_fmt,
        artifact_state=artifact_state_value,
        artifact_revision=revision,
        content_digest=content_digest,
        asset_manifest_digest=asset_digest,
        findings=findings,
        print_profile=print_profile_dict,
        geometry=geometry,
        metadata=meta_result.as_dict(),
        classification=classification.as_dict(),
        ai_disclosure=ai_rec.as_dict() if ai_rec is not None else None,
        preflighted_at=_utc_now(),
        warnings_require_ack=overall == RESULT_WARNING,
        package_allowed=overall == RESULT_PASS,
    )
    result.preflight_token = _make_token(_token_payload(result, settings))
    return result


def assert_prepare_kdp_package_allowed(
    project_data: Mapping[str, Any],
    *,
    preflight_token: str,
    warning_acknowledged: bool = False,
    print_settings: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    ai_disclosure: Mapping[str, Any] | None = None,
    publication_format: str | None = None,
    repo_root: Path | None = None,
) -> KdpPreflightResult:
    """Re-run preflight and enforce gate: FAIL blocked; WARNING needs ack; token must match."""
    result = run_kdp_preflight(
        project_data,
        print_settings=print_settings,
        metadata=metadata,
        ai_disclosure=ai_disclosure,
        publication_format=publication_format,
        repo_root=repo_root,
    )
    if not preflight_token or preflight_token != result.preflight_token:
        raise KdpPreflightError(
            "Stale or mismatched KDP preflight token. Re-run KDP Preflight on the current revision."
        )
    if result.overall == RESULT_FAIL:
        raise KdpPreflightError("FAIL — KDP export blocked; Prepare KDP Package cannot bypass failures.")
    if result.overall == RESULT_WARNING and not warning_acknowledged:
        raise KdpPreflightError(
            "WARNING — Human review required; acknowledge warnings before Prepare KDP Package."
        )
    # Refuse DRAFT/conflict even if somehow overall drifted
    if result.artifact_state in {None, "DRAFT", "CONFLICT"}:
        raise KdpPreflightError("KDP packaging requires APPROVED or LOCKED authoritative artifact.")
    result.package_allowed = True
    return result


def build_kdp_package_manifest(
    project_data: Mapping[str, Any],
    preflight: KdpPreflightResult,
    *,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Manifest only — does not invent a new Amazon upload format."""
    data = dict(project_data or {})
    merged = settings or _merge_settings(
        data,
        print_settings=None,
        metadata=None,
        ai_disclosure=None,
        publication_format=preflight.publication_format,
    )
    return {
        "label": "Ready for Amazon Previewer",
        "amazon_approval_claim": None,
        "note": "Ready for Amazon Previewer — never Guaranteed Amazon Approved.",
        "created_at": _utc_now(),
        "product_type": preflight.product_type,
        "publication_format": preflight.publication_format,
        "artifact_state": preflight.artifact_state,
        "artifact_revision": preflight.artifact_revision,
        "content_digest": preflight.content_digest,
        "asset_manifest_digest": preflight.asset_manifest_digest,
        "export_package_id": data.get("export_package_id") or data.get("package_id"),
        "settings": {
            "print": merged.get("print") or {},
            "metadata": merged.get("metadata") or {},
            "ai_disclosure": merged.get("ai_disclosure") or {},
        },
        "disclosure_record": preflight.ai_disclosure,
        "classification": preflight.classification,
        "print_profile": preflight.print_profile,
        "geometry": preflight.geometry,
        "rule_results": [f.as_dict() for f in preflight.findings],
        "overall": preflight.overall,
        "preflight_token": preflight.preflight_token,
        "hashes": {
            "content_digest": preflight.content_digest,
            "asset_manifest_digest": preflight.asset_manifest_digest,
            "preflight_token": preflight.preflight_token,
        },
    }
