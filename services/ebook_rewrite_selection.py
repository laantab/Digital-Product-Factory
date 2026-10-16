"""Passage selection utilities for optional manuscript rewrites."""


def selected_text(manuscript: str, start: int, end: int) -> str:
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(manuscript):
        raise ValueError('Select a valid passage within the manuscript.')
    return manuscript[start:end]


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
