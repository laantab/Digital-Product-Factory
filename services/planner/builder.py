"""Deterministic page planner for the Faith Planner and Budget Planner.

No AI call happens here. The same request always produces the same page list,
which is what makes the product testable and what lets the Editor-in-Chief
reason about a page count that was declared before the PDF existed.

The planner emits a list of `PlannerPage` records; `renderer.py` knows how to
draw each `kind`. Keeping the two apart means a layout change never silently
changes what the book contains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.planner import content as C

FAITH = "faith_planner"
BUDGET = "budget_planner"

PLANNER_TYPES = (FAITH, BUDGET)

PLANNER_LABELS = {
    FAITH: "Faith Planner",
    BUDGET: "Budget Planner",
}

# Cover palettes. Deep, printable, and distinct from each other so two planners
# on the same shelf are not the same book in two fonts.
PALETTES = {
    FAITH: {
        "cover_bg": (0.286, 0.106, 0.106),      # deep claret
        "cover_accent": (0.816, 0.549, 0.153),  # warm gold
        "cover_text": (1.0, 1.0, 1.0),
        "rule": (0.498, 0.184, 0.184),
        "band": (0.973, 0.957, 0.933),
        "head_text": (0.286, 0.106, 0.106),
    },
    BUDGET: {
        "cover_bg": (0.043, 0.235, 0.216),      # deep teal
        "cover_accent": (0.910, 0.788, 0.404),  # brass
        "cover_text": (1.0, 1.0, 1.0),
        "rule": (0.106, 0.373, 0.345),
        "band": (0.941, 0.964, 0.957),
        "head_text": (0.043, 0.235, 0.216),
    },
}

MIN_PAGES = 12
MAX_PAGES = 200
DEFAULT_PAGES = {FAITH: 60, BUDGET: 60}


@dataclass
class PlannerPage:
    kind: str
    title: str = ""
    subtitle: str = ""
    spec: dict[str, Any] = field(default_factory=dict)
    toc_entry: str = ""       # "" means the page is not listed in the contents
    structural: bool = False  # front/back matter


@dataclass
class PlannerRequest:
    planner_type: str = FAITH
    title: str = ""
    subtitle: str = ""
    owner_line: str = ""
    theme: str = ""
    audience: str = ""
    pages: int = 60
    page_size: str = "US Letter"
    include_cover: bool = True
    include_toc: bool = True
    include_notes: bool = True
    include_habit_tracker: bool = True
    include_calendar: bool = True
    include_reflection: bool = True
    seed: int | None = None


@dataclass
class PlannerPlan:
    planner_type: str
    title: str
    subtitle: str
    pages: list[PlannerPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def clamp_pages(value: Any, planner_type: str) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        n = DEFAULT_PAGES.get(planner_type, 60)
    return max(MIN_PAGES, min(n, MAX_PAGES))


def default_title(planner_type: str, theme: str = "") -> str:
    base = PLANNER_LABELS.get(planner_type, "Planner")
    theme = (theme or "").strip()
    return f"{theme} {base}".strip() if theme else base


def default_subtitle(planner_type: str) -> str:
    if planner_type == FAITH:
        return "An undated devotional planner for daily reading, prayer, and reflection"
    return "An undated worksheet system for budgeting, tracking, and paying down debt"


# --------------------------------------------------------------------------- #
# Front matter shared by both planners
# --------------------------------------------------------------------------- #
def _front_matter(req: PlannerRequest, how_to: list[tuple[str, str]],
                  disclaimer: str = "") -> list[PlannerPage]:
    pages: list[PlannerPage] = []
    if req.include_cover:
        pages.append(PlannerPage(
            kind="cover", title=req.title, subtitle=req.subtitle,
            spec={
                "owner_line": req.owner_line,
                "planner_type": req.planner_type,
                "eyebrow": (req.audience or "UNDATED EDITION").strip().upper(),
                # Filled in once the final page count is known.
                "caption": "",
            },
            structural=True))
    pages.append(PlannerPage(
        kind="ownership", title=req.title, subtitle=req.subtitle,
        spec={"disclaimer": disclaimer}, structural=True))
    if req.include_toc:
        pages.append(PlannerPage(kind="toc", title="Table of Contents", structural=True))
    pages.append(PlannerPage(
        kind="prose", title="How to Use This Planner",
        spec={"sections": how_to}, toc_entry="How to Use This Planner"))
    return pages


def _notes_pages(count: int, label: str = "Notes") -> list[PlannerPage]:
    return [
        PlannerPage(kind="lined_notes", title=label,
                    spec={"lines": 26},
                    toc_entry=label if i == 0 else "")
        for i in range(count)
    ]


# --------------------------------------------------------------------------- #
# Faith Planner
# --------------------------------------------------------------------------- #
def _faith_cycle(week_no: int, plan_row: tuple[str, str, str]) -> list[PlannerPage]:
    """One repeating unit: a weekly spread plus five daily study pages."""
    season, reference, gist = plan_row
    out = [
        PlannerPage(
            kind="faith_weekly",
            title=f"Week {week_no}",
            subtitle=f"{season} - {gist}",
            spec={
                "reference": reference,
                "prayer_categories": list(C.FAITH_PRAYER_CATEGORIES),
            },
            toc_entry=f"Week {week_no}: {reference}",
        )
    ]
    for day in range(1, 6):
        out.append(PlannerPage(
            kind="faith_daily",
            title=f"Week {week_no} - Day {day}",
            spec={"prompts": list(C.FAITH_DAILY_PROMPTS), "reference": reference},
        ))
    return out


def build_faith_pages(req: PlannerRequest) -> tuple[list[PlannerPage], list[str]]:
    warnings: list[str] = []
    pages = _front_matter(req, C.FAITH_HOW_TO_USE)

    pages.append(PlannerPage(
        kind="reading_plan", title="52-Week Reading Plan",
        subtitle="References only - read in the translation you already trust",
        spec={"rows": list(C.FAITH_READING_PLAN)},
        toc_entry="52-Week Reading Plan"))

    pages.append(PlannerPage(
        kind="prose", title="Reading a Passage in Context",
        spec={"sections": C.FAITH_CONTEXT_METHOD},
        toc_entry="Reading a Passage in Context"))

    pages.append(PlannerPage(
        kind="prose", title="Praying on the Days You Do Not Feel Like It",
        spec={"sections": C.FAITH_PRAYER_METHOD},
        toc_entry="Praying on the Days You Do Not Feel Like It"))

    pages.append(PlannerPage(
        kind="prose", title="How to Memorise One Verse a Month",
        spec={"sections": C.FAITH_MEMORY_METHOD},
        toc_entry="How to Memorise One Verse a Month"))

    pages.append(PlannerPage(
        kind="open_table", title="Prayer Log",
        subtitle="Record what you asked, and what actually happened",
        spec={
            "columns": [("Date", 0.12), ("Who / what I am praying for", 0.44),
                        ("Answered on", 0.14), ("What changed", 0.30)],
            "rows": 22,
        },
        toc_entry="Prayer Log"))

    pages.append(PlannerPage(
        kind="open_table", title="Scripture Memory Cards",
        subtitle="One reference a month, written out by hand three times",
        spec={
            "columns": [("Month", 0.16), ("Reference", 0.22),
                        ("Written 1 / 2 / 3", 0.22), ("Recalled from memory on", 0.40)],
            "rows": 12,
        },
        toc_entry="Scripture Memory Cards"))

    pages.append(PlannerPage(
        kind="open_table", title="Sermon and Teaching Notes",
        subtitle="Date, speaker, passage, and the one point you want to keep",
        spec={
            "columns": [("Date", 0.12), ("Speaker", 0.22),
                        ("Passage", 0.20), ("The one point I want to keep", 0.46)],
            "rows": 20,
        },
        toc_entry="Sermon and Teaching Notes"))

    if req.include_calendar:
        pages.append(PlannerPage(
            kind="calendar_month", title="Monthly Overview",
            subtitle="Undated - write the month and the starting weekday yourself",
            spec={}, toc_entry="Monthly Overview"))

    if req.include_habit_tracker:
        pages.append(PlannerPage(
            kind="habit_tracker", title="Spiritual Habit Tracker",
            subtitle="One month, seven habits - shade the square, do not score yourself",
            spec={"habits": list(C.FAITH_HABITS), "days": 31},
            toc_entry="Spiritual Habit Tracker"))

    if req.include_reflection:
        pages.append(PlannerPage(
            kind="prompt_page", title="Monthly Reflection",
            subtitle="Read back through your own entries before you answer these",
            spec={"prompts": list(C.FAITH_REFLECTION_PROMPTS), "lines_each": 3},
            toc_entry="Monthly Reflection"))

    # Repeating study cycle fills whatever budget remains.
    fixed = len(pages)
    tail = 2 if req.include_notes else 0
    room = max(0, req.pages - fixed - tail)
    cycle_len = 6
    weeks = max(1, room // cycle_len)
    for i in range(weeks):
        row = C.FAITH_READING_PLAN[i % len(C.FAITH_READING_PLAN)]
        pages.extend(_faith_cycle(i + 1, row))

    # Top up any remainder with daily pages rather than shipping a short book.
    while len(pages) < req.pages - tail:
        n = len(pages)
        pages.append(PlannerPage(
            kind="faith_daily", title="Daily Study", subtitle="",
            spec={"prompts": list(C.FAITH_DAILY_PROMPTS), "reference": ""},
            toc_entry="Daily Study" if n == fixed + weeks * cycle_len else ""))

    if req.include_notes:
        pages.extend(_notes_pages(min(tail, 2)))

    if len(pages) != req.pages:
        warnings.append(
            f"Page count adjusted from {req.pages} to {len(pages)} to keep whole "
            "weekly units intact."
        )
    return pages, warnings


# --------------------------------------------------------------------------- #
# Budget Planner
# --------------------------------------------------------------------------- #
def _budget_cycle(month_no: int) -> list[PlannerPage]:
    """One repeating unit: plan, fixed, variable, log, bills, review."""
    tag = f"Month {month_no}"
    return [
        PlannerPage(
            kind="labeled_table", title=f"{tag} - Income",
            subtitle="Plan before the month starts; reconcile after it ends",
            spec={
                "rows": list(C.BUDGET_INCOME_ROWS),
                "value_columns": ["Planned", "Actual", "Difference"],
                "total_label": "Total income",
                "blank_rows": 3,
            },
            toc_entry=f"{tag} - Income",
        ),
        PlannerPage(
            kind="labeled_table", title=f"{tag} - Fixed Costs",
            subtitle="Amounts that do not move much month to month",
            spec={
                "rows": list(C.BUDGET_FIXED_ROWS),
                "value_columns": ["Planned", "Actual", "Difference"],
                "total_label": "Total fixed costs",
                "blank_rows": 3,
            },
            toc_entry=f"{tag} - Fixed Costs",
        ),
        PlannerPage(
            kind="labeled_table", title=f"{tag} - Variable Spending",
            subtitle="The categories that decide whether the month works",
            spec={
                "rows": list(C.BUDGET_VARIABLE_ROWS),
                "value_columns": ["Planned", "Actual", "Difference"],
                "total_label": "Total variable spending",
                "blank_rows": 4,
            },
            toc_entry=f"{tag} - Variable Spending",
        ),
        PlannerPage(
            kind="open_table", title=f"{tag} - Expense Log",
            subtitle="Two honest weeks here is worth a year of estimating",
            spec={
                "columns": [("Date", 0.12), ("Category", 0.22),
                            ("Description", 0.42), ("Amount", 0.24)],
                "rows": 26,
            },
            toc_entry=f"{tag} - Expense Log",
        ),
        PlannerPage(
            kind="open_table", title=f"{tag} - Bill Tracker",
            subtitle="Due date, amount, and the date it actually left the account",
            spec={
                "columns": [("Bill", 0.34), ("Due", 0.14),
                            ("Amount", 0.18), ("Paid on", 0.16), ("Method", 0.18)],
                "rows": 20,
            },
            toc_entry=f"{tag} - Bill Tracker",
        ),
        PlannerPage(
            kind="prompt_page", title=f"{tag} - Monthly Review",
            subtitle="The gap between planned and actual is the lesson",
            spec={"prompts": list(C.BUDGET_REVIEW_PROMPTS), "lines_each": 3},
            toc_entry=f"{tag} - Monthly Review",
        ),
    ]


def build_budget_pages(req: PlannerRequest) -> tuple[list[PlannerPage], list[str]]:
    warnings: list[str] = []
    pages = _front_matter(req, C.BUDGET_HOW_TO_USE, disclaimer=C.BUDGET_DISCLAIMER)

    pages.append(PlannerPage(
        kind="prose", title="Four Budgeting Methods, and When Each One Fails",
        spec={"sections": C.BUDGET_METHODS},
        toc_entry="Four Budgeting Methods"))

    pages.append(PlannerPage(
        kind="snapshot", title="Financial Snapshot",
        subtitle="Do this once, in pencil, before you plan anything",
        spec={
            "assets": list(C.BUDGET_SNAPSHOT_ASSETS),
            "debts": list(C.BUDGET_SNAPSHOT_DEBTS),
        },
        toc_entry="Financial Snapshot"))

    pages.append(PlannerPage(
        kind="prose", title="Building Your First Emergency Fund",
        spec={"sections": C.BUDGET_EMERGENCY_FUND},
        toc_entry="Building Your First Emergency Fund"))

    pages.append(PlannerPage(
        kind="prose", title="How to Cut a Category Without Hating Your Life",
        spec={"sections": C.BUDGET_CUTTING},
        toc_entry="How to Cut a Category Without Hating Your Life"))

    pages.append(PlannerPage(
        kind="prose", title="Choosing a Debt Payoff Method",
        spec={"sections": C.BUDGET_DEBT_METHODS},
        toc_entry="Choosing a Debt Payoff Method"))

    pages.append(PlannerPage(
        kind="open_table", title="Debt Payoff Tracker",
        subtitle="List every balance, then work the order you chose",
        spec={
            "columns": [("Debt", 0.26), ("Balance", 0.15), ("Rate", 0.10),
                        ("Minimum", 0.13), ("Extra", 0.12), ("Cleared on", 0.24)],
            "rows": 18,
        },
        toc_entry="Debt Payoff Tracker"))

    pages.append(PlannerPage(
        kind="labeled_table", title="Sinking Funds",
        subtitle="Annual costs divided by twelve, so they stop being emergencies",
        spec={
            "rows": list(C.BUDGET_SINKING_FUNDS),
            "value_columns": ["Target", "Per month", "Balance"],
            "total_label": "Total per month",
            "blank_rows": 4,
        },
        toc_entry="Sinking Funds"))

    pages.append(PlannerPage(
        kind="open_table", title="Savings Goals",
        subtitle="A goal without a date and an amount is a wish",
        spec={
            "columns": [("Goal", 0.34), ("Target amount", 0.18),
                        ("By when", 0.16), ("Per month", 0.16), ("Reached on", 0.16)],
            "rows": 14,
        },
        toc_entry="Savings Goals"))

    if req.include_calendar:
        pages.append(PlannerPage(
            kind="calendar_month", title="Bill Calendar",
            subtitle="Undated - mark the days money leaves the account",
            spec={}, toc_entry="Bill Calendar"))

    if req.include_habit_tracker:
        pages.append(PlannerPage(
            kind="habit_tracker", title="Money Habit Tracker",
            subtitle="One month, seven habits - shade the square, do not score yourself",
            spec={"habits": list(C.BUDGET_HABITS), "days": 31},
            toc_entry="Money Habit Tracker"))

    fixed = len(pages)
    tail = 2 if req.include_notes else 0
    room = max(0, req.pages - fixed - tail)
    cycle_len = 6
    months = max(1, room // cycle_len)
    for i in range(months):
        pages.extend(_budget_cycle(i + 1))

    while len(pages) < req.pages - tail:
        pages.append(PlannerPage(
            kind="open_table", title="Expense Log",
            subtitle="Extra pages for a heavy month",
            spec={
                "columns": [("Date", 0.12), ("Category", 0.22),
                            ("Description", 0.42), ("Amount", 0.24)],
                "rows": 26,
            }))

    if req.include_notes:
        pages.extend(_notes_pages(min(tail, 2)))

    if len(pages) != req.pages:
        warnings.append(
            f"Page count adjusted from {req.pages} to {len(pages)} to keep whole "
            "monthly units intact."
        )
    return pages, warnings


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_planner_plan(req: PlannerRequest) -> PlannerPlan:
    if req.planner_type not in PLANNER_TYPES:
        raise ValueError(f"Unknown planner type: {req.planner_type!r}")

    title = req.title or default_title(req.planner_type, req.theme)
    subtitle = req.subtitle or default_subtitle(req.planner_type)
    req = PlannerRequest(**{**req.__dict__, "title": title, "subtitle": subtitle})

    if req.planner_type == FAITH:
        pages, warnings = build_faith_pages(req)
    else:
        pages, warnings = build_budget_pages(req)

    # The cover advertises the finished page count, so it is stamped only once
    # the page list is settled — a cover claiming 60 pages on a 58-page book is
    # exactly the kind of small lie the Editor-in-Chief exists to catch.
    if pages and pages[0].kind == "cover":
        size_label = str(req.page_size or "US Letter").strip().upper()
        pages[0].spec["caption"] = (
            f"{len(pages)} PAGES  -  {size_label}  -  PRINT AT HOME OR ON DEMAND"
        )

    return PlannerPlan(
        planner_type=req.planner_type,
        title=title,
        subtitle=subtitle,
        pages=pages,
        warnings=warnings,
    )


def toc_entries(pages: list[PlannerPage]) -> list[tuple[str, int]]:
    """(label, printed page number) for every page that asked to be listed."""
    out: list[tuple[str, int]] = []
    for i, p in enumerate(pages, start=1):
        if p.toc_entry:
            out.append((p.toc_entry, i))
    return out
