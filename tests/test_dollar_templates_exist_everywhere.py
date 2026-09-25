"""v1.9.9 -- the coloring-book "$" remover has patterns on every machine.

Its patterns were drawn only from Windows font files (C:\\Windows\\Fonts\\...).
On Linux -- including the live Render services -- none exist, the pattern list
came back empty, and no "$" was ever removed from a coloring page.
"""
import os

os.environ["FACTORY_TEST_MODE"] = "1"

import numpy as np  # noqa: E402

from services.coloring_book import line_art_cleanup as lac  # noqa: E402


def test_there_are_dollar_patterns_on_this_machine():
    lac._TEMPLATES = None
    templates = lac._get_templates()
    assert len(templates) >= 20
    assert any(40 <= t.shape[0] <= 90 for t in templates)


def test_patterns_exist_even_when_no_windows_font_does(monkeypatch):
    real_isfile = os.path.isfile
    monkeypatch.setattr(lac.os.path, "isfile",
                        lambda p: False if "Windows" in str(p) else real_isfile(p))
    lac._TEMPLATES = None
    try:
        assert len(lac._dollar_templates()) >= 20
    finally:
        lac._TEMPLATES = None


def test_a_dollar_sign_on_open_paper_is_removed():
    lac._TEMPLATES = None
    templ = next(t for t in lac._get_templates() if 40 <= t.shape[0] <= 90)
    arr = np.full((700, 500), 255, dtype=np.uint8)
    th, tw = templ.shape
    roi = arr[300:300 + th, 200:200 + tw]
    roi[templ > 0] = 0
    cleaned, n = lac.remove_dollar_and_text_marks(arr)
    assert n >= 1
    assert float(cleaned[300:300 + th, 200:200 + tw].mean()) > 240.0
