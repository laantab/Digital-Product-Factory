"""Regression coverage for the first Editor-in-Chief 2.0 proofreading patch."""
from services.ebook_copy_editor import edit_text


def test_new_common_typo_corrections_are_reversible_and_free():
    original = "Check the adress and enviroment before contacting the goverment."
    review = edit_text(original)
    assert review["edited"] == "Check the address and environment before contacting the government."
    assert review["original"] == original
    assert review["paid_calls"] == 0
    assert edit_text(review["edited"])["edited"] == review["edited"]


def test_new_words_do_not_modify_protected_content():
    original = '## Adress\n"adress" `enviroment` [goverment](https://example.org)\n'
    assert edit_text(original)["edited"] == original


def test_repeated_word_and_punctuation_are_advisory_only():
    original = "The garden garden grows;water remains essential."
    review = edit_text(original)
    assert review["edited"] == original
    assert {"REPEATED_WORD", "PUNCTUATION_SPACING"} <= {item["code"] for item in review["suggestions"]}
    assert review["paid_calls"] == 0


def test_protected_quotes_do_not_trigger_new_suggestions():
    original = "\"garden garden\" `water;soil`\n"
    review = edit_text(original)
    assert review["edited"] == original
    assert not review["suggestions"]
