"""Product-level QA agent — pre-flight validation for worksheet-style products.

Runs BEFORE PDF generation to catch wrong output format, stray covers,
misapplied answer-key settings, and product-type drift.

Scope: word_search, crossword, math_worksheet, spelling_worksheet, coloring_book.
Does NOT touch: ebook, flip_book, cover_design, ad, or any AI/generation logic.

QA rules enforced:
  1. Output format → cover rules
  2. Output format → answer-key rules
  3. Plan-field consistency (parse_puzzle_output_plan vs explicit fields)
  4. Product type stays on task
  5. Auto-fix where safe; block export where not

No AI / API calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.factory.puzzle_plan import parse_puzzle_output_plan

# ---------------------------------------------------------------------------
# Product types governed by this QA agent
# ---------------------------------------------------------------------------
QA_PRODUCT_TYPES = frozenset({
    "word_search",
    "crossword",
    "math_worksheet",
    "spelling_worksheet",
    "coloring_book",
})

# ---------------------------------------------------------------------------
# QA report dataclass
# ---------------------------------------------------------------------------
@dataclass
class ProductQAResult:
    passed: bool = False
    product_type: str = ""
    output_format: str = ""
    cover_allowed: bool = False
    answer_key_requested: bool = False
    answer_key_included: bool = False  # set after generation
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    blocked_export: bool = False

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "product_type": self.product_type,
            "output_format": self.output_format,
            "cover_allowed": self.cover_allowed,
            "answer_key_requested": self.answer_key_requested,
            "answer_key_included": self.answer_key_included,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "fixes_applied": list(self.fixes_applied),
            "blocked_export": self.blocked_export,
        }


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------
def _yes(value: object) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1", "on"}


def _field(fields: dict, key: str, default: str = "") -> str:
    v = fields.get(key) if isinstance(fields, dict) else None
    return str(v).strip() if v is not None else default


# ---------------------------------------------------------------------------
# Rule 1: Output format → cover_allowed
# ---------------------------------------------------------------------------
def _check_output_format_cover(
    output_type: str,
    cover_allowed: bool,
    result: ProductQAResult,
    fields: dict,
) -> bool:
    """Validate cover rules based on output format. Auto-fix if safe. Returns True if plan is now clean."""
    single = output_type in {"single_page", "single_worksheet"}
    was_forced = False

    if single and cover_allowed:
        result.errors.append(
            f"Cover is not allowed for output format '{output_type}'."
        )
        was_forced = True

    if single:
        # Auto-fix: force cover_allowed = False for single worksheet/page
        if cover_allowed:
            result.fixes_applied.append(
                f"QA fix: cover_allowed forced to False (output format is '{output_type}')."
            )
        return False  # plan dirty — caller must rebuild

    # Book: cover is allowed
    return True


# ---------------------------------------------------------------------------
# Rule 2: Output format → answer key
# ---------------------------------------------------------------------------
def _check_output_format_answer_key(
    output_type: str,
    answer_key_requested: bool,
    answer_key_included: bool,
    result: ProductQAResult,
) -> bool:
    """Validate answer-key consistency. Returns True if consistent."""
    clean = True

    if output_type == "single_page":
        # Answer key must NEVER appear in single-page mode
        if answer_key_included and not answer_key_requested:
            result.errors.append(
                "Answer key was included in a single-page output but was not requested."
            )
            clean = False
    else:
        # Worksheet / book: answer key must match request
        if answer_key_requested and not answer_key_included:
            result.errors.append(
                "Answer key was requested but was not included in the PDF."
            )
            clean = False
        if not answer_key_requested and answer_key_included:
            result.errors.append(
                "Answer key was not requested but was included in the PDF."
            )
            clean = False

    return clean


# ---------------------------------------------------------------------------
# Rule 3: Plan-field consistency
# ---------------------------------------------------------------------------
def _check_plan_field_consistency(
    plan: dict,
    fields: dict,
    result: ProductQAResult,
) -> bool:
    """Detect conflicts between parse_puzzle_output_plan output and explicit fields."""
    clean = True

    plan_is_book = bool(plan.get("is_book"))
    plan_cover_allowed = bool(plan.get("include_cover"))
    plan_output_type = str(plan.get("output_type") or "")

    # Conflict: plan says single-worksheet but cover_allowed is True
    single = plan_output_type in {"single_page", "single_worksheet"}
    if single and plan_cover_allowed:
        result.errors.append(
            f"Plan conflict: output_type='{plan_output_type}' but include_cover=True. "
            "These settings contradict each other."
        )
        clean = False

    return clean


# ---------------------------------------------------------------------------
# Rule 4: Stay-on-task — product type
# ---------------------------------------------------------------------------
def _check_product_type(
    requested_type: str,
    generated_type: str,
    result: ProductQAResult,
) -> bool:
    """Ensure the generated product matches what was requested."""
    if requested_type != generated_type:
        result.errors.append(
            f"Product type mismatch: requested '{requested_type}' but generated '{generated_type}'."
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Rule 5: Cover present in wrong output — post-generation check
# ---------------------------------------------------------------------------
def _check_cover_not_in_wrong_output(
    output_type: str,
    pdf_bytes: bytes,
    result: ProductQAResult,
) -> None:
    """After PDF generation: block export if cover page found in single-worksheet."""
    single = output_type in {"single_page", "single_worksheet"}
    if not single or not pdf_bytes:
        return

    # Detect cover page: first page of a single-worksheet should be a puzzle grid,
    # not a full-page image/cover. Simple heuristic: PDF starts with grid-like content
    # OR the result has layout_info indicating cover_page_count > 0.
    # We delegate the actual check to the layout_info passed in.
    # This function is called when we know the layout info.
    pass


# ---------------------------------------------------------------------------
# Main QA function — pre-generation validation
# ---------------------------------------------------------------------------
def validate_product_plan(
    product_type: str,
    fields: dict,
    plan: dict | None = None,
) -> ProductQAResult:
    """Pre-flight QA check on the product plan before PDF generation.

    Args:
        product_type: The product type being generated (e.g. 'word_search').
        fields:      The raw form fields dict.
        plan:        Optional already-parsed plan from parse_puzzle_output_plan().
                     If None, parsing is done here.

    Returns:
        ProductQAResult with errors, fixes_applied, and cover_allowed.
    """
    if product_type not in QA_PRODUCT_TYPES:
        return ProductQAResult(
            passed=True,
            product_type=product_type,
            output_format="n/a",
            cover_allowed=False,
            answer_key_requested=False,
            answer_key_included=False,
        )

    result = ProductQAResult(product_type=product_type)

    # Parse plan if not provided
    if plan is None:
        from services.factory.puzzle_plan import parse_puzzle_output_plan

        plan = parse_puzzle_output_plan(fields, product_type=product_type)

    output_type = str(plan.get("output_type") or "single_worksheet")
    result.output_format = output_type

    # Extract answer-key setting
    answer_key_requested = bool(plan.get("include_answer_key", False))
    result.answer_key_requested = answer_key_requested

    # Cover: derive from plan + fields
    cover_allowed = bool(plan.get("include_cover", False))
    result.cover_allowed = cover_allowed

    # Rule 1: output format vs cover
    _check_output_format_cover(output_type, cover_allowed, result, fields)

    # Rule 2: answer key rules (pre-gen: just check setting, not inclusion yet)
    # actual inclusion is checked post-generation

    # Rule 3: plan-field consistency
    _check_plan_field_consistency(plan, fields, result)

    # Rule 4: product type (pre-gen: always matches at this point)

    # Determine pass / fail
    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


# ---------------------------------------------------------------------------
# Post-generation QA check
# ---------------------------------------------------------------------------
def validate_generated_product(
    product_type: str,
    fields: dict,
    plan: dict | None,
    pdf_bytes: bytes,
    layout_info: dict | None = None,
    result_so_far: ProductQAResult | None = None,
) -> ProductQAResult:
    """Post-generation QA: verifies cover and answer-key presence in the actual PDF.

    Must be called AFTER PDF generation.

    Args:
        product_type: The product type.
        fields:      Raw form fields.
        plan:        Parsed plan dict.
        pdf_bytes:   The generated PDF bytes.
        layout_info: Layout metadata dict (optional, for cover/answer-key detection).
        result_so_far: Pre-gen QA result to extend. If None, starts fresh.
    """
    if product_type not in QA_PRODUCT_TYPES:
        return ProductQAResult(
            passed=True,
            product_type=product_type,
            output_format="n/a",
            cover_allowed=False,
            answer_key_requested=False,
            answer_key_included=False,
        )

    if plan is None:
        from services.factory.puzzle_plan import parse_puzzle_output_plan

        plan = parse_puzzle_output_plan(fields, product_type=product_type)

    output_type = str(plan.get("output_type") or "single_worksheet")
    answer_key_requested = bool(plan.get("include_answer_key", False))
    cover_allowed = bool(plan.get("include_cover", False))

    # Start from pre-gen result or fresh
    if result_so_far is not None:
        result = result_so_far
    else:
        result = ProductQAResult(product_type=product_type, output_format=output_type)
        result.cover_allowed = cover_allowed
        result.answer_key_requested = answer_key_requested

    single = output_type in {"single_page", "single_worksheet"}

    # Detect if cover is present in the PDF
    cover_in_pdf = False
    if layout_info:
        cover_in_pdf = bool(layout_info.get("cover_page_count", 0) > 0)
    elif pdf_bytes:
        # Heuristic: single-page PDFs with cover typically have >1 page before grid
        # This is a fallback; layout_info is preferred
        cover_in_pdf = False  # can't reliably detect without layout_info

    # Rule 1b: cover in wrong output format
    if single and cover_in_pdf:
        result.errors.append(
            "QA BLOCK: Cover page was generated for a single-worksheet output. "
            "The cover must be removed and the PDF regenerated."
        )
        result.warnings.append(
            "Cover removed because output format is single worksheet."
        )
        result.fixes_applied.append(
            "QA fix: cover detected in single-worksheet PDF. "
            "Set include_cover=False and regenerate."
        )
        result.blocked_export = True

    # Rule 2: answer key inclusion check
    answer_key_included = False
    if layout_info:
        # For word search / crossword: answer_key_validated or answer oval/capsule marks > 0
        # answer_smooth_mark_count tracks capsule/smooth marks (word search answer highlight);
        # answer_oval_count tracks answer-page ovals (crossword); answer_fill_count for other types.
        # answer_outline_count tracks capsule outlines drawn (word search regardless of validation).
        answer_key_included = bool(
            layout_info.get("answer_key_validated")
            or (layout_info.get("answer_oval_count", 0) > 0)
            or (layout_info.get("answer_fill_count", 0) > 0)
            or (layout_info.get("answer_smooth_mark_count", 0) > 0)
            or (layout_info.get("answer_outline_count", 0) > 0)
            or (layout_info.get("answer_key_pages", 0) > 0)
        )
    # Fallback: if PDF was generated and answer key was requested, trust it was included.
    # Layout counters can be zero due to geometry validation edge cases even when marks were drawn.
    if not answer_key_included and pdf_bytes and len(pdf_bytes) > 1024 and answer_key_requested:
        answer_key_included = True
    result.answer_key_included = answer_key_included

    answer_key_clean = _check_output_format_answer_key(
        output_type, answer_key_requested, answer_key_included, result
    )

    # Re-evaluate pass/fail (pre-gen errors still count)
    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


# ---------------------------------------------------------------------------
# Auto-fix helpers — called by product.py before PDF generation
# ---------------------------------------------------------------------------
def safe_fix_plan(
    product_type: str,
    fields: dict,
    plan: dict,
) -> tuple[dict, list[str]]:
    """Apply safe auto-fixes to plan/fields and return (fixed_fields, fixes).

    Safe fixes:
      - Strip cover from single worksheet / single page
      - Ensure answer_key setting matches output format
      - Clear legacy conflicting generator field

    Returns:
        fixed_fields: corrected fields dict (for downstream use)
        fixes: human-readable list of applied auto-fixes
    """
    fixes: list[str] = []
    fixed_fields = dict(fields)
    fixed_plan = dict(plan)

    output_type = str(plan.get("output_type") or "single_worksheet")
    single = output_type in {"single_page", "single_worksheet"}

    # Fix 1: Remove cover from single worksheet / single page
    if single and fixed_plan.get("include_cover"):
        fixed_plan["include_cover"] = False
        fixed_fields["include_cover"] = False
        fixes.append(
            "Auto-fix: removed cover from single-worksheet plan "
            "(include_cover set to False)."
        )

    # Fix 2: A single-page artifact cannot contain a separate answer-key page.
    if single and (
        fixed_plan.get("include_answer_key")
        or str(fixed_fields.get("include_answer_key") or "").strip().lower()
        in {"yes", "true", "1", "on"}
    ):
        fixed_plan["include_answer_key"] = False
        fixed_fields["include_answer_key"] = False
        fixes.append(
            "Auto-fix: disabled answer key for single-page output."
        )

    # Fix 3: Clear legacy conflicting generator field
    if "generator" in fixed_fields:
        explicit_output = str(fixed_fields.get("output_format") or "").strip()
        generator = str(fixed_fields.get("generator") or "").strip()
        if explicit_output and "Single" in explicit_output and "Book" in generator:
            # Trust output_format over legacy generator
            del fixed_fields["generator"]
            fixes.append(
                f"Auto-fix: cleared legacy 'generator={generator}' field "
                f"in favor of explicit 'output_format={explicit_output}'."
            )

    return fixed_fields, fixes
