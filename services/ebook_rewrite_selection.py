"""Passage selection utilities for optional manuscript rewrites."""


def selected_text(manuscript: str, start: int, end: int) -> str:
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(manuscript):
        raise ValueError('Select a valid passage within the manuscript.')
    return manuscript[start:end]
