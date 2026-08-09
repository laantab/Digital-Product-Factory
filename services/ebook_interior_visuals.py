"""Local, readable ebook diagrams / worksheets (HTML tables — no AI images)."""
from __future__ import annotations

import html
import re
from typing import Any


def _e(s: str) -> str:
    return html.escape(str(s or ""))


def is_screens_parenting_topic(title: str, topic: str = "", content: str = "") -> bool:
    blob = f"{title} {topic} {content[:800]}".lower()
    return any(
        k in blob
        for k in (
            "screen",
            "tablet",
            "digital media",
            "co-view",
            "toddler",
            "preschool",
            "parent",
        )
    )


def screens_visual_plan(chapter_titles: list[str]) -> list[dict[str, Any]]:
    """Attach topic-specific local aids to chapters for Screens with Purpose-class books."""
    catalog = [
        _aid_balance_diagram(),
        _aid_content_checklist(),
        _aid_coview_script(),
        _aid_end_routine(),
        _aid_decision_chart(),
        _aid_stop_switch_sequence(),
        _aid_family_screen_plan(),
    ]
    chapters: list[dict[str, Any]] = []
    for idx, name in enumerate(chapter_titles):
        aids = []
        if idx < len(catalog):
            aids.append(catalog[idx])
        elif idx == len(chapter_titles) - 1:
            aids.append(_aid_family_screen_plan())
        chapters.append({"chapter": name, "aids": aids})
    # Ensure every required visual appears at least once
    present = {a.get("title") for ch in chapters for a in ch.get("aids") or []}
    for aid in catalog:
        if aid["title"] not in present and chapters:
            chapters[min(len(chapters) - 1, catalog.index(aid))]["aids"].append(aid)
    return chapters


def _wrap(aid_type: str, title: str, body_html: str, caption: str, visual_id: str) -> dict:
    return {
        "type": aid_type,
        "title": title,
        "caption": caption,
        "visual_id": visual_id,
        "body": body_html,
        "html": body_html,
    }


def _aid_balance_diagram() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th colspan="3">Screens Support, Not Replace</th></tr>
<tr>
  <td width="33%"><b>Connection first</b><br/>Play, talk, books, outdoor time</td>
  <td width="34%"><b>Screens as a tool</b><br/>Learning apps, co-viewed shows, video calls</td>
  <td width="33%"><b>Protect basics</b><br/>Sleep, meals, movement, calm transitions</td>
</tr>
<tr><td colspan="3" style="text-align:center;"><b>Balance goal:</b> screens support family life — they do not become the default babysitter.</td></tr>
</table>
"""
    return _wrap(
        "diagram",
        "Screens Support, Not Replace",
        body,
        "Use this as a quick family check: what did screens support today, and what did they replace?",
        "v_balance",
    )


def _aid_content_checklist() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th>Age / content check</th><th>Yes</th><th>Not yet</th></tr>
<tr><td>Matches my child's age and temperament</td><td>☐</td><td>☐</td></tr>
<tr><td>Slow pace, clear language, kind characters</td><td>☐</td><td>☐</td></tr>
<tr><td>I can explain the main idea in one sentence</td><td>☐</td><td>☐</td></tr>
<tr><td>No pressure to buy, binge, or keep scrolling</td><td>☐</td><td>☐</td></tr>
<tr><td>Leaves room for talk, play, or a follow-up activity</td><td>☐</td><td>☐</td></tr>
</table>
"""
    return _wrap(
        "checklist",
        "The Three-Question Content Check",
        body,
        "If two or more boxes land in “Not yet,” choose different content or shorten the session.",
        "v_content_check",
    )


def _aid_coview_script() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th>Co-viewing conversation example</th></tr>
<tr><td>
<p><b>Parent:</b> “What do you think that character is feeling?”</p>
<p><b>Child:</b> “Mad. The tower fell.”</p>
<p><b>Parent:</b> “Yes — frustrated. What could they try next?”</p>
<p><b>Child:</b> “Build it again. Ask for help.”</p>
<p><b>Parent:</b> “Great ideas. After this episode, let’s build something with blocks for five minutes.”</p>
</td></tr>
</table>
"""
    return _wrap(
        "tip",
        "A Co-Viewing Conversation You Can Steal",
        body,
        "Short, warm questions turn screen time into language practice.",
        "v_coview",
    )


def _aid_end_routine() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th colspan="4">Calm end-of-screen routine</th></tr>
<tr>
  <td><b>1. Warn</b><br/>“Two more minutes.”</td>
  <td><b>2. Choose close</b><br/>Save / finish / pause together</td>
  <td><b>3. Switch</b><br/>Offer the next activity</td>
  <td><b>4. Connect</b><br/>Snack, story, or stretch</td>
</tr>
</table>
"""
    return _wrap(
        "flowchart",
        "A Calmer Way to End Tablet Time",
        body,
        "Predictable steps reduce bargaining more than sudden shut-offs.",
        "v_end_routine",
    )


def _aid_decision_chart() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th></th><th>Convenient (sometimes OK)</th><th>Default (rethink)</th></tr>
<tr><td><b>When</b></td><td>Travel, illness, short wait</td><td>Every meal / every evening</td></tr>
<tr><td><b>Who</b></td><td>Parent nearby or co-viewing</td><td>Solo for long stretches</td></tr>
<tr><td><b>Why</b></td><td>Specific purpose (calm, learn, connect)</td><td>“Just because” / fill boredom</td></tr>
<tr><td><b>After</b></td><td>Clear next activity</td><td>Meltdown or more scrolling</td></tr>
</table>
"""
    return _wrap(
        "table",
        "Convenient versus Default",
        body,
        "Convenience is a tool. Default is a habit. Name which one you are choosing.",
        "v_convenient",
    )


def _aid_stop_switch_sequence() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th colspan="3">Stop · Switch · Self-regulate</th></tr>
<tr>
  <td width="33%"><b>Stop</b><br/>Pause the device together. Breathe once.</td>
  <td width="34%"><b>Switch</b><br/>Name the next activity out loud.</td>
  <td width="33%"><b>Self-regulate</b><br/>Water, stretch, cuddle, or quiet corner.</td>
</tr>
</table>
"""
    return _wrap(
        "diagram",
        "Stop-Switch-Self-Regulate Practice",
        body,
        "Practice when everyone is calm so it is available when feelings run high.",
        "v_stop_switch",
    )


def _aid_family_screen_plan() -> dict:
    body = """
<table class="va-table" width="100%">
<tr><th colspan="2">Family Screen Plan (printable)</th></tr>
<tr><td width="40%">Week of</td><td>________________________</td></tr>
<tr><td>Daily window(s)</td><td>________________________</td></tr>
<tr><td>Allowed places</td><td>________________________</td></tr>
<tr><td>Co-view shows/apps</td><td>________________________</td></tr>
<tr><td>Device bedtime</td><td>________________________</td></tr>
<tr><td>Weekend exception</td><td>________________________</td></tr>
<tr><td>If conflict happens, we will</td><td>________________________</td></tr>
<tr><td>Parent signature</td><td>________________________</td></tr>
</table>
"""
    return _wrap(
        "worksheet",
        "One-Page Family Screen Plan",
        body,
        "Post on the fridge. Review weekly — adjust without shame.",
        "v_family_plan",
    )


GENERIC_HEADING_MAP_SCREENS = {
    "what this chapter helps you solve and why it matters": None,  # filled per chapter
    "a step-by-step method": None,
    "common mistakes": None,
    "chapter takeaway": None,
}


def rewrite_mechanical_headings(content_md: str, *, title: str = "", topic: str = "") -> str:
    """Replace rigid repeated H3 labels with topic-specific labels when possible."""
    if not is_screens_parenting_topic(title, topic, content_md):
        # Generic soft rewrite for all ebooks
        replacements = [
            (r"(?im)^###\s*What this chapter helps you solve.*$", "### What you will put into practice"),
            (r"(?im)^###\s*A step-by-step method\s*$", "### How to do this in real life"),
            (r"(?im)^###\s*Common mistakes\s*$", "### Watch-outs that trip families up"),
            (r"(?im)^###\s*Chapter takeaway\s*$", "### Your next useful move"),
        ]
        out = content_md
        for pat, repl in replacements:
            out = re.sub(pat, repl, out)
        return out

    # Screens / parenting: rotate descriptive labels by chapter occurrence
    takeaways = [
        "Your Screen-Purpose Decision",
        "What to Try at Dinner Tonight",
        "The Three-Question Content Check",
        "A Calmer Way to End Tablet Time",
        "Convenient versus Default",
        "Stop-Switch-Self-Regulate",
        "Your Family Screen Plan Check-In",
        "Age-Specific Examples to Reuse",
        "A Short Implementation Challenge",
    ]
    methods = [
        "A realistic family scenario",
        "A decision guide for busy evenings",
        "A content-quality walkthrough",
        "A co-viewing conversation example",
        "A transition script you can copy",
        "A sample daily routine",
        "Troubleshooting guidance",
        "Age-specific examples",
        "Try this for seven days",
    ]
    why_labels = [
        "Why this matters for toddlers and preschoolers",
        "Why conflict spikes — and how to lower it",
        "Why content quality beats minutes alone",
        "Why co-viewing changes what kids take away",
        "Why endings matter more than openings",
        "Why defaults beat willpower",
        "Why practice beats lectures",
        "Why one shared plan helps the whole house",
        "Why small experiments beat overnight bans",
    ]
    mistakes = [
        "Patterns that quietly raise conflict",
        "Content traps to skip",
        "Transition mistakes that invite bargaining",
        "Routine leaks that grow over time",
        "Well-meant rules that backfire",
        "Comparison traps from other families",
        "Overcorrecting after a hard day",
        "All-or-nothing resets",
        "Skipping repair after conflict",
    ]

    out_lines: list[str] = []
    ch_idx = -1
    ti = mi = wi = ki = 0
    for line in content_md.splitlines():
        if re.match(r"^##\s+", line):
            ch_idx += 1
        low = line.strip().lower()
        if re.match(r"^###\s*what this chapter helps", low):
            label = why_labels[min(wi, len(why_labels) - 1)]
            wi += 1
            out_lines.append(f"### {label}")
            continue
        if re.match(r"^###\s*a step-by-step method", low):
            label = methods[min(mi, len(methods) - 1)]
            mi += 1
            out_lines.append(f"### {label}")
            continue
        if re.match(r"^###\s*common mistakes", low):
            label = mistakes[min(ki, len(mistakes) - 1)]
            ki += 1
            out_lines.append(f"### {label}")
            continue
        if re.match(r"^###\s*chapter takeaway", low):
            label = takeaways[min(ti, len(takeaways) - 1)]
            ti += 1
            out_lines.append(f"### {label}")
            continue
        # Prose/label forms without markdown heading markers
        m_take = re.match(r"^(?:\*\*)?chapter takeaway(?:\*\*)?\s*[:.\-]\s*(.*)$", low, re.I)
        if m_take or re.match(r"^chapter takeaway\s*$", low):
            label = takeaways[min(ti, len(takeaways) - 1)]
            ti += 1
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            out_lines.append(f"### {label}")
            if rest:
                out_lines.append(rest)
            continue
        m_step = re.match(r"^(?:\*\*)?a step-by-step method(?:\*\*)?\s*[:.\-]?\s*$", low)
        if m_step:
            label = methods[min(mi, len(methods) - 1)]
            mi += 1
            out_lines.append(f"### {label}")
            continue
        m_mist = re.match(r"^(?:\*\*)?common mistakes(?: to avoid)?(?:\*\*)?\s*[:.\-]?\s*$", low)
        if m_mist:
            label = mistakes[min(ki, len(mistakes) - 1)]
            ki += 1
            out_lines.append(f"### {label}")
            continue
        # Strip duplicate "Chapter N" inside titles
        m = re.match(r"^(##\s+)Chapter\s+\d+\s*[:.\-]\s*(.+)$", line, re.I)
        if m:
            out_lines.append(f"{m.group(1)}{m.group(2).strip()}")
            continue
        out_lines.append(line)
    out = "\n".join(out_lines)
    # Final scrub of leftover prose labels (including mid-line forms)
    out = re.sub(r"(?i)\bchapter takeaway\s*:\s*", "", out)
    out = re.sub(r"(?i)\ba step-by-step method\s*:\s*", "", out)
    out = re.sub(r"(?i)\bcommon mistakes to avoid\s*:\s*", "", out)
    return out
