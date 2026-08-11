"""KDP interior and cover geometry: bleed, margins, gutter, page/cover size, spine.

Sources:
- Bleed / margins / gutter:
  https://kdp.amazon.com/help/topic/GVBQ3CMEQW3W2VL6
- Cover size + spine coefficients (B&W / color):
  https://kdp.amazon.com/help/topic/G201953020
- Groundwood spine coefficient:
  https://kdp.amazon.com/help/topic/G201857950
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.kdp.print_profile import (
    BleedMode,
    InkType,
    PaperType,
    PrintProfile,
    PrintProfileError,
)
from services.kdp.sources import (
    KDP_PAPERBACK_COVER,
    KDP_PAPERBACK_SUBMISSION,
    KDP_TRIM_BLEED_MARGINS,
)

# Interior / cover bleed per edge (inches)
BLEED_IN = Decimal("0.125")  # GVBQ3CMEQW3W2VL6 / G201953020

# Outside margins (top/bottom/outside)
OUTSIDE_MARGIN_NO_BLEED_IN = Decimal("0.25")  # GVBQ3CMEQW3W2VL6
OUTSIDE_MARGIN_WITH_BLEED_IN = Decimal("0.375")  # GVBQ3CMEQW3W2VL6

# Spine text rules (G201953020): at least 79 pages; 0.0625" clearance each side
SPINE_TEXT_MIN_PAGES = 79
SPINE_TEXT_CLEARANCE_IN = Decimal("0.0625")

# Spine thickness coefficients (inches per page)
# B&W white/cream + color premium/standard: G201953020
# Groundwood: G201857950
SPINE_COEFFICIENT_IN_PER_PAGE: dict[tuple[str, str], tuple[Decimal, str]] = {
    (InkType.BLACK.value, PaperType.WHITE.value): (
        Decimal("0.002252"),
        KDP_PAPERBACK_COVER,
    ),
    (InkType.BLACK.value, PaperType.CREAM.value): (
        Decimal("0.0025"),
        KDP_PAPERBACK_COVER,
    ),
    (InkType.BLACK.value, PaperType.GROUNDWOOD.value): (
        Decimal("0.00235"),
        KDP_PAPERBACK_SUBMISSION,
    ),
    (InkType.STANDARD_COLOR.value, PaperType.WHITE.value): (
        Decimal("0.002252"),
        KDP_PAPERBACK_COVER,
    ),
    (InkType.PREMIUM_COLOR.value, PaperType.WHITE.value): (
        Decimal("0.002347"),
        KDP_PAPERBACK_COVER,
    ),
}


class GeometryError(ValueError):
    """Invalid geometry inputs or unsupported coefficient lookup."""


@dataclass(frozen=True)
class MarginRequirements:
    inside_gutter_in: Decimal
    outside_in: Decimal
    page_count: int
    bleed: BleedMode
    source: str = KDP_TRIM_BLEED_MARGINS

    def as_dict(self) -> dict[str, Any]:
        return {
            "inside_gutter_in": str(self.inside_gutter_in),
            "outside_in": str(self.outside_in),
            "page_count": self.page_count,
            "bleed": self.bleed.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class InteriorPageSize:
    width_in: Decimal
    height_in: Decimal
    trim_width_in: Decimal
    trim_height_in: Decimal
    bleed: BleedMode
    source: str = KDP_TRIM_BLEED_MARGINS

    def as_dict(self) -> dict[str, Any]:
        return {
            "width_in": str(self.width_in),
            "height_in": str(self.height_in),
            "trim_width_in": str(self.trim_width_in),
            "trim_height_in": str(self.trim_height_in),
            "bleed": self.bleed.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class SpineResult:
    width_in: Decimal
    page_count: int
    ink: str
    paper: str
    coefficient_in_per_page: Decimal
    spine_text_allowed: bool
    spine_text_clearance_in: Decimal
    source: str
    status: str = "ok"  # ok | blocked

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "width_in": str(self.width_in),
            "page_count": self.page_count,
            "ink": self.ink,
            "paper": self.paper,
            "coefficient_in_per_page": str(self.coefficient_in_per_page),
            "spine_text_allowed": self.spine_text_allowed,
            "spine_text_clearance_in": str(self.spine_text_clearance_in),
            "source": self.source,
        }


@dataclass(frozen=True)
class CoverSize:
    width_in: Decimal
    height_in: Decimal
    trim_width_in: Decimal
    trim_height_in: Decimal
    spine_width_in: Decimal
    bleed_in: Decimal
    source: str = KDP_PAPERBACK_COVER

    def as_dict(self) -> dict[str, Any]:
        return {
            "width_in": str(self.width_in),
            "height_in": str(self.height_in),
            "trim_width_in": str(self.trim_width_in),
            "trim_height_in": str(self.trim_height_in),
            "spine_width_in": str(self.spine_width_in),
            "bleed_in": str(self.bleed_in),
            "source": self.source,
            # Cover Width = Bleed + Back + Spine + Front + Bleed
            # Cover Height = Bleed + Trim Height + Bleed
            "formula": {
                "cover_width": "bleed + trim_width + spine + trim_width + bleed",
                "cover_height": "bleed + trim_height + bleed",
            },
        }


def _q(value: Decimal, places: str = "0.000001") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def interior_page_size(profile: PrintProfile) -> InteriorPageSize:
    """Manuscript page size for the selected trim and bleed mode.

    With bleed (GVBQ3CMEQW3W2VL6):
      page_width  = trim_width  + 0.125"
      page_height = trim_height + 0.25"   (= trim_height + 2 * 0.125")
    Without bleed: page size equals trim size.
    """
    tw = profile.trim.width_in
    th = profile.trim.height_in
    if profile.bleed is BleedMode.WITH_BLEED:
        return InteriorPageSize(
            width_in=_q(tw + BLEED_IN),
            height_in=_q(th + (BLEED_IN * 2)),
            trim_width_in=tw,
            trim_height_in=th,
            bleed=profile.bleed,
        )
    return InteriorPageSize(
        width_in=tw,
        height_in=th,
        trim_width_in=tw,
        trim_height_in=th,
        bleed=profile.bleed,
    )


def gutter_margin_in(page_count: int) -> Decimal:
    """Minimum inside (gutter) margin by page count (GVBQ3CMEQW3W2VL6)."""
    if page_count < 24:
        raise GeometryError(
            f"Page count {page_count} is below KDP paperback minimum 24 "
            f"(source: {KDP_TRIM_BLEED_MARGINS})"
        )
    if page_count <= 150:
        return Decimal("0.375")
    if page_count <= 300:
        return Decimal("0.5")
    if page_count <= 500:
        return Decimal("0.625")
    if page_count <= 700:
        return Decimal("0.75")
    if page_count <= 828:
        return Decimal("0.875")
    raise GeometryError(
        f"Page count {page_count} exceeds documented gutter table upper bound 828 "
        f"(source: {KDP_TRIM_BLEED_MARGINS})"
    )


def margin_requirements(profile: PrintProfile) -> MarginRequirements:
    outside = (
        OUTSIDE_MARGIN_WITH_BLEED_IN
        if profile.bleed is BleedMode.WITH_BLEED
        else OUTSIDE_MARGIN_NO_BLEED_IN
    )
    return MarginRequirements(
        inside_gutter_in=gutter_margin_in(profile.page_count),
        outside_in=outside,
        page_count=profile.page_count,
        bleed=profile.bleed,
    )


def spine_coefficient(ink: InkType | str, paper: PaperType | str) -> tuple[Decimal, str]:
    i = InkType(ink) if not isinstance(ink, InkType) else ink
    p = PaperType(paper) if not isinstance(paper, PaperType) else paper
    key = (i.value, p.value)
    found = SPINE_COEFFICIENT_IN_PER_PAGE.get(key)
    if found is None:
        raise GeometryError(
            f"No verified spine coefficient for ink={i.value}, paper={p.value}. "
            "Refusing to fabricate a coefficient."
        )
    return found


def calculate_spine(profile: PrintProfile) -> SpineResult:
    """Spine width = page_count × paper/ink coefficient (verified Amazon formulas)."""
    coeff, source = spine_coefficient(profile.ink, profile.paper)
    width = _q(Decimal(profile.page_count) * coeff)
    return SpineResult(
        width_in=width,
        page_count=profile.page_count,
        ink=profile.ink.value,
        paper=profile.paper.value,
        coefficient_in_per_page=coeff,
        spine_text_allowed=profile.page_count >= SPINE_TEXT_MIN_PAGES,
        spine_text_clearance_in=SPINE_TEXT_CLEARANCE_IN,
        source=source,
        status="ok",
    )


def cover_size(profile: PrintProfile, spine: SpineResult | None = None) -> CoverSize:
    """Full wrap cover size including bleed.

    Cover Width  = Bleed + Back + Spine + Front + Bleed
    Cover Height = Bleed + Trim Height + Bleed
    Source: https://kdp.amazon.com/help/topic/G201953020
    """
    if spine is None:
        spine = calculate_spine(profile)
    if spine.status != "ok":
        raise GeometryError("Cannot compute cover size while spine calculation is blocked")
    tw = profile.trim.width_in
    th = profile.trim.height_in
    width = _q(BLEED_IN + tw + spine.width_in + tw + BLEED_IN)
    height = _q(BLEED_IN + th + BLEED_IN)
    return CoverSize(
        width_in=width,
        height_in=height,
        trim_width_in=tw,
        trim_height_in=th,
        spine_width_in=spine.width_in,
        bleed_in=BLEED_IN,
    )


def geometry_bundle(profile: PrintProfile) -> dict[str, Any]:
    """Deterministic geometry snapshot for a validated print profile."""
    if not isinstance(profile, PrintProfile):
        raise PrintProfileError("geometry_bundle requires a PrintProfile")
    page = interior_page_size(profile)
    margins = margin_requirements(profile)
    spine = calculate_spine(profile)
    cover = cover_size(profile, spine)
    return {
        "print_profile": profile.as_dict(),
        "interior_page_size": page.as_dict(),
        "margins": margins.as_dict(),
        "spine": spine.as_dict(),
        "cover_size": cover.as_dict(),
        "constants": {
            "bleed_in": str(BLEED_IN),
            "outside_margin_no_bleed_in": str(OUTSIDE_MARGIN_NO_BLEED_IN),
            "outside_margin_with_bleed_in": str(OUTSIDE_MARGIN_WITH_BLEED_IN),
            "spine_text_min_pages": SPINE_TEXT_MIN_PAGES,
            "sources": {
                "trim_bleed_margins": KDP_TRIM_BLEED_MARGINS,
                "paperback_cover": KDP_PAPERBACK_COVER,
                "paperback_submission": KDP_PAPERBACK_SUBMISSION,
            },
        },
    }
