"""Passage selection utilities for optional manuscript rewrites."""


def selected_text(manuscript: str, start: int, end: int) -> str:
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(manuscript):
        raise ValueError('Select a valid passage within the manuscript.')
    # Selection cannot include structural Markdown lines or break across them.
    import re
    piece = manuscript[start:end]
    if re.search(r'(?m)^(?:#{1,6}\s|>|[|]|```|~~~)', piece):
        raise ValueError('Select prose only, not Markdown structure.')
    return piece


def replace_selection(manuscript: str, start: int, end: int, replacement: str) -> str:
    """Build a review-only draft; preserve all text outside selected range."""
    original = selected_text(manuscript, start, end)
    if not isinstance(replacement, str) or not replacement.strip():
        raise ValueError('The replacement must contain text.')
    if start and manuscript[start - 1].isalnum() and original[0].isalnum():
        raise ValueError('Selection begins inside a word.')
    if end < len(manuscript) and original[-1].isalnum() and manuscript[end].isalnum():
        raise ValueError('Selection ends inside a word.')
    return manuscript[:start] + replacement + manuscript[end:]
