import xml.etree.ElementTree as ET

from scripts.release_gate_skip_policy import classify_junit_skips


def _root(class_name, test_name, reason):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    case = ET.SubElement(suite, "testcase", classname=class_name, name=test_name)
    ET.SubElement(case, "skipped", message=reason)
    return root


def test_only_project_351_missing_local_export_skip_is_approved():
    root = _root(
        "tests.test_warm_wellness_template.RevisionIdentityAndIsolation",
        "test_preserved_project_351_package_is_untouched_if_present",
        "Project 351 preserved package not present on this machine",
    )

    approved, unexpected = classify_junit_skips(root)

    assert approved == [
        "tests.test_warm_wellness_template.RevisionIdentityAndIsolation::"
        "test_preserved_project_351_package_is_untouched_if_present"
    ]
    assert unexpected == []


def test_any_other_skip_remains_a_gate_failure():
    root = _root("tests.test_example.Example", "test_unexpected_skip", "not expected")

    approved, unexpected = classify_junit_skips(root)

    assert approved == []
    assert unexpected == ["tests.test_example.Example::test_unexpected_skip"]


def test_project_351_skip_with_a_changed_reason_remains_a_gate_failure():
    root = _root(
        "tests.test_warm_wellness_template.RevisionIdentityAndIsolation",
        "test_preserved_project_351_package_is_untouched_if_present",
        "unexpected condition",
    )

    approved, unexpected = classify_junit_skips(root)

    assert approved == []
    assert unexpected == [
        "tests.test_warm_wellness_template.RevisionIdentityAndIsolation::"
        "test_preserved_project_351_package_is_untouched_if_present"
    ]


def test_no_skips_returns_empty_lists():
    root = ET.Element("testsuites")

    assert classify_junit_skips(root) == ([], [])
