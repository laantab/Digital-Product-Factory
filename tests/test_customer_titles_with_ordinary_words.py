"""v1.9.7 -- a customer's own title never hides their book.

"SAT Test Prep", "QA Engineer Career Guide", "Workflow Automation for Small
Business", "Seed Starting for Beginners" and "Internal Family Systems
Journal" all vanished from Saved Projects and from Continue, because the
clutter filter still matched bare words in the TITLE. Only an unmistakable
label ("[TEST]") in the title, or the words in the record's own metadata,
may hide a record.
"""
import os

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

import database  # noqa: E402

REAL_TITLES = [
    "SAT Test Prep for Busy Students",
    "QA Engineer Career Guide",
    "Workflow Automation for Small Business",
    "Seed Starting for Beginners",
    "Internal Family Systems Journal",
    "Pipeline Welding Basics",
    "Validation: A Parent's Guide to Listening",
    "The Placeholder Kitchen Cookbook",
]


def _p(title, **data):
    return {"id": 424242, "name": title, "type": "ebook",
            "data": {"title": title, "status": "completed", **data}}


@pytest.mark.parametrize("title", REAL_TITLES)
def test_a_real_title_is_not_clutter(title):
    assert database.is_customer_clutter_record(_p(title)) is False


@pytest.mark.parametrize("title", ["[TEST] Garden", "(QA) Garden", "Garden [debug]"])
def test_an_explicit_label_still_hides(title):
    assert database.is_customer_clutter_record(_p(title)) is True


def test_internal_metadata_still_hides():
    assert database.is_customer_clutter_record(
        _p("Gardening", status="validation")) is True
    assert database.is_customer_clutter_record(
        _p("Gardening", _test_reason="smoke test")) is True


def test_strong_internal_phrases_still_hide():
    assert database.is_customer_clutter_record(_p("Workflow Test Ebook")) is True
    assert database.is_customer_clutter_record(_p("Final Download Proof")) is True
