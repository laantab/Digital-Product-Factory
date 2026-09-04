"""Fixture mode must require BOTH safety switches.

Fixture content is deterministic test data, not a product. A paying customer
must never receive it. Before this, EBOOK_CUSTOMER_PATH_FIXTURE alone unlocked
it, so one stray environment variable could have served test content as a real
ebook.

Both must be strictly true:
    FACTORY_TEST_MODE=1
    EBOOK_CUSTOMER_PATH_FIXTURE=1

Anything else -- absent, blank, "0", "false", malformed -- uses the normal
production path. There is no silent fallback.
"""
from __future__ import annotations

import pytest

from services.external_calls import ebook_fixture_mode

BOTH = ("FACTORY_TEST_MODE", "EBOOK_CUSTOMER_PATH_FIXTURE")


def _set(monkeypatch, test_mode, fixture):
    for name, value in (("FACTORY_TEST_MODE", test_mode),
                        ("EBOOK_CUSTOMER_PATH_FIXTURE", fixture)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


# ------------------------------------------------------ must NOT activate ---


def test_neither_variable_present(monkeypatch):
    _set(monkeypatch, None, None)
    assert ebook_fixture_mode() is False


def test_only_factory_test_mode(monkeypatch):
    """Safe Mode alone must not serve fixture content."""
    _set(monkeypatch, "1", None)
    assert ebook_fixture_mode() is False


def test_only_fixture_variable(monkeypatch):
    """The dangerous case: a stray fixture flag in a production process."""
    _set(monkeypatch, None, "1")
    assert ebook_fixture_mode() is False


@pytest.mark.parametrize("bad", ["0", "false", "False", "no", "", "   ", "maybe",
                                 "2", "on", "TRUE-ish", "null", "None"])
def test_malformed_or_false_values_never_activate(monkeypatch, bad):
    _set(monkeypatch, "1", bad)
    assert ebook_fixture_mode() is False, f"fixture must not activate for {bad!r}"
    _set(monkeypatch, bad, "1")
    assert ebook_fixture_mode() is False, f"fixture must not activate for {bad!r}"


def test_production_mode_cannot_reach_fixture_content(monkeypatch):
    """Normal production: no test mode, even with the fixture flag set."""
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv("EBOOK_CUSTOMER_PATH_FIXTURE", "1")

    from services.ebook_customer_path import fixture_mode

    assert fixture_mode() is False
    assert ebook_fixture_mode() is False


# ---------------------------------------------------------- must activate ---


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "Yes", " 1 "])
def test_activates_only_when_both_are_true(monkeypatch, truthy):
    _set(monkeypatch, truthy, truthy)
    assert ebook_fixture_mode() is True


def test_public_fixture_mode_delegates_to_the_dual_gate(monkeypatch):
    from services.ebook_customer_path import fixture_mode

    _set(monkeypatch, "1", "1")
    assert fixture_mode() is True
    _set(monkeypatch, "1", "0")
    assert fixture_mode() is False


# ------------------------------------------- every consumer uses the gate ---


def test_visual_plan_fixture_requires_both(monkeypatch):
    """services/ebook_package.generate_visual_plan"""
    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv("EBOOK_CUSTOMER_PATH_FIXTURE", "1")
    assert ebook_fixture_mode() is False


def test_no_consumer_reads_the_fixture_variable_directly_for_content():
    """Content gates must go through the dual gate, not a bare env read."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for rel in (
        "services/ebook_package.py",
        "services/ebook_factory_pipeline.py",
        "services/quality/download_pipeline_agent.py",
        "services/ebook_customer_path.py",
    ):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r'os\.environ\.get\(\s*["\']EBOOK_CUSTOMER_PATH_FIXTURE', text):
            line = text[: match.start()].count("\n") + 1
            # An OR-style "skip paid work" guard is allowed; a content gate is not.
            window = text[max(0, match.start() - 400): match.start()]
            if "FACTORY_TEST_MODE" not in window:
                offenders.append(f"{rel}:{line}")
    assert not offenders, f"content gates must use ebook_fixture_mode(): {offenders}"
