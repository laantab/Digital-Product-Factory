"""Narrow independent checks prompted by actual fresh-book review.

These reject known defects; passing is not a marketability certification.
Author-supplied manuscripts and existing editions are not rewritten.
"""
import re


def title_issues(title):
    if re.match(r"^\s*(?:hypothetical|sample title|example title|working title)\s*:",title,re.I):
        return ['Remove the internal example label from the reader-facing title.']
    return []


def chapter_issues(chapter):
    text=chapter['text']
    issues=[]
    # A claim that a tool is supplied must be supported by an actual tool,
    # rather than paragraphs telling readers to invent their own checklist.
    promised=re.search(r'\b(?:checklists? (?:provided|below|included)|(?:use|follow|complete|see) (?:a|the) (?:final )?checklist)\b',text,re.I)
    items=re.findall(r'(?m)^\s*(?:\[\s?\]|[-*\u2022]|\d+[.)]|Check:)\s+\S',text)
    if promised and len(items)<3:
        issues.append('The chapter refers to a supplied checklist but supplies no usable checklist. Include at least three concrete action items on separate lines, each ending with a complete sentence.')
    # Specific implausible instruction observed in the test. Broader practical
    # usefulness still requires independent model and human review.
    if re.search(r'\bstack(?:ing)?\s+(?:the\s+)?folding tables\b',text,re.I):
        issues.append('Do not stack folding tables to create a dining surface. Use an existing table in its intended stable configuration, or simplify the gathering setup.')
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        # Negated safety instructions are allowed; these narrow patterns flag
        # the affirmative recommendations actually observed in the pilot.
        if re.search(r"\b(?:never|not|avoid|don't)\b",sentence,re.I):continue
        if re.search(r'\bstack(?:ing)?\s+(?:(?:two|three|\d+|the)\s+)?(?:air\s+)?mattress(?:es)?\b',sentence,re.I):
            issues.append('Do not stack mattresses. Use an available bed or mattress in its intended stable configuration.')
        if re.search(r'\b(?:use|using|place|put|set up|stack)\b[^.!?]{0,100}\b(?:air\s+)?mattress(?:es)?\b[^.!?]{0,60}\bhallways?\b',sentence,re.I):
            issues.append('Do not use hallways as sleeping areas. Keep circulation paths and exits clear; choose an existing safe sleeping space or reduce the overnight guest count.')
    return issues


def book_issues(book):
    if book.get('source')!='local_model':
        return []
    return title_issues(book['title'])+[issue for chapter in book['chapters'] for issue in chapter_issues(chapter)]
