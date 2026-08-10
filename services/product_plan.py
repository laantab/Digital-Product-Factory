"""Product Planning module.

Turns a product idea (often coming from a saved Market Research result) into a
complete product blueprint, returned as structured JSON so the frontend can lay
it out cleanly and the Product Builder module can consume it later.
"""
from ai_client import chat_json

_PLAN_KEYS = [
    "product_title",
    "subtitle",
    "product_type",
    "target_audience",
    "customer_problem",
    "product_promise",
    "main_transformation",
    "price_range",
    "product_description",
    "outline",
    "bonus_ideas",
    "cover_concept",
    "sales_angle",
    "marketing_hook",
    "next_step",
]


def _f(data: dict, key: str, default: str = "") -> str:
    return str(data.get(key, default) or default).strip()


def _coerce_plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    plan = {}
    for key in _PLAN_KEYS:
        plan[key] = raw.get(key, "")
    for key in ("outline", "bonus_ideas"):
        val = plan.get(key)
        if isinstance(val, str):
            plan[key] = [val] if val.strip() else []
        elif not isinstance(val, list):
            plan[key] = []
        else:
            plan[key] = [str(v).strip() for v in val if str(v).strip()]
    return plan


def generate_product_plan(form: dict) -> dict:
    if not isinstance(form, dict):
        raise ValueError("Product planning details are required.")

    idea = _f(form, "idea")
    if not idea:
        raise ValueError("Please enter a product idea.")

    product_type = _f(form, "product_type") or "Not Sure Yet"
    format_clause = (
        "The product type is not decided yet, so choose the most suitable format "
        "and state it clearly."
        if product_type == "Not Sure Yet"
        else f"The intended product type is: {product_type}."
    )

    raw = chat_json(
        system=(
            "You are a digital-product strategist who turns rough ideas into "
            "clear, sellable product blueprints for beginners. You are concrete, "
            "practical, and encouraging."
        ),
        user=(
            "Create a complete product blueprint from the planning brief below. "
            f"{format_clause}\n\n"
            "PLANNING BRIEF:\n"
            f"- Product idea: {idea}\n"
            f"- Product type: {product_type}\n"
            f"- Target audience: {_f(form, 'audience')}\n"
            f"- Main problem it solves: {_f(form, 'problem')}\n"
            f"- Desired customer outcome: {_f(form, 'outcome')}\n"
            f"- Tone / style: {_f(form, 'tone')}\n"
            f"- Suggested length or size: {_f(form, 'length')}\n"
            f"- Difficulty level: {_f(form, 'difficulty')}\n"
            f"- Notes / special instructions: {_f(form, 'notes')}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "product_title": string.\n'
            '- "subtitle": string.\n'
            '- "product_type": string (the final chosen format).\n'
            '- "target_audience": string.\n'
            '- "customer_problem": string.\n'
            '- "product_promise": string, the core promise to the buyer.\n'
            '- "main_transformation": string, the before-to-after change.\n'
            '- "price_range": string, e.g. "$12 - $29".\n'
            '- "product_description": string, 2-4 sentences.\n'
            '- "outline": array of chapter/section strings in order.\n'
            '- "bonus_ideas": array of 2-5 bonus/add-on strings.\n'
            '- "cover_concept": string describing the cover idea.\n'
            '- "sales_angle": string, the positioning angle.\n'
            '- "marketing_hook": string, a short attention-grabbing hook.\n'
            '- "next_step": string, one clear recommended next action.\n'
            "Do not use emojis. Return only the JSON object."
        ),
        max_completion_tokens=3500,
    )

    plan = _coerce_plan(raw)
    # When research/planning already selected an explicit product type, keep it.
    # The model must not silently rewrite Coloring Book / Word Search / etc. to
    # Ebook — sendToBuilder routes from plan.product_type.
    if product_type and product_type != "Not Sure Yet":
        plan["product_type"] = product_type
    resolved_type = plan.get("product_type") or product_type
    return {
        "form": form,
        "product_type": resolved_type,
        "plan": plan,
    }
