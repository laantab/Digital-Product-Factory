"""Allow only documented, conditional skips in the strict release gate."""
from __future__ import annotations

import xml.etree.ElementTree as ET


# This test is explicitly conditional: it verifies that a real, preserved
# Project 351 export is untouched *when that customer's local export exists*.
# Ordinary checkouts do not contain customer exports, so its documented
# skip is expected there. Every other skip remains a gate failure.
_APPROVED_CONDITIONAL_SKIPS = {
    (
        "tests.test_warm_wellness_template.RevisionIdentityAndIsolation",
        "test_preserved_project_351_package_is_untouched_if_present",
    ): "Project 351 preserved package not present on this machine",
}


def classify_junit_skips(root: ET.Element) -> tuple[list[str], list[str]]:
    """Return (approved, unexpected) skip labels from a parsed JUnit root.

    A skip is approved only when both its exact test id and its documented
    reason match. Renames, changed reasons, and every other skipped test fail
    closed until deliberately reviewed.
    """
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    approved: list[str] = []
    unexpected: list[str] = []
    for suite in suites:
        for case in suite.findall("testcase"):
            skipped = case.find("skipped")
            if skipped is None:
                continue
            class_name = case.get("classname", "")
            test_name = case.get("name", "")
            label = f"{class_name}::{test_name}"
            expected_reason = _APPROVED_CONDITIONAL_SKIPS.get((class_name, test_name))
            details = " ".join((skipped.get("message", ""), skipped.text or ""))
            if expected_reason and expected_reason in details:
                approved.append(label)
            else:
                unexpected.append(label)
    return approved, unexpected
