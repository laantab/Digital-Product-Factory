"""Book metadata and ISBN validation for KDP foundations (Pass 1).

ISBN rules (Amazon Help):
- ISBN is a unique 13-digit number, typically starting with 978 or 979
  https://kdp.amazon.com/help/topic/G201834170
- Low-content books may publish without an ISBN or use a purchaser-owned ISBN;
  they are not eligible for a free KDP ISBN
  https://kdp.amazon.com/help/topic/GGE5T76TWKA85DJM
  https://kdp.amazon.com/en_US/help/topic/GTJ8LBXL6Z4WV5QX
- eBooks do not require an ISBN on KDP
- This module validates caller-supplied ISBN strings; it never invents ISBNs.

Check-digit arithmetic follows ISO 2108 (ISBN-13).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from services.kdp.classification import ContentClass, classify_content
from services.kdp.sources import (
    ISO_2108_ISBN,
    KDP_GET_ISBN,
    KDP_ISBN_IMPRINT,
    KDP_LOW_CONTENT_BOOKS,
)


class IsbnOption(str, Enum):
    NONE = "none"  # not provided / not applicable
    OWN = "own"  # publisher-owned ISBN (caller-supplied)
    KDP_FREE = "kdp_free"  # free KDP ISBN (eligibility only; no number invented)
    PUBLISH_WITHOUT = "publish_without"  # low-content option


class MetadataError(ValueError):
    """Invalid book metadata or ISBN."""


@dataclass(frozen=True)
class IsbnValidationResult:
    ok: bool
    normalized: str | None
    option: IsbnOption
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source: str = KDP_ISBN_IMPRINT

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "normalized": self.normalized,
            "option": self.option.value,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "source": self.source,
            "check_digit_standard": ISO_2108_ISBN,
        }


@dataclass(frozen=True)
class MetadataValidationResult:
    ok: bool
    title: str
    subtitle: str
    authors: tuple[str, ...]
    description: str
    language: str
    imprint: str
    isbn: IsbnValidationResult
    content_class: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "title": self.title,
            "subtitle": self.subtitle,
            "authors": list(self.authors),
            "description": self.description,
            "language": self.language,
            "imprint": self.imprint,
            "isbn": self.isbn.as_dict(),
            "content_class": self.content_class,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def isbn13_check_digit(body12: str) -> str:
    """Return ISO 2108 ISBN-13 check digit for the first 12 digits."""
    if len(body12) != 12 or not body12.isdigit():
        raise MetadataError("ISBN-13 body must be exactly 12 digits")
    total = 0
    for idx, ch in enumerate(body12):
        n = int(ch)
        total += n if idx % 2 == 0 else n * 3
    return str((10 - (total % 10)) % 10)


def normalize_isbn(raw: str | None) -> str | None:
    """Normalize a caller-supplied ISBN; returns None if empty.

    Accepts ISBN-13 with optional hyphens/spaces. Does not generate values.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Reject obvious placeholders / invented markers
    lowered = text.lower()
    if lowered in {"tbd", "n/a", "na", "none", "null", "generate", "auto"}:
        raise MetadataError("ISBN must be caller-supplied; refusing placeholder/invented values")
    compact = text.replace("-", "").replace(" ", "")
    if compact.lower().startswith("isbn"):
        compact = compact[4:]
    digits = _digits_only(compact)
    if len(digits) == 10:
        # Convert ISBN-10 to ISBN-13 (978 + first 9 + new check digit) for validation path
        body12 = "978" + digits[:9]
        return body12 + isbn13_check_digit(body12)
    if len(digits) == 13:
        return digits
    raise MetadataError("ISBN must be 10 or 13 digits (hyphens/spaces allowed)")


def validate_isbn13(isbn: str) -> None:
    if len(isbn) != 13 or not isbn.isdigit():
        raise MetadataError("ISBN-13 must be 13 digits")
    if not (isbn.startswith("978") or isbn.startswith("979")):
        raise MetadataError(
            f"ISBN-13 must start with 978 or 979 (source: {KDP_ISBN_IMPRINT})"
        )
    expected = isbn13_check_digit(isbn[:12])
    if isbn[-1] != expected:
        raise MetadataError(
            f"ISBN-13 check digit mismatch (expected {expected}, got {isbn[-1]}; "
            f"{ISO_2108_ISBN})"
        )


def validate_isbn(
    *,
    isbn: str | None = None,
    option: IsbnOption | str = IsbnOption.NONE,
    content_class: ContentClass | str | None = None,
    binding: str | None = "paperback",
    is_ebook: bool = False,
) -> IsbnValidationResult:
    """Validate ISBN option + optional caller-supplied number. Never invents an ISBN."""
    opt = IsbnOption(option) if not isinstance(option, IsbnOption) else option
    errors: list[str] = []
    warnings: list[str] = []

    cls: ContentClass | None
    if content_class is None:
        cls = None
    elif isinstance(content_class, ContentClass):
        cls = content_class
    else:
        cls = ContentClass(str(content_class))

    if opt is IsbnOption.KDP_FREE:
        if cls is ContentClass.LOW_CONTENT:
            errors.append(
                "Low-content books are not eligible for a free KDP ISBN "
                f"(source: {KDP_LOW_CONTENT_BOOKS} / {KDP_GET_ISBN})"
            )
        if isbn:
            errors.append(
                "kdp_free option must not invent or attach a fabricated ISBN number; "
                "omit isbn until KDP assigns one"
            )
        return IsbnValidationResult(
            ok=not errors,
            normalized=None,
            option=opt,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    if opt is IsbnOption.PUBLISH_WITHOUT:
        if cls is not ContentClass.LOW_CONTENT:
            errors.append(
                "publish_without ISBN is a low-content option "
                f"(source: {KDP_LOW_CONTENT_BOOKS})"
            )
        if isbn:
            errors.append("publish_without must not include an ISBN value")
        return IsbnValidationResult(
            ok=not errors,
            normalized=None,
            option=opt,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    if opt is IsbnOption.NONE:
        if isbn:
            errors.append("isbn provided but option is none")
        elif not is_ebook and cls is not ContentClass.LOW_CONTENT and binding in {
            "paperback",
            "hardcover",
        }:
            # Print books require an ISBN unless low-content publish-without
            warnings.append(
                "Paperback/hardcover titles generally require an ISBN unless publishing "
                f"low-content without an ISBN (source: {KDP_ISBN_IMPRINT})"
            )
        return IsbnValidationResult(
            ok=not errors,
            normalized=None,
            option=opt,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # OWN
    if not isbn:
        errors.append("own ISBN option requires a caller-supplied ISBN (never invented)")
        return IsbnValidationResult(
            ok=False,
            normalized=None,
            option=opt,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    try:
        normalized = normalize_isbn(isbn)
        if normalized is None:
            raise MetadataError("own ISBN option requires a caller-supplied ISBN")
        validate_isbn13(normalized)
    except MetadataError as exc:
        errors.append(str(exc))
        return IsbnValidationResult(
            ok=False,
            normalized=None,
            option=opt,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
    return IsbnValidationResult(
        ok=True,
        normalized=normalized,
        option=opt,
        errors=(),
        warnings=tuple(warnings),
    )


def _authors_from(data: Mapping[str, Any]) -> tuple[str, ...]:
    raw = data.get("authors")
    if raw is None and data.get("author"):
        raw = [data.get("author")]
    if raw is None:
        return ()
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    if isinstance(raw, (list, tuple)):
        out = tuple(str(a).strip() for a in raw if str(a).strip())
        return out
    raise MetadataError("authors must be a string or list of strings")


def validate_book_metadata(data: Mapping[str, Any]) -> MetadataValidationResult:
    """Validate listing metadata + ISBN policy. Pure; does not mutate projects."""
    errors: list[str] = []
    warnings: list[str] = []

    title = str(data.get("title") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    description = str(data.get("description") or data.get("listing_description") or "").strip()
    language = str(data.get("language") or "en").strip() or "en"
    imprint = str(data.get("imprint") or "").strip()
    try:
        authors = _authors_from(data)
    except MetadataError as exc:
        authors = ()
        errors.append(str(exc))

    if not title:
        errors.append("title is required")
    if not authors:
        errors.append("at least one author is required")
    if not description:
        warnings.append("description is empty")

    product_type = data.get("product_type")
    classification = classify_content(
        product_type=str(product_type) if product_type is not None else None,
        explicit_class=data.get("content_class") or data.get("kdp_content_class"),
    )

    is_ebook = bool(data.get("is_ebook")) or str(product_type or "").lower() == "ebook"
    binding = str(data.get("binding") or ("ebook" if is_ebook else "paperback")).lower()

    option_raw = data.get("isbn_option") or data.get("isbn_mode") or "none"
    try:
        option = IsbnOption(str(option_raw).strip().lower())
    except ValueError:
        errors.append(f"Invalid isbn_option={option_raw!r}")
        option = IsbnOption.NONE

    isbn_result = validate_isbn(
        isbn=data.get("isbn"),
        option=option,
        content_class=classification.content_class,
        binding=binding,
        is_ebook=is_ebook,
    )
    errors.extend(isbn_result.errors)
    warnings.extend(isbn_result.warnings)
    warnings.extend(classification.notes)

    if option is IsbnOption.OWN and imprint == "":
        warnings.append(
            "Own ISBN typically requires a registered imprint name "
            f"(source: {KDP_GET_ISBN})"
        )
    if len(imprint) > 100:
        errors.append("imprint exceeds 100-character KDP field limit")

    return MetadataValidationResult(
        ok=not errors,
        title=title,
        subtitle=subtitle,
        authors=authors,
        description=description,
        language=language,
        imprint=imprint,
        isbn=isbn_result,
        content_class=classification.content_class.value,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
