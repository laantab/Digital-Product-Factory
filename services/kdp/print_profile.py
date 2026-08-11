"""Authoritative KDP paperback/hardcover print-profile model.

Sources:
- Trim sizes + page-count ranges:
  https://kdp.amazon.com/help/topic/GVBQ3CMEQW3W2VL6
- Ink / paper options referenced on the same Help topic and cover Help:
  https://kdp.amazon.com/help/topic/G201953020
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from services.kdp.sources import KDP_PAPERBACK_COVER, KDP_TRIM_BLEED_MARGINS


class BindingType(str, Enum):
    PAPERBACK = "paperback"
    HARDCOVER = "hardcover"


class InkType(str, Enum):
    BLACK = "black"
    STANDARD_COLOR = "standard_color"
    PREMIUM_COLOR = "premium_color"


class PaperType(str, Enum):
    WHITE = "white"
    CREAM = "cream"
    GROUNDWOOD = "groundwood"


class BleedMode(str, Enum):
    NO_BLEED = "no_bleed"
    WITH_BLEED = "with_bleed"


@dataclass(frozen=True)
class TrimSize:
    """Trim width × height in inches (authoritative catalog entry)."""

    width_in: Decimal
    height_in: Decimal
    label: str
    is_large: bool = False

    @property
    def key(self) -> str:
        return f"{self.width_in}x{self.height_in}"


@dataclass(frozen=True)
class PageCountRange:
    min_pages: int
    max_pages: int | None  # None = not available for this combination


@dataclass(frozen=True)
class PrintProfile:
    """Resolved print profile for geometry and page-count validation."""

    binding: BindingType
    ink: InkType
    paper: PaperType
    trim: TrimSize
    bleed: BleedMode
    page_count: int
    sources: tuple[str, ...] = (KDP_TRIM_BLEED_MARGINS, KDP_PAPERBACK_COVER)

    def as_dict(self) -> dict[str, Any]:
        return {
            "binding": self.binding.value,
            "ink": self.ink.value,
            "paper": self.paper.value,
            "trim_width_in": str(self.trim.width_in),
            "trim_height_in": str(self.trim.height_in),
            "trim_label": self.trim.label,
            "is_large_trim": self.trim.is_large,
            "bleed": self.bleed.value,
            "page_count": self.page_count,
            "sources": list(self.sources),
        }


class PrintProfileError(ValueError):
    """Invalid or unsupported print-profile combination."""


def _d(value: str | int | float | Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PrintProfileError(f"Invalid decimal value: {value!r}") from exc


def _trim(width: str, height: str, *, large: bool = False) -> TrimSize:
    w = _d(width)
    h = _d(height)
    return TrimSize(width_in=w, height_in=h, label=f'{w}" x {h}"', is_large=large)


# Paperback trim catalog from KDP "Set Trim Size, Bleed, and Margins"
# (GVBQ3CMEQW3W2VL6). Large-trim threshold: width > 6.12" or height > 9".
PAPERBACK_TRIM_SIZES: tuple[TrimSize, ...] = (
    _trim("5", "8"),
    _trim("5.06", "7.81"),
    _trim("5.25", "8"),
    _trim("5.5", "8.5"),
    _trim("6", "9"),
    _trim("6.14", "9.21", large=True),
    _trim("6.69", "9.61", large=True),
    _trim("7", "10", large=True),
    _trim("7.44", "9.69", large=True),
    _trim("7.5", "9.25", large=True),
    _trim("8", "10", large=True),
    _trim("8.25", "6", large=True),
    _trim("8.25", "8.25", large=True),
    _trim("8.5", "8.5", large=True),
    _trim("8.5", "11", large=True),
    _trim("8.27", "11.69", large=True),
    # Additional paperback sizes listed on the same Help topic
    _trim("4.06", "7.17"),
    _trim("4.13", "6.81"),
    _trim("4.41", "6.85"),
    _trim("5", "7.4"),
    _trim("5.04", "7.17"),
    _trim("5.83", "8.27"),
    _trim("5.98", "8.58"),
    _trim("5.98", "8.94"),
    _trim("7.17", "10.12", large=True),
    _trim("7.17", "8.11", large=True),
    _trim("8.27", "10.12", large=True),
)

HARDCOVER_TRIM_SIZES: tuple[TrimSize, ...] = (
    _trim("5.5", "8.5"),
    _trim("6", "9"),
    _trim("6.14", "9.21", large=True),
    _trim("7", "10", large=True),
    _trim("8.25", "11", large=True),
)

_TRIM_INDEX: dict[tuple[str, str], TrimSize] = {
    (str(t.width_in), str(t.height_in)): t for t in PAPERBACK_TRIM_SIZES
}
for t in HARDCOVER_TRIM_SIZES:
    _TRIM_INDEX.setdefault((str(t.width_in), str(t.height_in)), t)


def _range(min_pages: int, max_pages: int | None) -> PageCountRange:
    return PageCountRange(min_pages=min_pages, max_pages=max_pages)


def _default_bw_white() -> PageCountRange:
    return _range(24, 828)


def _default_bw_cream() -> PageCountRange:
    return _range(24, 776)


def _default_bw_groundwood() -> PageCountRange:
    return _range(24, 812)


def _default_std_color() -> PageCountRange:
    return _range(72, 600)


def _default_prem_color() -> PageCountRange:
    return _range(24, 828)


# Page-count matrix keyed by (binding, ink, paper, trim_key).
# Values taken from GVBQ3CMEQW3W2VL6 tables. Combinations marked unavailable
# use max_pages=None.
def _build_page_count_matrix() -> dict[tuple[str, str, str, str], PageCountRange]:
    matrix: dict[tuple[str, str, str, str], PageCountRange] = {}

    def put(
        binding: BindingType,
        ink: InkType,
        paper: PaperType,
        trim: TrimSize,
        rng: PageCountRange,
    ) -> None:
        matrix[(binding.value, ink.value, paper.value, trim.key)] = rng

    # Common paperback rows (first table on Help topic)
    common_pb = [
        _trim("5", "8"),
        _trim("5.06", "7.81"),
        _trim("5.25", "8"),
        _trim("5.5", "8.5"),
        _trim("6", "9"),
        _trim("6.14", "9.21", large=True),
        _trim("6.69", "9.61", large=True),
        _trim("7", "10", large=True),
        _trim("7.44", "9.69", large=True),
        _trim("7.5", "9.25", large=True),
        _trim("8", "10", large=True),
        _trim("4.06", "7.17"),
        _trim("4.13", "6.81"),
        _trim("4.41", "6.85"),
        _trim("5", "7.4"),
        _trim("5.04", "7.17"),
        _trim("5.83", "8.27"),
        _trim("5.98", "8.58"),
        _trim("5.98", "8.94"),
        _trim("7.17", "10.12", large=True),
        _trim("7.17", "8.11", large=True),
    ]
    for trim in common_pb:
        put(BindingType.PAPERBACK, InkType.BLACK, PaperType.WHITE, trim, _default_bw_white())
        put(BindingType.PAPERBACK, InkType.BLACK, PaperType.CREAM, trim, _default_bw_cream())
        put(
            BindingType.PAPERBACK,
            InkType.BLACK,
            PaperType.GROUNDWOOD,
            trim,
            _default_bw_groundwood(),
        )
        put(
            BindingType.PAPERBACK,
            InkType.STANDARD_COLOR,
            PaperType.WHITE,
            trim,
            _default_std_color(),
        )
        put(
            BindingType.PAPERBACK,
            InkType.PREMIUM_COLOR,
            PaperType.WHITE,
            trim,
            _default_prem_color(),
        )

    # Reduced max page counts for selected large trims
    special_pb = {
        "8.25x6": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 800),
                PaperType.CREAM: _range(24, 750),
                PaperType.GROUNDWOOD: _range(24, 784),
            },
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, 600)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 800)},
        },
        "8.25x8.25": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 800),
                PaperType.CREAM: _range(24, 750),
                PaperType.GROUNDWOOD: _range(24, 784),
            },
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, 600)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 800)},
        },
        "8.5x8.5": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 590),
                PaperType.CREAM: _range(24, 550),
                PaperType.GROUNDWOOD: _range(24, 578),
            },
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, 600)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 590)},
        },
        "8.5x11": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 590),
                PaperType.CREAM: _range(24, 550),
                PaperType.GROUNDWOOD: _range(24, 578),
            },
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, 600)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 590)},
        },
        "8.27x11.69": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 780),
                PaperType.CREAM: _range(24, 730),
                PaperType.GROUNDWOOD: _range(24, 764),
            },
            # Standard color not available for this trim on Help table
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, None)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 590)},
        },
        "8.27x10.12": {
            InkType.BLACK: {
                PaperType.WHITE: _range(24, 780),
                PaperType.CREAM: _range(24, 730),
                PaperType.GROUNDWOOD: _range(24, 764),
            },
            InkType.STANDARD_COLOR: {PaperType.WHITE: _range(72, 600)},
            InkType.PREMIUM_COLOR: {PaperType.WHITE: _range(24, 780)},
        },
    }
    for key, by_ink in special_pb.items():
        w_s, h_s = key.split("x", 1)
        trim = lookup_trim(w_s, h_s)
        for ink, by_paper in by_ink.items():
            for paper, rng in by_paper.items():
                put(BindingType.PAPERBACK, ink, paper, trim, rng)

    # Hardcover (GVBQ3CMEQW3W2VL6): groundwood / standard color unavailable
    hc_range = _range(75, 550)
    hc_unavailable = _range(75, None)
    for trim in HARDCOVER_TRIM_SIZES:
        put(BindingType.HARDCOVER, InkType.BLACK, PaperType.WHITE, trim, hc_range)
        put(BindingType.HARDCOVER, InkType.BLACK, PaperType.CREAM, trim, hc_range)
        put(
            BindingType.HARDCOVER,
            InkType.BLACK,
            PaperType.GROUNDWOOD,
            trim,
            hc_unavailable,
        )
        put(
            BindingType.HARDCOVER,
            InkType.STANDARD_COLOR,
            PaperType.WHITE,
            trim,
            hc_unavailable,
        )
        put(
            BindingType.HARDCOVER,
            InkType.PREMIUM_COLOR,
            PaperType.WHITE,
            trim,
            hc_range,
        )

    return matrix


def lookup_trim(width_in: str | Decimal, height_in: str | Decimal) -> TrimSize:
    key = (str(_d(width_in)), str(_d(height_in)))
    trim = _TRIM_INDEX.get(key)
    if trim is None:
        raise PrintProfileError(
            f"Trim size {key[0]}\" x {key[1]}\" is not in the KDP catalog "
            f"(source: {KDP_TRIM_BLEED_MARGINS})"
        )
    return trim


PAGE_COUNT_MATRIX = _build_page_count_matrix()


def page_count_range(
    binding: BindingType | str,
    ink: InkType | str,
    paper: PaperType | str,
    trim: TrimSize,
) -> PageCountRange:
    b = BindingType(binding) if not isinstance(binding, BindingType) else binding
    i = InkType(ink) if not isinstance(ink, InkType) else ink
    p = PaperType(paper) if not isinstance(paper, PaperType) else paper
    key = (b.value, i.value, p.value, trim.key)
    rng = PAGE_COUNT_MATRIX.get(key)
    if rng is None:
        raise PrintProfileError(
            f"No page-count range for binding={b.value}, ink={i.value}, "
            f"paper={p.value}, trim={trim.key} (source: {KDP_TRIM_BLEED_MARGINS})"
        )
    return rng


def validate_page_count(profile: PrintProfile) -> None:
    rng = page_count_range(profile.binding, profile.ink, profile.paper, profile.trim)
    if rng.max_pages is None:
        raise PrintProfileError(
            f"Combination binding={profile.binding.value}, ink={profile.ink.value}, "
            f"paper={profile.paper.value}, trim={profile.trim.key} is not available "
            f"(source: {KDP_TRIM_BLEED_MARGINS})"
        )
    if profile.page_count < rng.min_pages or profile.page_count > rng.max_pages:
        raise PrintProfileError(
            f"Page count {profile.page_count} outside allowed range "
            f"{rng.min_pages}-{rng.max_pages} for {profile.trim.key} / "
            f"{profile.ink.value} / {profile.paper.value} "
            f"(source: {KDP_TRIM_BLEED_MARGINS})"
        )


def _parse_enum(enum_cls: type[Enum], value: Any, field: str) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        raise PrintProfileError(f"Missing required field: {field}")
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return enum_cls(text)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum_cls)
        raise PrintProfileError(f"Invalid {field}={value!r}; allowed: {allowed}") from exc


def build_print_profile(data: Mapping[str, Any]) -> PrintProfile:
    """Build and validate a print profile from a plain mapping.

    Expected keys: binding, ink, paper, trim_width_in, trim_height_in,
    bleed (or has_bleed), page_count.
    """
    binding = _parse_enum(BindingType, data.get("binding", "paperback"), "binding")
    ink = _parse_enum(InkType, data.get("ink"), "ink")
    paper = _parse_enum(PaperType, data.get("paper"), "paper")

    # Color interiors use white paper on KDP Help tables.
    if ink in (InkType.STANDARD_COLOR, InkType.PREMIUM_COLOR) and paper != PaperType.WHITE:
        raise PrintProfileError(
            "Standard/premium color ink is cataloged with white paper only "
            f"(source: {KDP_TRIM_BLEED_MARGINS})"
        )
    if ink is InkType.BLACK and paper not in (
        PaperType.WHITE,
        PaperType.CREAM,
        PaperType.GROUNDWOOD,
    ):
        raise PrintProfileError(f"Unsupported paper for black ink: {paper.value}")

    if "trim_width_in" not in data or "trim_height_in" not in data:
        raise PrintProfileError("trim_width_in and trim_height_in are required")
    trim = lookup_trim(data["trim_width_in"], data["trim_height_in"])
    if binding is BindingType.HARDCOVER and trim.key not in {t.key for t in HARDCOVER_TRIM_SIZES}:
        raise PrintProfileError(
            f"Trim {trim.key} is not a hardcover option (source: {KDP_TRIM_BLEED_MARGINS})"
        )

    if "bleed" in data:
        bleed = _parse_enum(BleedMode, data.get("bleed"), "bleed")
    else:
        has_bleed = data.get("has_bleed")
        if has_bleed is None:
            raise PrintProfileError("bleed or has_bleed is required")
        bleed = BleedMode.WITH_BLEED if bool(has_bleed) else BleedMode.NO_BLEED

    try:
        page_count = int(data["page_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PrintProfileError("page_count must be an integer") from exc
    if page_count < 1:
        raise PrintProfileError("page_count must be >= 1")

    profile = PrintProfile(
        binding=binding,  # type: ignore[arg-type]
        ink=ink,  # type: ignore[arg-type]
        paper=paper,  # type: ignore[arg-type]
        trim=trim,
        bleed=bleed,  # type: ignore[arg-type]
        page_count=page_count,
    )
    validate_page_count(profile)
    return profile
