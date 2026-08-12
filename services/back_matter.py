"""
Deterministic back-matter modules for ebook previews (no AI calls).
Provides Quick Reference, FAQ, and Action Worksheet sections.
"""

from .ebook_package import _e

# ---------------------------------------------------------------------------
# Topic detection
# ---------------------------------------------------------------------------

def _detect_topic(title: str, topic: str = "") -> str:
    combined = (title + " " + topic).lower()
    if any(k in combined for k in ["dog", "pup", "pet", "canine", "training", "behavior"]):
        return "dog"
    if any(k in combined for k in ["ai model", "llm", "gpt", "claude", "gemini", "artificial intelligence"]):
        return "ai"
    if any(k in combined for k in ["marketing funnel", "funnel", "conversion", "sales funnel", "email funnel"]):
        return "marketing"
    if any(k in combined for k in ["fitness", "exercise", "workout", "training", "muscle", "strength", "cardio", "aging well", "over 50", "after 50", "senior fitness", "active aging"]):
        return "fitness"
    if any(k in combined for k in ["health", "wellness", "nutrition", "diet", "weight loss", "sleep", "stress", "energy", "immune"]):
        return "health"
    if any(k in combined for k in ["budget", "finance", "financial", "money management", "invest", "stock", "retirement", "debt", "credit", "savings", "passive income"]):
        return "finance"
    if any(k in combined for k in ["legal", "law", "rights", "contract", "liability", "estate planning", "will", "trademark"]):
        return "legal"
    return "general"


# ---------------------------------------------------------------------------
# Quick Reference
# ---------------------------------------------------------------------------

def build_quick_reference_html(title: str, topic: str = "") -> str:
    """One-page cheat sheet with the book's core takeaways."""
    t = _detect_topic(title, topic)
    tpl = _QUICK_REF_TEMPLATES.get(t, _QUICK_REF_TEMPLATES["general"])
    return (
        '<div class="bm-section quick-reference-page">'
        f'<div class="bm-label">Quick Reference</div>'
        f'<div class="bm-title">{_e(title)}</div>'
        f'<div class="bm-intro">{tpl["intro"]}</div>'
        f'<div class="bm-grid">{tpl["grid"]}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------

def build_faq_html(topic: str = "") -> str:
    """Topic-aware FAQ with 5-8 questions and answers."""
    t = _detect_topic("", topic)
    faqs = _FAQ_POOLS.get(t, _FAQ_POOLS["general"])
    items = "".join(
        f'<div class="faq-item">'
        f'<div class="faq-q">{_e(q)}</div>'
        f'<div class="faq-a">{_e(a)}</div>'
        f'</div>'
        for q, a in faqs
    )
    return (
        '<div class="bm-section faq-page">'
        '<div class="bm-label">FAQ</div>'
        f'<div class="faq-list">{items}</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Action Worksheet
# ---------------------------------------------------------------------------

def build_action_worksheet_html(topic: str = "") -> str:
    """One-page fillable action-plan table."""
    t = _detect_topic("", topic)
    tpl = _WORKSHEET_TEMPLATES.get(t, _WORKSHEET_TEMPLATES["general"])
    rows = "".join(
        f'<tr>'
        f'<td class="ws-row-num">{i + 1}</td>'
        f'<td class="ws-action">{_e(row["action"])}</td>'
        f'<td class="ws-when"></td>'
        f'<td class="ws-done"><span class="ws-check"></span></td>'
        f'</tr>'
        for i, row in enumerate(tpl["rows"])
    )
    return (
        '<div class="bm-section worksheet-page">'
        '<div class="bm-label">Action Plan</div>'
        f'<div class="bm-title">{tpl["title"]}</div>'
        f'<div class="ws-table-wrap">'
        # table-layout:fixed + explicit col widths prevent xhtml2pdf text concat
        f'<table class="ws-table ws-table-fixed">'
        f'<colgroup>'
        f'<col style="width:36px;">'   # #
        f'<col style="width:auto;">'    # Action (flexible)
        f'<col style="width:140px;">'   # When
        f'<col style="width:48px;">'    # Done (checkbox column)
        f'</colgroup>'
        f'<thead><tr><th>#</th><th>Action</th><th>When</th><th>Done</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'</div>'
        f'<div class="ws-note">{tpl["note"]}</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Combined back matter
# ---------------------------------------------------------------------------

def build_back_matter_html(
    title: str,
    topic: str = "",
    package_id: str = "",
    *,
    include: bool = False,
    sections: list[str] | None = None,
) -> str:
    """Build optional back-matter sections.

    Default is omit. Generic FAQ / Quick Reference / Action Worksheet are never
    injected merely to pad length. Callers must pass include=True and an explicit
    section list (outline-backed) to opt in.
    """
    if not include:
        return ""
    wanted = {str(s).strip().lower() for s in (sections or []) if str(s).strip()}
    if not wanted:
        return ""
    parts: list[str] = []
    if "quick reference" in wanted or "qr" in wanted:
        parts.append(build_quick_reference_html(title, topic))
    if "faq" in wanted or "frequently asked questions" in wanted:
        parts.append(build_faq_html(topic))
    if "action" in wanted or "action plan" in wanted or "worksheet" in wanted:
        parts.append(build_action_worksheet_html(topic))
    return "".join(parts)


# ---------------------------------------------------------------------------
# CSS (appended to main ebook CSS via render_preview_html)
# ---------------------------------------------------------------------------

_BACK_MATTER_CSS = """
.bm-section { border-top: 3px solid #ede9fe; margin-top: 32px; padding-top: 24px; }
.bm-label { display: inline-block; background: #f5f3ff; color: #6d28d9; font-weight: 700;
  font-size: 11px; text-transform: uppercase;
  padding: 5px 12px; border-radius: 999px; margin-bottom: 14px; }
.bm-title { font-size: 20px; font-weight: 800; color: #1e1b4b; margin-bottom: 12px; }
.bm-intro { font-size: 14px; color: #475569; margin-bottom: 18px; }
.bm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.bm-point { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }
.bm-point-title { font-size: 13px; font-weight: 700; color: #312e81; margin-bottom: 6px; }
.bm-point-body { font-size: 13px; color: #475569; }
.bm-section.worksheet-page .bm-title { font-size: 18px; margin-bottom: 14px; }
.faq-list { display: flex; flex-direction: column; gap: 14px; }
.faq-item { border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 18px; background: #fff; }
.faq-q { font-size: 14px; font-weight: 700; color: #1e1b4b; margin-bottom: 6px; }
.faq-a { font-size: 14px; color: #475569; line-height: 1.65; }
.ws-table-wrap { overflow-x: auto; margin-bottom: 12px; }
.ws-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.ws-table-fixed { table-layout: fixed; }
.ws-table th { background: #f5f3ff; color: #4c1d95; font-weight: 700; padding: 10px 12px; text-align: left; border-bottom: 2px solid #c4b5fd; }
.ws-table td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
.ws-row-num { color: #7c3aed; font-weight: 700; width: 36px; }
.ws-action { color: #1e1b4b; }
.ws-when { background: #fef9c3; min-width: 140px; width: 140px; }
.ws-done { width: 48px; }
.ws-check { display: inline-block; width: 18px; height: 18px; border: 2px solid #7c3aed; border-radius: 4px; }
.ws-note { font-size: 12px; color: #6b7280; font-style: italic; margin-top: 8px; }
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qr_point(title: str, body: str) -> str:
    return (
        f'<div class="bm-point">'
        f'<div class="bm-point-title">{_e(title)}</div>'
        f'<div class="bm-point-body">{_e(body)}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_QUICK_REF_TEMPLATES = {
    "fitness": {
        "intro": "Core principles for building strength, mobility, and energy at any age.",
        "grid": ""
            + _qr_point("Start slow and build gradually", "Consistency matters more than intensity. A 15-minute daily walk beats a 2-hour weekend workout you skip.")
            + _qr_point("Prioritize joint-friendly movement", "Low-impact exercises (walking, swimming, cycling, resistance bands) protect joints while building strength.")
            + _qr_point("Protein supports muscle maintenance", "After age 40, the body needs more protein to maintain and build muscle. Spread intake across meals.")
            + _qr_point("Recovery is part of the program", "Sleep, hydration, and rest days are when your body actually gets stronger.")
            + _qr_point("Track what matters", "Keep a simple log of workouts, energy levels, and progress — not just weight.")
            + _qr_point("Make it sustainable", "The best fitness routine is the one you actually enjoy and will keep doing."),
    },
    "health": {
        "intro": "Key habits that support long-term health, energy, and wellbeing.",
        "grid": ""
            + _qr_point("Eat whole foods most of the time", "Prioritize vegetables, lean proteins, whole grains, and healthy fats over processed options.")
            + _qr_point("Stay hydrated", "Water supports digestion, energy, concentration, and joint health. Aim for clear-to-light-yellow urine as a guide.")
            + _qr_point("Move every day", "Any movement counts — walking, stretching, gardening. Aim for at least 30 minutes of light activity daily.")
            + _qr_point("Prioritize sleep quality", "7-9 hours of consistent sleep supports immune function, mood, and weight management.")
            + _qr_point("Manage stress actively", "Chronic stress undermines everything else. Build in daily breaks, breathwork, or time outdoors.")
            + _qr_point("Get regular checkups", "Prevention is easier than treatment. Stay current on screenings appropriate for your age and risk factors."),
    },
    "finance": {
        "intro": "Core principles for managing money, reducing debt, and building financial security.",
        "grid": ""
            + _qr_point("Know your numbers", "Track income and expenses for at least one month before making any budget changes.")
            + _qr_point("Pay yourself first", "Save a set amount before any other expenses. Even small amounts compound over time.")
            + _qr_point("Tackle high-interest debt first", "Credit card debt grows fastest. Focus extra payments there while maintaining minimums on other debt.")
            + _qr_point("Build an emergency fund", "Aim for 3-6 months of essential expenses in a separate, accessible account.")
            + _qr_point("Automate what you can", "Automating savings and bill payments removes friction and reduces the chance of missed payments.")
            + _qr_point("Keep it simple", "A basic budget with a few categories is more sustainable than an elaborate system you abandon."),
    },
    "legal": {
        "intro": "Foundational legal awareness points when starting a business or project.",
        "grid": ""
            + _qr_point("Separate personal and business finances", "An LLC or business structure protects personal assets from business liabilities.")
            + _qr_point("Get it in writing", "Verbal agreements are hard to enforce. Use written contracts for every significant arrangement.")
            + _qr_point("Understand your liability", "Know which activities in your business carry risk and how to mitigate them.")
            + _qr_point("Protect your intellectual property", "Trademarks, copyrights, and NDAs each serve different purposes — use them appropriately.")
            + _qr_point("Budget for legal help", "An ounce of prevention with an attorney is worth pounds of cure. Consult early, not just when things go wrong.")
            + _qr_point("Know when to escalate", "Some situations require a licensed attorney. Know your limits and seek professional help when needed."),
    },
    "dog": {
        "intro": "Core principles for understanding and shaping your dog's behavior.",
        "grid": ""
            + _qr_point("Be consistent", "Dogs learn through repetition and predictable routines.")
            + _qr_point("Read body language", "Tail position, ear set, and eye contact reveal emotional state.")
            + _qr_point("Reward wanted behavior", "Positive reinforcement is faster and more reliable than punishment.")
            + _qr_point("Manage the environment", "Set up situations for success before asking for new behaviors.")
            + _qr_point("Exercise and mental stimulation", "A tired dog is a calm, trainable dog.")
            + _qr_point("Patience is essential", "Behavior change takes weeks, not days. Stay the course."),
    },
    "ai": {
        "intro": "Key factors when evaluating and choosing an AI model for your work.",
        "grid": ""
            + _qr_point("Understand your use case", "Different models excel at different tasks — match the tool to the job.")
            + _qr_point("Check context window size", "Larger context windows handle longer documents and conversations.")
            + _qr_point("Evaluate output quality", "Run test prompts before committing. Quality varies widely.")
            + _qr_point("Consider cost at scale", "Per-token pricing adds up. Estimate your expected volume first.")
            + _qr_point("Review data policies", "Understand how your data is stored, used, or shared.")
            + _qr_point("Test edge cases", "Models behave very differently on unusual or adversarial inputs."),
    },
    "marketing": {
        "intro": "The five stages of a marketing funnel and how to move prospects through each one.",
        "grid": ""
            + _qr_point("Awareness", "Attract strangers with content, ads, and social media reach.")
            + _qr_point("Discovery", "Offer a lead magnet to capture contact information.")
            + _qr_point("Consideration", "Nurture with email sequences, case studies, and webinars.")
            + _qr_point("Conversion", "Present an offer with a clear incentive to act now.")
            + _qr_point("Retention", "Delight customers and turn them into repeat buyers and referral sources.")
            + _qr_point("Measure everything", "Use UTM parameters and analytics to track performance at each stage."),
    },
    "general": {
        "intro": "The most important ideas from this guide, distilled for quick reference.",
        "grid": ""
            + _qr_point("Start with the core idea", "Identify the single most important concept before taking action.")
            + _qr_point("Break it into steps", "Large goals become manageable when split into small, daily actions.")
            + _qr_point("Track your progress", "Measurement drives improvement. Set up a simple tracking system.")
            + _qr_point("Adjust based on feedback", "Revise your approach after reviewing results, not before.")
            + _qr_point("Stay consistent", "Small, repeated effort outperforms sporadic bursts of intensity.")
            + _qr_point("Celebrate milestones", "Acknowledging progress builds momentum and reinforces the habit."),
    },
}

_FAQ_POOLS = {
    "fitness": [
        ("Is it too late to start exercising after 50?", "Not at all. Studies consistently show that adults who begin regular exercise after 50 see significant improvements in strength, mobility, and energy. The key is starting at a level that matches your current fitness and progressing gradually."),
        ("What type of exercise is safest for beginners?", "Low-impact activities are generally safest to start with: brisk walking, swimming, cycling, and bodyweight strength exercises with light resistance. Always warm up before and stretch after. Consult your doctor if you have any pre-existing conditions."),
        ("How often should I exercise?", "Most guidelines suggest at least 150 minutes of moderate aerobic activity per week (e.g., 30 minutes, 5 days a week) plus 2 strength training sessions. Even 10-minute sessions throughout the day add up."),
        ("I feel sore after exercising. Is that normal?", "Mild muscle soreness 24-48 hours after a workout is normal, especially when starting or trying something new. Rest, gentle movement, and hydration help recovery. Severe pain, swelling, or pain that doesn't fade is not normal — see a professional."),
        ("Do I need a gym membership?", "No. Many effective exercises require no equipment: bodyweight squats, push-ups against a wall, walking, and stretching. A few resistance bands or dumbbells add variety. The best gym is the one you'll actually use."),
        ("How do I stay motivated to keep exercising?", "Start with activities you genuinely enjoy. Set small, realistic goals. Track your progress in a simple log. Find an accountability partner or community. Remember that the goal is a lifelong habit, not a short-term sprint."),
        ("Can I still build muscle as I get older?", "Yes. While muscle-building capacity decreases slightly with age (a process called sarcopenia), regular resistance training at any age stimulates muscle growth and strength gains. Adequate protein intake supports this process."),
    ],
    "health": [
        ("How much water should I drink each day?", "A common guideline is 8 glasses (64 oz) per day, but individual needs vary based on activity level, climate, and body size. A practical guide: drink enough that your urine is clear to light yellow most of the time."),
        ("What foods should I prioritize?", "Fill half your plate with vegetables and fruits. Add lean protein sources (fish, chicken, beans, eggs). Include whole grains and healthy fats (nuts, olive oil, avocado). Minimize processed foods, added sugars, and excessive sodium."),
        ("How can I improve my sleep quality?", "Keep a consistent sleep schedule, even on weekends. Limit screens 1 hour before bed. Keep the bedroom cool, dark, and quiet. Avoid caffeine after noon and large meals close to bedtime."),
        ("Is stress actually harmful to my health?", "Chronic stress elevates cortisol levels, which over time can contribute to weight gain, poor sleep, weakened immunity, and digestive issues. Short-term stress is normal and manageable. Building daily stress-management habits (exercise, breathwork, time outdoors) is worth the effort."),
        ("Do I need supplements?", "Most people with a balanced diet don't need supplements, but certain groups may benefit: vitamin D in winter climates, B12 for vegans, iron if deficient. Get blood work done to identify specific needs rather than guessing. Talk to your doctor before starting any supplement."),
        ("How often should I see my doctor?", "Annual physical exams are generally recommended for adults. Frequency increases with age and health conditions. Stay current on recommended screenings (colonoscopy, mammogram, cholesterol, blood pressure, diabetes) as advised by your healthcare provider."),
        ("Can I reverse health problems with diet and exercise?", "Some conditions (pre-diabetes, high blood pressure, high cholesterol) can be significantly improved or even reversed with lifestyle changes. Others (Type 2 diabetes, heart disease) can be managed and their progression slowed. Lifestyle change is powerful, but results vary and should complement — not replace — medical care."),
    ],
    "finance": [
        ("How do I start a budget if I've never done one?", "Start by tracking every dollar you spend for one month without changing anything. Then categorize the spending (housing, food, transportation, entertainment, etc.). Compare that to your monthly income. Set realistic spending limits for each category based on what's left after essentials."),
        ("Should I pay off debt or save first?", "A common approach: maintain a small emergency fund ($1,000) first, then attack high-interest debt aggressively. Simultaneously build your full emergency fund as debt goes down. The psychological win of reducing debt is real, so balance financial logic with what keeps you motivated."),
        ("How much should I have in an emergency fund?", "Aim for 3-6 months of essential expenses (housing, food, utilities, insurance, minimum debt payments). Keep it in a separate savings account that's accessible but not too easy to tap impulsively."),
        ("Is it worth paying off a mortgage early?", "It depends on the interest rate, your other financial goals, and your peace of mind. If your mortgage rate is low, investing extra money may yield better returns. If the psychological freedom of owning your home outright matters to you, extra payments toward the mortgage are a valid choice."),
        ("How much should I be saving for retirement?", "A general guideline is 15-20% of your gross income, but the right number depends on your age, goals, and current savings. The most important thing is to start — even small amounts grow significantly over time with compound interest."),
        ("Should I invest in the stock market?", "For goals more than 5 years away, stocks have historically outperformed most other asset classes. For short-term goals, lower-risk options (bonds, high-yield savings) are more appropriate. Diversification across asset classes reduces risk. If you're unsure, a fee-only financial advisor can help."),
        ("What's the difference between a Roth IRA and a traditional IRA?", "A traditional IRA gives you a tax deduction now but you pay taxes on withdrawals in retirement. A Roth IRA doesn't give an upfront deduction but withdrawals in retirement are tax-free. Your current tax bracket, expected future tax bracket, and income limits determine which is better for you."),
    ],
    "legal": [
        ("Do I need a lawyer to start my business?", "Not necessarily for simple businesses. Sole proprietorships and some LLCs can be set up without a lawyer using online services. You should consult a lawyer when the business involves significant liability risk, multiple partners, complex contracts, or regulated industries."),
        ("What's the difference between a trademark, copyright, and patent?", "A trademark protects brand names, logos, and slogans. A copyright protects original creative works (writing, art, music, software). A patent protects inventions and processes. Each has different registration requirements, costs, and durations."),
        ("What should be in a contract?", "At minimum: the parties involved, the scope of work or agreement, payment terms, timeline, and what happens if either party breaches the agreement. Vague contracts cause disputes. Specific, clear language protects both parties."),
        ("Do I need an NDA (Non-Disclosure Agreement)?", "NDAs are useful when sharing confidential business information with potential partners, investors, or contractors. They establish legal expectations around confidentiality. They don't guarantee protection — they provide a basis for legal action if confidentiality is breached."),
        ("What is an LLC and do I need one?", "An LLC (Limited Liability Company) separates your personal assets from business liabilities. If someone sues your business, your personal savings, home, or car are generally protected. If your business carries risk (consulting, product sales, client work), an LLC is usually worth the small annual cost."),
        ("What happens if I don't have a written contract?", "Without a written contract, you rely on verbal agreements and applicable state laws — both of which are harder to prove and enforce. Courts may imply default terms that don't reflect what either party intended. A handshake deal is risky; always document material agreements in writing."),
        ("How do I protect my online content and intellectual property?", "Use copyright notices on your work (© Your Name). Register copyrights for your most valuable creative works. Use trademarks for brand identifiers. For software or processes, consult a patent attorney if the invention is novel and commercially valuable."),
    ],
    "dog": [
        ("How long does it take to train a dog?", "It depends on the dog and the behavior. Basic commands can show results within 1-2 weeks of consistent practice. Complex behaviors or behavior modification may take several months. Patience and consistency are the key factors."),
        ("Should I use treats or praise for training?", "Both work, but treats are more reliable for teaching new behaviors, especially early on. Once a behavior is learned, you can fade treats and rely more on verbal praise and play."),
        ("My dog barks at everything. What should I do?", "First, identify the trigger. Then teach an incompatible behavior (like 'go to your bed') and reward calm responses. Avoid yelling — it can increase excitement and reinforce the barking."),
        ("Is it too late to train an older dog?", "Not at all. While puppies learn quickly, adult dogs can absolutely learn new behaviors. It may take slightly longer, but positive reinforcement works at any age."),
        ("What does 'positive reinforcement' mean?", "It means adding something desirable (a treat, praise, or play) immediately after a behavior you want to repeat. This makes the dog more likely to repeat that behavior in the future."),
        ("Should I hire a professional trainer?", "If you're dealing with aggression, severe anxiety, or fear-based behaviors, a certified behavior consultant (not just a trainer) is strongly recommended. For basic obedience, quality books and videos can work well."),
        ("How do I stop my dog from jumping on people?", "Teach an alternative behavior like 'sit' before guests arrive. Reward the sit consistently. Ask visitors to ignore jumping and only greet the dog when all four paws are on the ground."),
    ],
    "ai": [
        ("What's the difference between an AI model and an AI tool?", "An AI model is the underlying engine (like GPT-4 or Claude). An AI tool or product wraps that model with a user interface, memory, and additional features. The model determines capability; the tool determines usability."),
        ("Which AI model should I use for writing?", "For creative writing, models with strong reasoning and style are best. For structured output or formatting, look for models with strong instruction-following. Try a few and compare outputs on your actual tasks."),
        ("How does 'context window' affect what I can do?", "The context window is how much text the model can 'see' at once. Larger windows let you feed in long documents, conversation history, or large datasets. If your content exceeds the limit, you need to chunk it."),
        ("Are AI outputs original?", "AI generates new text statistically, not by copying. However, it can produce outputs similar to training data. For sensitive or proprietary content, treat AI output as a first draft and verify facts independently."),
        ("Can I use AI-generated content commercially?", "In most cases, yes. Most providers grant you rights to outputs. However, check each provider's terms of service, especially for outputs used in regulated industries or public-facing commercial materials."),
        ("How do I get better outputs from AI?", "Be specific and clear in your instructions. Provide context, examples, and format guidelines. For complex tasks, break them into steps and iterate. Prompt engineering significantly affects output quality."),
        ("What about AI privacy and data security?", "Different providers have different policies. For sensitive data, use providers with explicit data-retention policies, opt-out of training, and enterprise agreements. Never input private personal data without verifying the provider's policies."),
    ],
    "marketing": [
        ("What is a marketing funnel?", "A marketing funnel is the journey a prospect takes from first learning about you to becoming a customer. It has stages — awareness, discovery, consideration, conversion, and retention — each requiring different content and tactics."),
        ("Do I need all five funnel stages?", "Most profitable businesses use all five. Skipping stages leads to dropping prospects. A full funnel builds trust over time so that when prospects are ready to buy, they choose you."),
        ("What's a lead magnet?", "A lead magnet is a free, valuable resource (like a checklist, template, or mini-course) offered in exchange for an email address. It moves strangers from awareness into your funnel."),
        ("How do I write a high-converting sales page?", "Focus on the prospect's problem, agitate it, then present your solution as the clear answer. Use social proof, address objections, and end with a specific, time-bound call to action."),
        ("What are UTM parameters?", "UTM parameters are short text tags you add to URLs (e.g., utm_source=email). They tell analytics tools where traffic came from, enabling you to measure which channels and campaigns actually drive sales."),
        ("How often should I email my list?", "A consistent schedule beats a sporadic one. Most businesses email 1-2 times per week. The right frequency depends on your audience and content value — watch unsubscribe rates as your guide."),
        ("How do I measure funnel performance?", "Track conversion rates between each stage: visitor-to-lead, lead-to-opportunity, opportunity-to-customer. Use a CRM or spreadsheet to calculate where prospects drop off and focus improvement efforts there."),
    ],
    "general": [
        ("Is this approach right for me?", "The strategies in this guide work best when you apply them consistently. They require some upfront setup but become automatic over time. Start with one change and build from there."),
        ("How long before I see results?", "Most people notice initial improvements within 1-2 weeks. Meaningful, measurable results typically appear after 4-6 weeks of consistent effort. Track your baseline so you can see the progress."),
        ("Do I need special tools or software?", "Most of the principles here require only pen and paper or a basic digital tool. Advanced tools can help at scale, but don't let the absence of tools stop you from starting."),
        ("What if I slip up or fall off track?", "Slips are normal and expected. The key is to resume your practice as quickly as possible without self-judgment. One off day doesn't erase weeks of progress."),
        ("Can I adapt these methods to my situation?", "These principles are frameworks, not rigid scripts. Use the ones that fit your circumstances and adapt the specifics to match your goals, pace, and available resources."),
        ("How do I stay motivated over time?", "Connect your practice to a meaningful outcome. Track and celebrate small wins. Build accountability through a journal, a friend, or a community. Motivation follows momentum — start and it will follow."),
        ("What if my situation is unique?", "Every situation has unique elements, but the core principles of focus, consistency, and measurement apply universally. Use the framework, then refine based on your specific results."),
    ],
}

_WORKSHEET_TEMPLATES = {
    "fitness": {
        "title": "My Over-50 Fitness Action Plan",
        "note": "Choose activities you enjoy. Start small and build gradually. Track daily.",
        "rows": [
            {"action": "List 3 low-impact activities I could do regularly (walking, swimming, cycling, etc.)"},
            {"action": "Choose one to start this week and schedule it in my calendar"},
            {"action": "Check if my current protein intake is enough for muscle maintenance"},
            {"action": "Set up a simple tracker for daily movement (steps, minutes, or activities)"},
            {"action": "Note my energy level each morning this week — look for patterns"},
            {"action": "Plan one active recovery day (gentle stretching or a short walk) this week"},
            {"action": "Identify one barrier to exercise and write one way to address it"},
        ],
    },
    "health": {
        "title": "My 30-Day Wellness Tracker",
        "note": "Check in with yourself daily. Small consistent habits create lasting results.",
        "rows": [
            {"action": "Write down 3 whole foods I'll prioritize adding to my diet this week"},
            {"action": "Set a daily water goal and track intake for 3 days"},
            {"action": "Note my average sleep hours this week and how I feel upon waking"},
            {"action": "Identify my top source of stress and one way to reduce it"},
            {"action": "Schedule one health screening or checkup I've been postponing"},
            {"action": "Replace one processed snack with a whole-food alternative"},
            {"action": "Spend 10 minutes outdoors each day and note my mood afterward"},
        ],
    },
    "finance": {
        "title": "My Financial Foundations Worksheet",
        "note": "Complete one section per week. Progress over perfection.",
        "rows": [
            {"action": "Calculate my total monthly income (after taxes)"},
            {"action": "List all monthly expenses — categorize as essential vs. discretionary"},
            {"action": "Set a monthly savings target (even $50 is a start) and automate it"},
            {"action": "List all outstanding debts with interest rates (highest first)"},
            {"action": "Start a simple spreadsheet to track spending for one month"},
            {"action": "Calculate my emergency fund goal (3-6 months of expenses)"},
            {"action": "Identify one unnecessary expense to reduce or eliminate this month"},
        ],
    },
    "legal": {
        "title": "My Business Legal Checklist",
        "note": "Check each item as you complete it. Consult a lawyer for items marked with **.",
        "rows": [
            {"action": "Choose a business structure (LLC, sole proprietorship, etc.)"},
            {"action": "Register my business name and check trademark availability **"},
            {"action": "Open a separate business bank account"},
            {"action": "Draft or review key contracts for clients or contractors **"},
            {"action": "Identify which intellectual property needs protection (trademark, copyright, NDA) **"},
            {"action": "Review my liability exposure and determine insurance needs"},
            {"action": "Set up a system for tracking business expenses and receipts"},
        ],
    },
    "dog": {
        "title": "My Dog Training Action Plan",
        "note": "Complete one row per training session. Check the box when done.",
        "rows": [
            {"action": "Identify my dog's primary trigger for unwanted behavior"},
            {"action": "Set up the environment to prevent the trigger (management)"},
            {"action": "Choose one command to teach this week"},
            {"action": "Gather treats and practice 3 sessions per day (5 min each)"},
            {"action": "Record one video of our training session to review progress"},
            {"action": "Reward calm behavior 10 times today, even when not training"},
            {"action": "Research one local positive-reinforcement trainer or class"},
        ],
    },
    "ai": {
        "title": "AI Model Evaluation Checklist",
        "note": "Rate each model 1-5 after testing with your actual prompts.",
        "rows": [
            {"action": "Define my top 3 use cases for the AI tool"},
            {"action": "List 5 test prompts that cover my most important tasks"},
            {"action": "Run the same prompts through 2-3 candidate models"},
            {"action": "Score output quality for each model (1=poor, 5=excellent)"},
            {"action": "Compare cost per 1,000 tokens or per month for expected usage"},
            {"action": "Check data-privacy and commercial-use terms for each option"},
            {"action": "Make a decision and set up my first project with the chosen model"},
        ],
    },
    "marketing": {
        "title": "My Funnel Setup Plan",
        "note": "Fill in each row as you complete the setup step.",
        "rows": [
            {"action": "Define my single most valuable offer"},
            {"action": "Write a 3-sentence description of my ideal customer"},
            {"action": "Create a lead magnet that solves one specific problem"},
            {"action": "Set up an email capture form (landing page or website)"},
            {"action": "Write a 5-email nurture sequence"},
            {"action": "Add UTM parameters to all links in my first campaign"},
            {"action": "Launch and review open rates after 3 days"},
        ],
    },
    "general": {
        "title": "My 30-Day Action Plan",
        "note": "Pick one action per day. Mark done when completed.",
        "rows": [
            {"action": "Define the single most important outcome I want this month"},
            {"action": "Write three measurable milestones that prove progress"},
            {"action": "Schedule a daily 15-minute block for this project"},
            {"action": "Complete the first milestone and note what worked"},
            {"action": "Complete the second milestone and note what slowed me down"},
            {"action": "Review notes and adjust my approach for the next week"},
            {"action": "Finish the third milestone while keeping the daily habit"},
        ],
    },
}


def _qr_point(title: str, body: str) -> str:
    return (
        f'<div class="bm-point">'
        f'<div class="bm-point-title">{_e(title)}</div>'
        f'<div class="bm-point-body">{_e(body)}</div>'
        f'</div>'
    )
