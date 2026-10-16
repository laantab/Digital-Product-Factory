"""Shared editorial mode policy: one quality standard, two user experiences.

Mode choice alone does not perform writes or authorize paid services.
"""
MODES = ("automatic", "manual")
DEFAULT_MODE = "automatic"


def choose_mode(value=None):
    if value is None or value == "":
        return DEFAULT_MODE
    if value not in MODES:
        raise ValueError("Choose automatic or manual editing.")
    return value


def editing_policy(mode=None):
    mode = choose_mode(mode)
    return {
        "mode": mode,
        "automatic_proofreading": mode == "automatic",
        "manual_acceptance_required": mode == "manual",
        "publishing_quality_gate_required": True,
        "paid_ai_authorized": False,
        "preserve_previous_exports": True,
    }
