"""Math Worksheet Builder — generates grade-appropriate math problems.

Fully local / procedural generator. No OpenAI, no network, no Tavily.
The math worksheet never falls back to ebook or any other product type.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Local procedural math problem generator — no OpenAI, no network
# ---------------------------------------------------------------------------

def _normalize_grade_label(grade: str) -> str:
    """Return 'Grade N' once — UI already sends 'Grade 6', not bare '6'."""
    raw = str(grade or "3").strip()
    if not raw:
        raw = "3"
    stripped = re.sub(r"(?i)^grades?\s*", "", raw).strip()
    if not stripped:
        stripped = "3"
    return f"Grade {stripped}"


def _resolve_topic_and_ops(topic: str) -> tuple[str, list[str]]:
    """Map UI topic to display label + operation list.

    Single-operation topics keep their label and force that op exclusively.
    Intentionally mixed topics (or unknown) display as 'Mixed Operations'.
    """
    topic_l = str(topic or "").strip().lower()
    if any(t in topic_l for t in ["add", "plus", "sum"]):
        return "Addition", ["+"]
    if any(t in topic_l for t in ["subtract", "minus", "difference"]):
        return "Subtraction", ["-"]
    if any(t in topic_l for t in ["multiplic", "multiply", "times", "product"]):
        return "Multiplication", ["*"]
    if any(t in topic_l for t in ["divid", "division", "quotient"]):
        return "Division", ["/"]
    if any(t in topic_l for t in ["fraction", "fractions"]):
        # Fractions practice uses a restricted mixed set; keep topic name.
        return (str(topic or "Fractions").strip() or "Fractions"), ["+", "-", "*"]
    # Default / Decimals / Algebra / Geometry / Word Problems → mixed ops
    if topic_l in ("", "mixed", "mixed arithmetic", "mixed operations"):
        return "Mixed Operations", ["+", "-", "*", "/"]
    # Keep specific non-op topic names but generate mixed practice.
    label = str(topic or "Mixed Operations").strip() or "Mixed Operations"
    return label, ["+", "-", "*", "/"]


def _generate_local_problems(
    count: int,
    grade: str,
    topic: str,
    difficulty: str,
    include_challenge: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Generate math problems procedurally. Fully local — no API calls.

    Args:
        count: number of main problems to generate.
        grade: grade level (e.g. "3" for Grade 3).
        topic: math topic (e.g. "Mixed Arithmetic", "Fractions").
        difficulty: "Easy" | "Medium" | "Hard".
        include_challenge: if True, also generate 1-3 challenge problems
            for the bonus section. Default False.

    Returns:
        (main_problems, challenge_problems)
    """
    problems = []
    difficulty_val = str(difficulty or "Medium").strip().lower()

    # Determine number ranges by grade
    grade_num = int(re.sub(r"[^0-9]", "", str(grade or "3").strip()) or "3")
    if grade_num <= 2:
        a_max, b_max = 20, 10
    elif grade_num <= 4:
        a_max, b_max = 100, 50
    elif grade_num <= 6:
        a_max, b_max = 500, 100
    else:
        a_max, b_max = 1000, 200

    _label, ops = _resolve_topic_and_ops(topic)

    for i in range(count):
        op = ops[i % len(ops)]
        if op == "+":
            a = random.randint(1, a_max)
            b = random.randint(1, b_max)
            ans = a + b
            expr = f"{a} + {b} = ?"
        elif op == "-":
            a = random.randint(b_max + 1, a_max + b_max)
            b = random.randint(1, min(a - 1, b_max))
            ans = a - b
            expr = f"{a} - {b} = ?"
        elif op == "*":
            if difficulty_val == "easy":
                a = random.randint(2, 5)
                b = random.randint(2, 10)
            elif difficulty_val == "hard":
                a = random.randint(5, 12)
                b = random.randint(5, 12)
            else:
                a = random.randint(2, 10)
                b = random.randint(2, 12)
            ans = a * b
            # ASCII operators keep PDF typography stable (no Type1 fallback).
            expr = f"{a} x {b} = ?"
        else:  # division
            b = random.randint(2, 12)
            ans = random.randint(2, 12)
            a = b * ans
            expr = f"{a} / {b} = ?"

        problems.append({
            "number": i + 1,
            "expression": expr,
            "answer": str(ans),
            "hint": "",
            "operation": op,
        })

    challenges = []
    if include_challenge:
        # 1-3 challenges depending on count. Only for medium/hard difficulty.
        if difficulty_val in ("medium", "hard"):
            challenge_count = min(3, max(1, count // 4 + 1))
        else:
            challenge_count = 1
        # Challenge section follows the selected topic when it is a single op.
        challenge_ops = ops if len(ops) == 1 else ["*", "/"]
        for i in range(challenge_count):
            op = challenge_ops[i % len(challenge_ops)]
            if op == "+":
                a = random.randint(50, 200)
                b = random.randint(50, 200)
                ans = a + b
                expr = f"{a} + {b} = ?"
            elif op == "-":
                a = random.randint(100, 300)
                b = random.randint(20, 99)
                ans = a - b
                expr = f"{a} - {b} = ?"
            elif op == "*":
                a = random.randint(8, 15)
                b = random.randint(8, 15)
                ans = a * b
                expr = f"{a} x {b} = ?"
            else:
                b = random.randint(8, 15)
                ans = random.randint(8, 15)
                a = b * ans
                expr = f"{a} / {b} = ?"
            challenges.append({
                "number": i + 1,
                "expression": expr,
                "answer": str(ans),
                "hint": "",
                "operation": op,
            })

    return problems, challenges


@dataclass
class MathProblem:
    number: int
    expression: str  # e.g. "24 + 17 = ?"
    answer: float | int | str
    hint: str = ""

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "expression": self.expression,
            "answer": self.answer,
            "hint": self.hint,
        }


@dataclass
class MathWorksheetResult:
    title: str
    subtitle: str
    grade: str
    math_topic: str
    difficulty: str
    problems: list[MathProblem]
    challenge_problems: list[MathProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    solution_only: list[MathProblem] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "grade": self.grade,
            "math_topic": self.math_topic,
            "difficulty": self.difficulty,
            "problems": [p.as_dict() for p in self.problems],
            "challenge_problems": [p.as_dict() for p in self.challenge_problems],
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _parse_math_response(raw: dict | str, count: int) -> tuple[list[dict], list[dict]]:
    """Kept for backwards compatibility with any caller that still passes AI
    output. Math Worksheet no longer uses AI; problems are fully procedural.
    """
    if isinstance(raw, str):
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                import json as _json
                raw = _json.loads(match.group(1))
            except Exception:
                pass

    data = raw if isinstance(raw, dict) else {}
    problems = data.get("problems", [])
    challenges = data.get("challenge_problems", [])
    if not isinstance(problems, list):
        problems = []
    if not isinstance(challenges, list):
        challenges = []
    return problems, challenges


def build_math_worksheet(
    *,
    worksheet_title: str = "",
    grade: str = "3",
    math_topic: str = "",
    difficulty: str = "Medium",
    problem_count: int = 20,
    include_answer_key: bool = True,
    include_challenge: bool = False,
) -> MathWorksheetResult:
    """
    Generate a math worksheet with grade-appropriate, verified problems.

    Fully local / procedural — no OpenAI, no network. The math worksheet never
    depends on an API key; if the .env is missing the worksheet still works.

    Args:
        include_challenge: if True, also generate 1-3 challenge problems for the
            bonus section AND include their answers in the answer key. Default
            False. When False, no challenge problems are generated.
    """
    title = str(worksheet_title or "Math Worksheet").strip()
    topic_raw = str(math_topic or "").strip()
    grade_val = _normalize_grade_label(grade)
    difficulty_val = str(difficulty or "Medium").strip()
    topic, _ops = _resolve_topic_and_ops(topic_raw)

    # Local procedural generation only — no AI dependency.
    problems_raw, challenges_raw = _generate_local_problems(
        problem_count, grade_val, topic_raw or topic, difficulty_val,
        include_challenge=bool(include_challenge),
    )

    if not problems_raw:
        return MathWorksheetResult(
            title=title,
            subtitle="",
            grade=grade_val,
            math_topic=topic,
            difficulty=difficulty_val,
            problems=[],
            errors=["Failed to generate math problems (local procedural generator returned no problems)."],
        )

    # Build problem objects
    problems: list[MathProblem] = []
    for i, entry in enumerate(problems_raw[:problem_count]):
        problems.append(MathProblem(
            number=i + 1,
            expression=str(entry.get("expression", "")).strip(),
            answer=str(entry.get("answer", "")),
            hint=str(entry.get("hint", "")),
        ))

    challenges: list[MathProblem] = []
    for i, entry in enumerate(challenges_raw[:3]):
        challenges.append(MathProblem(
            number=i + 1,
            expression=str(entry.get("expression", "")).strip(),
            answer=str(entry.get("answer", "")),
            hint=str(entry.get("hint", "")),
        ))

    # Verify: check all problems have expressions and answers
    missing = [p for p in problems if not p.expression or not p.answer]
    if missing:
        return MathWorksheetResult(
            title=title,
            subtitle="",
            grade=grade_val,
            math_topic=topic,
            difficulty=difficulty_val,
            problems=[],
            errors=[
                f"{len(missing)} generated problem(s) had empty expression or answer. "
                "Local procedural generator produced an invalid result."
            ],
        )

    return MathWorksheetResult(
        title=title,
        subtitle="",
        grade=grade_val,
        math_topic=topic,
        difficulty=difficulty_val,
        problems=problems,
        challenge_problems=challenges,
    )
