"""Source links must fit the page and must not print as boxes.

THE HISTORY THIS GUARDS
-----------------------
A URL is one unbreakable token to the PDF renderer, which honours no CSS rule
that would split it. A 110-character Amazon link ran past the page edge and
failed print preflight with "text extends outside the page box".

The first fix inserted zero-width spaces at each separator to create break
points. Invisible in a browser — but the PDF font has no glyph for them, so
every link on the finished book's Sources page printed as a row of black
boxes. That is worse than the fault it replaced.

Nothing invisible is added now. The label is shortened and the anchor keeps
the real address.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_book_layout import (  # noqa: E402
    _URL_TEXT_BUDGET,
    printable_source_url,
)

#: Anything a font might not have a glyph for.
INVISIBLES = "​‌‍⁠﻿­"

LONG = (
    "https://www.amazon.com/HEALTHY-MEAL-PREP-COOKBOOK-Nutritious-Packed-Lunches"
    "/dp/B0CVXS9J8N?pd_rd_w=abcde&pf_rd_p=12345678-90ab-cdef&pd_rd_r=deadbeef"
)


def test_no_invisible_character_ever_reaches_the_page():
    for url in (LONG, "https://a.test/" + "x-" * 90, "https://short.test/a"):
        printed = printable_source_url(url)
        assert not (set(printed) & set(INVISIBLES)), f"invisible char in {printed!r}"


def test_a_long_address_is_shortened_to_something_that_fits():
    printed = printable_source_url(LONG)
    assert len(printed) <= _URL_TEXT_BUDGET + 1  # the ellipsis
    assert printed.endswith("…")


def test_the_site_is_always_readable():
    assert printable_source_url(LONG).startswith("https://www.amazon.com/")


def test_tracking_parameters_are_dropped():
    printed = printable_source_url(LONG)
    for noise in ("pd_rd_w", "pf_rd_p", "deadbeef", "?"):
        assert noise not in printed


def test_a_short_address_is_left_exactly_as_it_is():
    url = "https://www.verywellfit.com/easy-weight-loss-meal-plans-3495471"
    assert printable_source_url(url) == url


def test_a_bare_domain_survives_with_no_trailing_slash():
    assert printable_source_url("https://example.test/") == "https://example.test/"
    assert printable_source_url("https://example.test") == "https://example.test"


def test_a_domain_longer_than_the_budget_still_returns_something_sane():
    url = "https://" + "d" * 120 + "/some/path"
    printed = printable_source_url(url)
    assert printed.startswith("https://")
    assert not (set(printed) & set(INVISIBLES))


def test_empty_input_is_empty_output():
    assert printable_source_url("") == ""
    assert printable_source_url(None) == ""


def test_the_anchor_keeps_a_working_address_while_the_label_is_short():
    """Shortening the label must not shorten the link the reader clicks."""
    from services.ebook_book_layout import _linkify_sources

    html = _linkify_sources(f"<ul><li>{LONG}</li></ul>")
    assert LONG.split("?")[0] in html, "the href must still reach the source"
    assert "pd_rd_w" not in html
    assert not (set(html) & set(INVISIBLES))
