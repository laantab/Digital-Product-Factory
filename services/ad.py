"""Product Promotion Package generation for digital product funnels — free + paid.

Generates a complete promotion package across all major platforms driven by
the product/funnel context. Supports Goal A (drive freebie signups) and
Goal B (sell paid product).
"""
from ai_client import chat, chat_json
import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORMS = [
    "pinterest",
    "tiktok",
    "instagram_reels",
    "facebook_groups",
    "youtube_shorts",
    "youtube_thumbnails",
    "blog_post",
    "threads",
    "email",
]

PROMOTION_GOALS = [
    "freebie_signups",
    "sell_paid_product",
]

PLATFORM_LABELS = {
    "pinterest": "Pinterest",
    "tiktok": "TikTok",
    "instagram_reels": "Instagram Reels",
    "facebook_groups": "Facebook Groups",
    "youtube_shorts": "YouTube Shorts",
    "youtube_thumbnails": "YouTube Thumbnails",
    "blog_post": "Blog Post",
    "threads": "Threads / X",
    "email": "Email",
}

PROMOTION_GOAL_LABELS = {
    "freebie_signups": "Drive freebie signups",
    "sell_paid_product": "Sell paid product",
}

# ---------------------------------------------------------------------------
# Legacy 30-second ad script (kept for backward compat)
# ---------------------------------------------------------------------------

def generate_ad(details: str) -> dict:
    """Write a 30-second video ad script (legacy single-format)."""
    details = (details or "").strip()
    if not details:
        raise ValueError("Please describe the finished product.")

    script = chat(
        system=(
            "You are a direct-response video ad copywriter. You write punchy, "
            "high-converting short-form video scripts."
        ),
        user=(
            "Write a 30-second video ad script for the digital product described "
            "below. Format the script as a two-column Markdown table with exactly "
            "two columns: 'Visuals' and 'Audio'. Use 5-7 rows that flow as a "
            "timed storyboard from hook to call-to-action. Keep each cell concise. "
            "Return only the Markdown table, no extra commentary. Do not use "
            "emojis.\n\n"
            f"PRODUCT DETAILS:\n{details}"
        ),
    )
    return {"details": details, "script": script}


# ---------------------------------------------------------------------------
# Product Promotion Package generator
# ---------------------------------------------------------------------------

def _build_goal_context(goal: str, ctx: dict) -> tuple[str, str]:
    """Return (goal_clause, cta_note) based on the promotion goal."""
    freebie = ctx.get("freebie_name", "").strip()
    landing_url = ctx.get("landing_page_url", "").strip()
    paid_url = ctx.get("paid_product_url", "").strip()
    product_title = ctx.get("product_title", "").strip()

    if goal == "freebie_signups":
        goal_clause = (
            "PRIMARY GOAL: Drive signups for the free giveaway / lead magnet. "
            "Every piece should lead with a hook that creates desire for the "
            "free offer, then direct to the free download. Position the paid "
            "product as the natural upgrade path."
        )
        cta_note = f"CTA for freebie: 'Download the free [freebie name]' | Landing page: {landing_url or '[your landing page URL]'}"
    else:
        goal_clause = (
            "PRIMARY GOAL: Drive sales of the paid product. Lead with the "
            "transformation, not the freebie. Use urgency sparingly — only when "
            "authentically true. Mention the free starter pack as a low-commitment "
            "entry point when appropriate."
        )
        cta_note = f"CTA for product: 'Get [product name] now' | Product URL: {paid_url or '[your product URL]'}"

    return goal_clause, cta_note


def _build_context_block(ctx: dict) -> str:
    """Build the product context block for the AI prompt."""
    lines = [
        f"PRODUCT TITLE: {ctx.get('product_title', '[product title]').strip()}",
        f"PRODUCT TYPE: {ctx.get('product_type', 'digital product').strip()}",
        f"TARGET AUDIENCE: {ctx.get('target_audience', '[your target audience]').strip()}",
        f"CUSTOMER PROBLEM: {ctx.get('customer_problem', '[the specific problem this solves]').strip()}",
        f"PRODUCT PROMISE / DESIRED OUTCOME: {ctx.get('product_promise', '[the transformation or outcome]').strip()}",
        f"TONE: {ctx.get('tone', 'helpful and relatable').strip()}",
    ]
    if ctx.get("freebie_name", "").strip():
        lines.append(f'FREE GIVEAWAY / LEAD MAGNET: "{ctx.get("freebie_name", "").strip()}"')
    if ctx.get("landing_page_url", "").strip():
        lines.append(f"LANDING PAGE URL: {ctx.get('landing_page_url', '').strip()}")
    if ctx.get("paid_product_url", "").strip():
        lines.append(f"PAID PRODUCT URL: {ctx.get('paid_product_url', '').strip()}")
    if ctx.get("product_description", "").strip():
        lines.append(f"PRODUCT DESCRIPTION: {ctx.get('product_description', '').strip()}")
    if ctx.get("price", "").strip():
        lines.append(f"PRICE: {ctx.get('price', '').strip()}")
    return "\n".join(lines)


def _build_prompt(ctx: dict, goal: str, include_paid: bool) -> str:
    """Build the comprehensive AI prompt for the full promotion package."""
    goal_clause, cta_note = _build_goal_context(goal, ctx)
    context_block = _build_context_block(ctx)

    return (
        "Generate a complete Product Promotion Package for the digital product below. "
        "Every piece must be SPECIFIC to the product, audience, problem, and promise. "
        "No generic lines like 'change your life today', 'unlock your potential', "
        "'get results fast', 'don't miss out', or 'this is for everyone'. "
        "No emojis in any output.\n\n"
        f"{context_block}\n\n"
        f"{goal_clause}\n"
        f"CTA NOTE: {cta_note}\n\n"
        "Return a single JSON object with ALL of the following keys. "
        "Return only the JSON object — no markdown, no commentary.\n\n"
        "# 1. SHORT VIDEO SCRIPTS (TikTok / Instagram Reels / YouTube Shorts)\n"
        '"short_video_scripts": [\n'
        "  {\n"
        "    \"platform\": \"tiktok\" | \"instagram\" | \"youtube_shorts\",\n"
        "    \"hook\": \"first 3-second hook — grab attention immediately\",\n"
        "    \"problem_statement\": \"1-2 sentences stating the specific problem\",\n"
        "    \"quick_value\": \"the core insight or tip delivered in the video\",\n"
        "    \"spoken_script\": \"full spoken script, 15-30 seconds\",\n"
        "    \"on_screen_text\": \"suggested text overlays in brackets\",\n"
        "    \"visual_direction\": \"what to show on camera / B-roll\",\n"
        "    \"cta\": \"clear call-to-action at the end\",\n"
        "    \"length\": \"15s | 30s | 60s\"\n"
        "  }\n"
        "] — generate exactly 10 scripts, mix of TikTok / Instagram / YouTube Shorts\n\n"
        "# 2. YOUTUBE THUMBNAIL IDEAS\n"
        '"youtube_thumbnails": [\n'
        "  {\n"
        "    \"title_text\": \"text for the thumbnail (5-7 words max)\",\n"
        "    \"visual_concept\": \"what the thumbnail shows\",\n"
        "    \"emotional_angle\": \"the emotion it triggers (curiosity, relief, etc.)\",\n"
        "    \"color_direction\": \"suggested color palette / style\",\n"
        "    \"design_notes\": \"layout notes (face + text, text only, etc.)\"\n"
        "  }\n"
        "] — generate exactly 5 thumbnail ideas\n\n"
        "# 3. YOUTUBE VIDEO TITLES\n"
        '"youtube_titles": {\n'
        "  \"searchable\": [\"10 searchable title ideas, keyword-rich\"],\n"
        "  \"curiosity\": [\"5 curiosity-gap titles\"],\n"
        "  \"howto\": [\"5 how-to title ideas\"]\n"
        "}\n\n"
        "# 4. PINTEREST PACKAGE\n"
        '"pinterest_pins": {\n'
        "  \"titles\": [\"10 pin titles, max 100 chars, benefit-led and keyword-rich\"],\n"
        "  \"descriptions\": [\"10 pin descriptions, max 500 chars\"],\n"
        "  \"design_ideas\": [\"10 pin design concepts, 1-2 sentences each\"],\n"
        "  \"keywords\": [\"15 relevant keywords / hashtags for search\"]\n"
        "}\n\n"
        "# 5. FACEBOOK / GROUP POSTS\n"
        '"facebook_posts\": [\n'
        "  {\n"
        "    \"post_text\": \"value-first post, 150-300 words, no spam language\",\n"
        "    \"cta\": \"soft call-to-action at the end\",\n"
        "    \"angle\": \"the specific angle of this post\"\n"
        "  }\n"
        "] — generate exactly 5 posts\n\n"
        "# 6. INSTAGRAM CAPTIONS\n"
        '"instagram_captions\": [\n'
        "  {\n"
        "    \"caption_text\": \"full caption with hook + value copy\",\n"
        "    \"hook\": \"first line / hook (should stop the scroll)\",\n"
        "    \"cta\": \"call-to-action\",\n"
        "    \"hashtags\": \"15 relevant hashtags\"\n"
        "  }\n"
        "] — generate exactly 10 captions\n\n"
        "# 7. THREADS / X POSTS\n"
        '"threads_posts\": [\n'
        "  {\n"
        "    \"post_text\": \"short post, 100-280 characters\",\n"
        "    \"type\": \"tip | curiosity | question | story | stat\",\n"
        "    \"cta_variation\": \"optional CTA\"\n"
        "  }\n"
        "] — generate exactly 15 posts, mix of types\n\n"
        "# 8. EMAIL PROMOTION PACKAGE\n"
        '"email_package\": {\n'
        "  \"subject_lines\": [\"10 subject lines, max 50 chars, curiosity or benefit-driven\"],\n"
        "  \"short_promos\": [\n"
        "    {\n"
        "      \"email_type\": \"nurture | awareness | urgency\",\n"
        "      \"subject\": \"subject line\",\n"
        "      \"body\": \"short promo email body, 80-120 words\"\n"
        "    }\n"
        "  ],\n"
        "  \"launch_email\": {\n"
        "    \"subject\": \"launch email subject line\",\n"
        "    \"body\": \"full launch email, 150-200 words\"\n"
        "  },\n"
        "  \"final_reminder\": {\n"
        "    \"subject\": \"final reminder subject line\",\n"
        "    \"body\": \"last-chance reminder email, 100-150 words\"\n"
        "  }\n"
        "}\n\n"
        "# 9. LANDING PAGE CTA VARIATIONS\n"
        '"landing_page_ctas\": {\n'
        "  \"button_texts\": [\"10 CTA button texts, action-oriented, 3-6 words\"],\n"
        "  \"headlines\": [\"5 headline options for the landing page hero\"],\n"
        "  \"subheadlines\": [\"5 subheadline options\"]\n"
        "}\n\n"
        "# 10. 7-DAY FREE TRAFFIC POSTING PLAN\n"
        '"seven_day_plan\": {\n'
        "  \"days\": [\n"
        "    {\n"
        "      \"day\": 1-7,\n"
        "      \"platform\": \"platform name\",\n"
        "      \"content_type\": \"e.g. value post, short video, email, story, pin\",\n"
        "      \"post_angle\": \"what angle or hook to use that day\",\n"
        "      \"cta\": \"what CTA to include\",\n"
        "      \"posting_note\": \"1-2 sentence execution tip\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "# 11. PAID AD COPY (optional — include only if paid advertising is relevant)\n"
        '"paid_ads\": {\n'
        "  \"facebook_ads\": [\n"
        "    {\n"
        "      \"headline\": \"ad headline (under 40 chars)\",\n"
        "      \"primary_text\": \"primary ad copy, 100-150 words\",\n"
        "      \"description\": \"ad description (under 30 chars)\",\n"
        "      \"cta\": \"button text\"\n"
        "    }\n"
        "  ],\n"
        "  \"short_video_ads\": [\n"
        "    {\n"
        "      \"hook\": \"first 3 seconds\",\n"
        "      \"body\": \"spoken ad script, 15-30 seconds\",\n"
        "      \"cta\": \"end card CTA\"\n"
        "    }\n"
        "  ],\n"
        "  \"google_yt_ads\": [\n"
        "    {\n"
        "      \"headline1\": \"headline 1 (max 30 chars)\",\n"
        "      \"headline2\": \"headline 2 (max 30 chars)\",\n"
        "      \"headline3\": \"headline 3 (max 30 chars)\",\n"
        "      \"description1\": \"description line 1 (max 90 chars)\",\n"
        "      \"description2\": \"description line 2 (max 90 chars)\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )


def generate_promotion_package(
    funnel_context: dict,
    promotion_goal: str,
    include_paid_ads: bool = False,
) -> dict:
    """Generate a complete Product Promotion Package.

    Args:
        funnel_context: Dict with keys:
            - product_title       (str, required)
            - product_type        (str)
            - target_audience    (str)
            - customer_problem   (str)
            - product_promise    (str)
            - product_description (str)
            - freebie_name      (str, optional)
            - landing_page_url    (str, optional)
            - paid_product_url   (str, optional)
            - tone               (str)
            - price              (str, optional)
        promotion_goal: "freebie_signups" or "sell_paid_product"
        include_paid_ads: Whether to include paid ad copy

    Returns:
        Dict with all package sections.
    """
    ctx = funnel_context or {}
    product_title = (ctx.get("product_title") or "").strip()
    if not product_title:
        raise ValueError("Product title is required.")

    if promotion_goal not in PROMOTION_GOALS:
        raise ValueError("Select a valid promotion goal: freebie_signups or sell_paid_product.")

    prompt = _build_prompt(ctx, promotion_goal, include_paid_ads)

    result = chat_json(
        system=(
            "You are a direct-response copywriter and content strategist. "
            "You write platform-specific promotional content that is concrete, "
            "specific, and conversion-focused. You NEVER use generic marketing "
            "lines. You write for real people with real problems. "
            "No emojis."
        ),
        user=prompt,
        max_completion_tokens=12000,
    )

    return {
        "product_title": product_title,
        "promotion_goal": promotion_goal,
        "goal_label": PROMOTION_GOAL_LABELS.get(promotion_goal, promotion_goal),
        "include_paid_ads": include_paid_ads,
        "funnel_context": ctx,
        "package": result,
    }


# ---------------------------------------------------------------------------
# Legacy traffic content generator (kept for backward compat with prior version)
# ---------------------------------------------------------------------------

PLATFORMS_LEGACY = [
    "pinterest",
    "tiktok",
    "instagram_reels",
    "facebook_groups",
    "youtube_shorts",
    "blog_post",
    "email",
]

TRAFFIC_GOALS_LEGACY = [
    "get_freebie_signups",
    "sell_paid_product",
    "promote_landing_page",
    "grow_email_list",
    "launch_announcement",
    "retarget_interested",
    "social_media_batch",
]


def generate_traffic_content(
    funnel_context: dict,
    platforms: list[str],
    traffic_goal: str,
    num_pieces: int = 5,
) -> dict:
    """Generate platform-specific free traffic content from a product/funnel (legacy v1)."""
    platforms = [p for p in (platforms or []) if p in PLATFORMS_LEGACY]
    if not platforms:
        raise ValueError("Select at least one platform.")
    if traffic_goal not in TRAFFIC_GOALS_LEGACY:
        raise ValueError("Select a valid traffic goal.")

    ctx = funnel_context or {}
    product_title = (ctx.get("product_title") or "").strip()
    if not product_title:
        raise ValueError("Product title is required.")

    audience = ctx.get("target_audience", "").strip()
    problem = ctx.get("customer_problem", "").strip()
    promise = ctx.get("product_promise", "").strip()
    freebie = ctx.get("freebie_name", "").strip()
    landing_url = ctx.get("landing_page_url", "").strip()
    paid_url = ctx.get("paid_product_url", "").strip()
    tone = ctx.get("tone", "helpful and relatable").strip()
    product_type = ctx.get("product_type", "digital product").strip()

    freebie_clause = f'\n- Free giveaway / lead magnet: "{freebie}"' if freebie else ""
    landing_clause = f'\n- Landing page URL (link to use in CTAs): {landing_url}' if landing_url else ""
    paid_clause = f'\n- Paid product URL: {paid_url}' if paid_url else ""

    goal_clause = {
        "get_freebie_signups": "Primary goal: drive clicks to the free giveaway / lead magnet.",
        "sell_paid_product": "Primary goal: drive sales of the paid product.",
        "promote_landing_page": "Primary goal: drive traffic to the landing page.",
        "grow_email_list": "Primary goal: grow the email list via the free giveaway.",
        "launch_announcement": "Primary goal: announce the product launch.",
        "retarget_interested": "Primary goal: re-engage people who showed interest but did not convert.",
        "social_media_batch": "Primary goal: produce a variety of platform-native posts that build authority.",
    }.get(traffic_goal, "")

    platform_summaries = {
        "pinterest": "Pinterest: pin titles (max 100 chars) and pin descriptions (max 500 chars). Titles must be keyword-rich.",
        "tiktok": "TikTok: short-form video scripts (60-90 seconds). Hook in first 3 seconds, core value, then CTA.",
        "instagram_reels": "Instagram Reels: short-form video scripts (30-60 seconds). Hook in first 2 seconds, value delivery, then CTA.",
        "facebook_groups": "Facebook Group: value-post format. Long-form post (150-300 words) that delivers genuine insight, ends with soft CTA.",
        "youtube_shorts": "YouTube Shorts: video script (30-60 seconds). Hook-first, one concrete tip, then CTA.",
        "blog_post": "Blog post: headline (max 70 chars, SEO-friendly) plus a one-paragraph outline (3-4 bullet points).",
        "email": "Email: subject line (max 50 chars) plus a short email body (80-120 words).",
    }

    platform_outputs = {
        "pinterest": f'"pin_titles": [array of {num_pieces} strings, max 100 chars], "pin_descriptions": [array of {num_pieces} strings, max 500 chars]',
        "tiktok": f'"video_scripts": [array of {num_pieces} objects each with "hook", "body", "cta"]',
        "instagram_reels": f'"video_scripts": [array of {num_pieces} objects each with "hook", "body", "cta"]',
        "facebook_groups": f'"posts": [array of {num_pieces} strings, 150-300 words each]',
        "youtube_shorts": f'"video_scripts": [array of {num_pieces} objects each with "hook", "body", "cta"]',
        "blog_post": f'"headlines": [array of {num_pieces} strings, max 70 chars], "outlines": [array of {num_pieces} strings, 3-4 bullets]',
        "email": f'"subject_lines": [array of {num_pieces} strings, max 50 chars], "bodies": [array of {num_pieces} strings, 80-120 words]',
    }

    platform_specs = "\n".join(f"- {p}: {platform_summaries[p]}" for p in platforms)
    output_specs = "\n".join(f"- {p}: {platform_outputs[p]}" for p in platforms)

    user_prompt = (
        f"Generate free traffic content for a digital product funnel.\n\n"
        f"PRODUCT: {product_title}\n"
        f"TYPE: {product_type}\n"
        f"AUDIENCE: {audience or '[your target audience]'}\n"
        f"CUSTOMER PROBLEM: {problem or '[the specific problem]'}\n"
        f"PRODUCT PROMISE: {promise or '[the transformation]'}\n"
        f"TONE: {tone}\n"
        f"{freebie_clause}\n"
        f"{landing_clause}\n"
        f"{paid_clause}\n\n"
        f"TRAFFIC GOAL: {goal_clause}\n\n"
        f"PLATFORMS TO GENERATE FOR:\n{platform_specs}\n\n"
        f"Return a JSON object with one key per platform:\n{output_specs}\n\n"
        "- No emojis. No generic lines. Return only the JSON object."
    )

    result = chat_json(
        system=(
            "You are a direct-response copywriter and traffic content strategist. "
            "You write platform-specific content that is concrete, specific, "
            "and conversion-focused. You NEVER use generic marketing lines."
        ),
        user=user_prompt,
        max_completion_tokens=6000,
    )

    return {
        "product_title": product_title,
        "platforms": platforms,
        "traffic_goal": traffic_goal,
        "goal_label": goal_clause.split(":")[0].strip(),
        "num_pieces": num_pieces,
        "platform_results": result,
    }


def generate_seven_day_plan(
    funnel_context: dict,
    platforms: list[str],
    traffic_goal: str,
) -> dict:
    """Generate a 7-day posting plan (legacy v1)."""
    ctx = funnel_context or {}
    product_title = (ctx.get("product_title") or "").strip()
    freebie = ctx.get("freebie_name", "").strip()
    landing_url = ctx.get("landing_page_url", "").strip()
    audience = ctx.get("target_audience", "").strip()
    problem = ctx.get("customer_problem", "").strip()
    promise = ctx.get("product_promise", "").strip()
    tone = ctx.get("tone", "helpful and relatable").strip()

    platform_list = ", ".join(PLATFORM_LABELS.get(p, p) for p in (platforms or [])) or "Social media"

    prompt = (
        f"Create a 7-day free traffic posting plan.\n\n"
        f"Product: {product_title}\n"
        f"Target audience: {audience or '[your target audience]'}\n"
        f"Problem: {problem or '[specific problem]'}\n"
        f"Promise: {promise or '[transformation]'}\n"
        f"Tone: {tone}\n"
        f"Free giveaway: {freebie or '[freebie name]'}\n"
        f"Landing page: {landing_url or '[landing page URL]'}\n"
        f"Platforms: {platform_list}\n\n"
        'Return JSON: {"days": [{"day":1,"platform":"","content_type":"","post_angle":"","cta":"","posting_note":""}]}'
    )

    result = chat_json(
        system="You are a content calendar strategist.",
        user=prompt,
        max_completion_tokens=3000,
    )
    return {"product_title": product_title, "platforms": platforms, "traffic_goal": traffic_goal, "plan": result}


def _build_promotion_text(pkg: dict, ctx: dict) -> str:
    """Convert an ad package dict into a readable text document."""
    title = ctx.get("product_title", "")
    lines = [f"AD PROMOTION PACKAGE — {title}", "=" * 50, ""]

    def section(heading: str, items: list) -> None:
        if not items:
            return
        lines.append(heading)
        lines.append("-" * 40)
        for item in items:
            lines.append(f"  {item}")
        lines.append("")

    # Short video scripts (TikTok / Reels / YouTube Shorts)
    for s in pkg.get("short_video_scripts") or []:
        lines.append(f"--- {s.get('platform', 'short video').upper()} SCRIPT ---")
        lines.append(f"Hook: {s.get('hook', '')}")
        lines.append(f"Problem: {s.get('problem_statement', '')}")
        lines.append(f"Quick Value: {s.get('quick_value', '')}")
        lines.append(f"Script:\n{s.get('spoken_script', '')}")
        lines.append(f"On-Screen Text: {s.get('on_screen_text', '')}")
        lines.append(f"Visual Direction: {s.get('visual_direction', '')}")
        lines.append(f"CTA: {s.get('cta', '')}")
        lines.append("")

    # YouTube thumbnails
    for t in pkg.get("youtube_thumbnails") or []:
        lines.append("--- YOUTUBE THUMBNAIL ---")
        lines.append(f"Title Text: {t.get('title_text', '')}")
        lines.append(f"Visual: {t.get('visual_concept', '')}")
        lines.append(f"Emotion: {t.get('emotional_angle', '')}")
        lines.append(f"Color/Style: {t.get('color_direction', '')}")
        lines.append(f"Design Notes: {t.get('design_notes', '')}")
        lines.append("")

    # YouTube titles
    yt = pkg.get("youtube_titles") or {}
    if yt:
        lines.append("YOUTUBE VIDEO TITLES")
        lines.append("-" * 40)
        for cat in ["searchable", "curiosity", "howto"]:
            items = yt.get(cat) or []
            if items:
                lines.append(f"\n{cat.title()}:")
                for t in items:
                    lines.append(f"  - {t}")
        lines.append("")

    # Pinterest pins
    pins = pkg.get("pinterest_pins") or []
    if pins:
        lines.append("PINTEREST PINS")
        lines.append("-" * 40)
        if isinstance(pins, list):
            for i, p in enumerate(pins):
                lines.append(f"\nPin {i+1}:")
                lines.append(f"  Title: {p.get('title', p.get('pin_title', ''))}")
                lines.append(f"  Description: {p.get('description', p.get('pin_description', ''))}")
                lines.append(f"  Design Idea: {p.get('design_idea', '')}")
        else:
            titles = pins.get("titles") or []
            for i, t in enumerate(titles):
                lines.append(f"\nPin {i+1}: {t}")
                lines.append(f"  Description: {(pins.get('descriptions') or [''])[i] if i < len(pins.get('descriptions') or []) else ''}")
        lines.append("")

    # Facebook posts
    fb_posts = pkg.get("facebook_posts") or []
    for i, p in enumerate(fb_posts):
        lines.append(f"--- FACEBOOK POST {i+1} ---")
        for key in ["post_angle", "hook", "body", "cta"]:
            val = p.get(key, "")
            if val:
                lines.append(f"{key.replace('_', ' ').title()}: {val}")
        lines.append("")

    # Email promo
    for e in pkg.get("email_promo") or []:
        lines.append(f"--- EMAIL PROMO: {e.get('subject', 'Untitled')} ---")
        lines.append(f"Subject: {e.get('subject', '')}")
        lines.append(f"Preview Text: {e.get('preview_text', '')}")
        lines.append(f"Body:\n{e.get('body', '')}")
        lines.append(f"CTA: {e.get('cta', '')}")
        lines.append("")

    # Blog post
    blog = pkg.get("blog_post") or {}
    if blog:
        lines.append("--- BLOG POST ---")
        lines.append(f"Title: {blog.get('title', '')}")
        lines.append(f"SEO Headline: {blog.get('seo_headline', '')}")
        lines.append(f"Intro: {blog.get('intro', '')}")
        for s in blog.get("sections") or []:
            lines.append(f"\n  ## {s.get('heading', '')}")
            lines.append(f"  {s.get('content', '')}")
        lines.append(f"\nCTA: {blog.get('cta', '')}")
        lines.append("")

    # 7-day plan
    plan = pkg.get("seven_day_plan") or {}
    days = plan.get("days") or []
    if days:
        lines.append("7-DAY SOCIAL MEDIA PLAN")
        lines.append("-" * 40)
        for d in days:
            lines.append(f"\nDay {d.get('day', '?')}: {d.get('platform', '')}")
            lines.append(f"  Content Type: {d.get('content_type', '')}")
            lines.append(f"  Angle: {d.get('post_angle', '')}")
            lines.append(f"  CTA: {d.get('cta', '')}")
            lines.append(f"  Note: {d.get('posting_note', '')}")

    return "\n".join(lines)





# ---------------------------------------------------------------------------
# Launch Package Generator
# ---------------------------------------------------------------------------

def generate_launch_package(funnel_context: dict, promotion_goal: str = "sell_paid_product") -> dict:
    """Generate a complete MiloTree-style launch package for a saved product.

    Produces 8 sections:
      1. Freebie Builder — the lead magnet
      2. Opt-in Page Copy — squeeze / lead capture page
      3. Sales Page Copy — paid product sales page
      4. Thank-You / Tripwire Page — post-signup with upsell
      5. Ad Package — TikTok, Reels, Shorts, thumbnails, Pinterest, FB, email
      6. Email Sequence — delivery, value, pitch, reminder, final offer
      7. Delivery Checklist — fulfillment instructions
      8. Launch Checklist — pre-launch, launch day, post-launch

    Args:
        funnel_context: dict with keys like product_title, audience, problem,
            promise, product_description, price, freebie_name, landing_page_url,
            paid_product_url.
        promotion_goal: "freebie_signups" (drive list) or "sell_paid_product".
    """
    title = funnel_context.get("product_title") or funnel_context.get("title") or "[Product Title]"
    audience = funnel_context.get("audience") or "[Your Target Audience]"
    problem = funnel_context.get("problem") or "[The Problem They Face]"
    promise = funnel_context.get("product_promise") or funnel_context.get("promise") or "[The Transformation]"
    description = funnel_context.get("product_description") or funnel_context.get("description") or ""
    price = funnel_context.get("price") or "[Price]"
    freebie = funnel_context.get("freebie_name") or funnel_context.get("freebie") or "[Freebie / Lead Magnet]"
    landing_url = funnel_context.get("landing_page_url") or funnel_context.get("landing_url") or "[Opt-in Page URL]"
    paid_url = funnel_context.get("paid_product_url") or funnel_context.get("product_url") or "[Sales Page URL]"
    tone = funnel_context.get("tone") or "empathetic and understanding"

    # ── Section 1: Freebie Builder ──────────────────────────────────────────
    freebie_prompt = (
        f"Product: {title}\n"
        f"Audience: {audience}\n"
        f"Problem: {problem}\n"
        f"Promise: {promise}\n"
        f"Paid product: {description}\n\n"
        f"Create a compelling free lead magnet (freebie) that complements this paid product. "
        f"Choose the BEST format for this audience and product. Options: 5-page starter pack, "
        f"checklist, sample worksheet pack, sample coloring page pack, prompt cheat sheet, "
        f"mini guide, printable sample, or another format you think would work better.\n\n"
        f"Return JSON with this exact structure:\n"
        f'{{"freebie_name": "...", "freebie_format": "...", "freebie_description": "...", '
        f'"freebie_pages": "...", "why_this_freebie": "...", '
        f'"freebie_optin_headline": "...", "freebie_optin_subheadline": "..."}}'
    )
    freebie_data = chat_json(
        system="You are a lead magnet strategist who creates irresistible freebies.",
        user=freebie_prompt,
        max_completion_tokens=1500,
    )

    # ── Section 2: Opt-in Page Copy ─────────────────────────────────────────
    optin_prompt = (
        f"Product: {title}\n"
        f"Audience: {audience}\n"
        f"Problem: {problem}\n"
        f"Promise: {promise}\n"
        f"Freebie: {freebie}\n"
        f"Freebie details: {json.dumps(freebie_data)}\n"
        f"Tone: {tone}\n\n"
        f"Write a compelling opt-in (lead capture) page. Return JSON:\n"
        f'{{"headline": "...", "subheadline": "...", '
        f'"what_you_get": ["...", "..."], '
        f'"signup_cta": "...", '
        f'"trust_section": "...", '
        f'"faq": [{{"q": "...", "a": "..."}}]}}'
    )
    optin_data = chat_json(
        system="You write high-converting opt-in pages for digital product funnels.",
        user=optin_prompt,
        max_completion_tokens=2000,
    )

    # ── Section 3: Sales Page Copy ─────────────────────────────────────────
    sales_prompt = (
        f"Product: {title}\n"
        f"Audience: {audience}\n"
        f"Problem: {problem}\n"
        f"Promise: {promise}\n"
        f"Description: {description}\n"
        f"Price placeholder: {price}\n"
        f"Tone: {tone}\n\n"
        f"Write a complete sales page for this digital product. Return JSON:\n"
        f'{{"headline": "...", "problem_section": "...", '
        f'"promise_section": "...", '
        f'"whats_included": ["...", "..."], '
        f'"who_is_this_for": "...", '
        f'"price_display": "Price: {price} — [your price here]", '
        f'"cta_button": "...", '
        f'"guarantee": "...", '
        f'"faq": [{{"q": "...", "a": "..."}}]}}'
    )
    sales_data = chat_json(
        system="You write persuasive sales copy for digital products and online courses.",
        user=sales_prompt,
        max_completion_tokens=2500,
    )

    # ── Section 4: Thank-You / Tripwire Page ────────────────────────────────
    tripwire_prompt = (
        f"Product: {title}\n"
        f"Audience: {audience}\n"
        f"Problem: {problem}\n"
        f"Promise: {promise}\n"
        f"Paid product URL: {paid_url}\n"
        f"Price: {price}\n"
        f"Description: {description}\n"
        f"Tone: {tone}\n\n"
        f"Write a thank-you page for people who just downloaded the freebie. "
        f"Include a tripwire offer (the paid product at a special price). "
        f"Return JSON:\n"
        f'{{"thank_you_message": "...", '
        f'"tripwire_headline": "...", '
        f'"tripwire_description": "...", '
        f'"tripwire_price": "SPECIAL PRICE: [your special price here]", '
        f'"tripwire_cta": "...", '
        f'"no_thanks_link": "No thanks, just send me my freebie."}}'
    )
    tripwire_data = chat_json(
        system="You write high-converting thank-you pages with tripwire upsells for digital product launches.",
        user=tripwire_prompt,
        max_completion_tokens=2000,
    )

    # ── Section 5: Ad Package (reuse promotion package logic) ───────────────
    ad_data = generate_promotion_package(
        funnel_context=funnel_context,
        promotion_goal=promotion_goal,
        include_paid_ads=False,
    )

    # ── Section 6: Email Sequence ────────────────────────────────────────────
    email_prompt = (
        f"Product: {title}\n"
        f"Audience: {audience}\n"
        f"Problem: {problem}\n"
        f"Promise: {promise}\n"
        f"Freebie: {freebie}\n"
        f"Paid product: {description}\n"
        f"Price: {price}\n"
        f"Sales page URL: {paid_url}\n"
        f"Tone: {tone}\n\n"
        f"Write a 5-email follow-up sequence for people who got the freebie. "
        f"Return JSON:\n"
        f'{{"emails": ['
        f'{{"subject": "Email 1: Delivery", "body": "..."}},'
        f'{{"subject": "Email 2: Value Teaser", "body": "..."}},'
        f'{{"subject": "Email 3: Product Pitch", "body": "..."}},'
        f'{{"subject": "Email 4: Reminder / Urgency", "body": "..."}},'
        f'{{"subject": "Email 5: Final Offer", "body": "..."}}'
        f']}}'
    )
    email_data = chat_json(
        system="You write email sequences for digital product launches.",
        user=email_prompt,
        max_completion_tokens=4000,
    )

    # ── Section 7: Delivery Checklist ────────────────────────────────────────
    delivery_checklist = (
        f"## Delivery Checklist for: {title}\n\n"
        f"### Where Your Files Are\n"
        f"- PDF / ZIP download: [paste the file URL or path here]\n"
        f"- Recommended hosting: Gumroad, Lemon Squeezy, Payhip, or your own site\n\n"
        f"### Setting Up Auto-Delivery\n"
        f"1. Upload your PDF/ZIP to your delivery platform\n"
        f"2. Set the file as the 'deliverable' for your {title}\n"
        f"3. For Gumroad: paste the product URL as your 'purchase URL'\n"
        f"4. For Lemon Squeezy: use the 'attached files' feature\n"
        f"5. Test the purchase flow yourself before going live\n\n"
        f"### Freebie Delivery (if separate from paid product)\n"
        f"- Upload the freebie file to your email platform (ConvertKit, Mailchimp, etc.)\n"
        f"- Create an automation: 'New subscriber' → 'Send freebie email'\n"
        f"- Or use a platform like Strip pdffile as a lead magnet deliverable\n\n"
        f"### Post-Purchase Follow-up\n"
        f"- Confirm your email sequence is active (5 emails minimum)\n"
        f"- Check that the email sequence delay is set appropriately:\n"
        f"  Day 0: Delivery email (immediate)\n"
        f"  Day 1: Value email\n"
        f"  Day 3: Product pitch\n"
        f"  Day 5: Reminder\n"
        f"  Day 7: Final offer\n"
    )

    # ── Section 8: Launch Checklist ─────────────────────────────────────────
    launch_checklist = (
        f"## Launch Checklist for: {title}\n\n"
        f"### 1 Week Before Launch\n"
        f"[ ] Upload PDF/ZIP and test the delivery flow\n"
        f"[ ] Set up your email sequence and test it\n"
        f"[ ] Create your opt-in page ({landing_url})\n"
        f"[ ] Set up your sales page ({paid_url})\n"
        f"[ ] Write and schedule your social media posts\n"
        f"[ ] Prepare your ad creatives (see ad_package.txt)\n"
        f"[ ] Notify your email list: 'Something's coming...' email\n\n"
        f"### Launch Day\n"
        f"[ ] Confirm all links are live and correct\n"
        f"[ ] Post on social media (see 7-day plan in ad_package.txt)\n"
        f"[ ] Run ads (start with lowest budget, monitor)\n"
        f"[ ] Engage in any Facebook groups or communities you belong to\n"
        f"[ ] Respond to any comments or DMs quickly\n\n"
        f"### Post-Launch\n"
        f"[ ] Day 3: Check open rates on your email sequence\n"
        f"[ ] Day 5: Send a reminder to non-openers\n"
        f"[ ] Day 7: Send final offer email\n"
        f"[ ] Collect testimonials from buyers\n"
        f"[ ] Plan your next launch or evergreen funnel"
    )

    return {
        "product_title": title,
        "promotion_goal": promotion_goal,
        "freebie": freebie_data,
        "optin_page": optin_data,
        "sales_page": sales_data,
        "thank_you_tripwire": tripwire_data,
        "ad_package": ad_data,
        "email_sequence": email_data,
        "delivery_checklist": delivery_checklist,
        "launch_checklist": launch_checklist,
    }
