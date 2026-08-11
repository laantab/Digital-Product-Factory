"""KDP foundations (Pass 1): print profile, geometry, metadata, classification, AI disclosure.

Pure computation/validation only. No route wiring, no export-blocking preflight UI,
no mutation of legacy/locked artifacts.
"""
from __future__ import annotations

from services.kdp.ai_disclosure import (
    AiContentKind,
    AiDisclosureError,
    AiDisclosureRecord,
    AiProvenance,
    build_ai_disclosure,
)
from services.kdp.classification import (
    ClassificationResult,
    ContentClass,
    classify_content,
)
from services.kdp.geometry import (
    BLEED_IN,
    CoverSize,
    GeometryError,
    InteriorPageSize,
    MarginRequirements,
    SpineResult,
    calculate_spine,
    cover_size,
    geometry_bundle,
    gutter_margin_in,
    interior_page_size,
    margin_requirements,
    spine_coefficient,
)
from services.kdp.metadata import (
    IsbnOption,
    IsbnValidationResult,
    MetadataError,
    MetadataValidationResult,
    isbn13_check_digit,
    normalize_isbn,
    validate_book_metadata,
    validate_isbn,
    validate_isbn13,
)
from services.kdp.print_profile import (
    BleedMode,
    BindingType,
    InkType,
    PaperType,
    PrintProfile,
    PrintProfileError,
    TrimSize,
    build_print_profile,
    lookup_trim,
    page_count_range,
    validate_page_count,
)
from services.kdp.sources import SOURCE_INDEX

__all__ = [
    "SOURCE_INDEX",
    "AiContentKind",
    "AiDisclosureError",
    "AiDisclosureRecord",
    "AiProvenance",
    "BLEED_IN",
    "BleedMode",
    "BindingType",
    "ClassificationResult",
    "ContentClass",
    "CoverSize",
    "GeometryError",
    "InkType",
    "InteriorPageSize",
    "IsbnOption",
    "IsbnValidationResult",
    "MarginRequirements",
    "MetadataError",
    "MetadataValidationResult",
    "PaperType",
    "PrintProfile",
    "PrintProfileError",
    "SpineResult",
    "TrimSize",
    "build_ai_disclosure",
    "build_print_profile",
    "calculate_spine",
    "classify_content",
    "cover_size",
    "geometry_bundle",
    "gutter_margin_in",
    "interior_page_size",
    "isbn13_check_digit",
    "lookup_trim",
    "margin_requirements",
    "normalize_isbn",
    "page_count_range",
    "spine_coefficient",
    "validate_book_metadata",
    "validate_isbn",
    "validate_isbn13",
    "validate_page_count",
]
