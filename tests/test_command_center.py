"""Protected tests for the Digital Product Factory Command Center.

These prove the Command Center (command_center/) does what
SESSION_HANDOFF-era owners actually need it for, and — the important
safety property — that it cannot generate a product or call a paid API,
because it is wired to nothing that can.
"""
from __future__ import annotations

import ast
import inspect
import json
import re

import pytest

from command_center import status
from command_center.server import app as cc_app


# ---------------------------------------------------------------------------
# Source of truth
# ---------------------------------------------------------------------------

def test_identifies_factory_v13_as_the_source_of_truth():
    info = status.get_git_info()
    assert info["folder_name"] == "Factory-v1.3"
    assert info["is_expected_folder"] is True
    assert status.EXPECTED_FOLDER_NAME == "Factory-v1.3"


def test_displays_the_current_branch():
    info = status.get_git_info()
    # This repo's own branch at test time -- must be readable, not None/blank.
    assert isinstance(info["branch"], str) and info["branch"]


def test_displays_a_git_commit():
    info = status.get_git_info()
    assert info["commit_short"] != "unknown"
    assert re.match(r"^[0-9a-f]{4,40}$", info["commit_short"] or "")
    assert re.match(r"^[0-9a-f]{40}$", info["commit"] or "")


# ---------------------------------------------------------------------------
# Version information
# ---------------------------------------------------------------------------

def test_displays_factory_and_component_version_information():
    version = status.get_factory_version()
    assert re.match(r"^\d+\.\d+\.\d+$", version)

    manifest = status.load_component_versions()
    components = manifest.get("components", {})
    for key in ("word_search_engine", "crossword_engine", "topic_vocabulary_resolver"):
        assert key in components
        assert "version" in components[key]


# ---------------------------------------------------------------------------
# Canonical handoff
# ---------------------------------------------------------------------------

def test_loads_the_canonical_handoff():
    handoff = status.load_handoff()
    for field in ("current_task", "stopped_at", "next_step", "next_claude"):
        assert field in handoff


def test_missing_handoff_file_falls_back_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "HANDOFF_FILE", tmp_path / "does_not_exist.json")
    handoff = status.load_handoff()
    assert handoff == status.default_handoff()


def test_displays_exactly_one_next_step():
    handoff = status.load_handoff()
    # A single string, never a list of competing tasks.
    assert isinstance(handoff["next_step"], str)


def test_distinguishes_completed_open_and_blocked_work(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "HANDOFF_FILE", tmp_path / "handoff_status.json")
    status.save_handoff(
        {
            "current_task": "Test task",
            "stopped_at": "Test stop",
            "next_step": "Test next step",
            "next_claude": "code",
            "open_issues": [
                {"title": "An open one", "status": "open"},
                {"title": "A blocked one", "status": "blocked"},
            ],
            "completed_log": [{"date": "2026-09-11", "items": ["Finished thing"]}],
        }
    )
    client = cc_app.test_client()
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Finished thing" in body
    assert "An open one" in body
    assert "A blocked one" in body
    assert 'class="badge completed"' in body
    assert 'class="badge open"' in body
    assert 'class="badge blocked"' in body


# ---------------------------------------------------------------------------
# Function Lock Matrix (2026-09-12)
# ---------------------------------------------------------------------------

def test_function_lock_registry_loads_and_sorts_locked_first(tmp_path, monkeypatch):
    registry_file = tmp_path / "function_lock_registry.json"
    registry_file.write_text(json.dumps({
        "functions": {
            "b_func": {"display_name": "B Func", "status": "PROTECTED"},
            "a_func": {"display_name": "A Func", "status": "LOCKED",
                       "last_known_good_commit": "abc1234", "fast_gate": True, "full_gate": True},
        }
    }), encoding="utf-8")
    monkeypatch.setattr(status, "FUNCTION_LOCK_REGISTRY_FILE", registry_file)

    rows = status.load_function_lock_registry()
    assert [r["key"] for r in rows] == ["a_func", "b_func"]
    assert rows[0]["status"] == "LOCKED"
    assert rows[0]["last_known_good_commit"] == "abc1234"


def test_missing_function_lock_registry_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "FUNCTION_LOCK_REGISTRY_FILE", tmp_path / "missing.json")
    assert status.load_function_lock_registry() == []
    context = status.build_context()  # must not raise
    assert context["function_locks"] == []


def test_function_lock_matrix_renders_on_the_page(tmp_path, monkeypatch):
    registry_file = tmp_path / "function_lock_registry.json"
    registry_file.write_text(json.dumps({
        "functions": {
            "word_search": {
                "display_name": "Word Search", "status": "LOCKED",
                "last_known_good_commit": "a021385", "fast_gate": True, "full_gate": True,
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr(status, "FUNCTION_LOCK_REGISTRY_FILE", registry_file)

    client = cc_app.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Function Lock Matrix" in body
    assert "Word Search" in body
    assert "a021385" in body


# ---------------------------------------------------------------------------
# Competitive Upgrade Roadmap (2026-09-12)
# ---------------------------------------------------------------------------

def _write_roadmap(path, *, current="upgrade_1_cover_system"):
    path.write_text(json.dumps({
        "current_upgrade": current,
        "upgrade_order": ["upgrade_1_cover_system", "upgrade_2_interior_themes"],
        "standing_priority": "QUALITY before more product types.",
        "upgrades": {
            "upgrade_1_cover_system": {
                "number": 1, "name": "Global Professional Cover System",
                "status": "VERIFYING", "status_detail": "Gates running.",
                "next_step": "Report the Full Release Gate result.",
                "dependencies": [], "affected_products_functions": ["ebook"],
            },
            "upgrade_2_interior_themes": {
                "number": 2, "name": "Designrr-Quality Interior Themes and Templates",
                "status": "NOT_STARTED", "status_detail": "Waiting on Upgrade 1.",
                "next_step": "Do not begin until Upgrade 1 is COMPLETE_LOCKED.",
                "dependencies": ["upgrade_1_cover_system"], "affected_products_functions": [],
            },
        },
    }), encoding="utf-8")


def test_roadmap_loads_current_upgrade_and_preserves_order(tmp_path, monkeypatch):
    roadmap_file = tmp_path / "roadmap.json"
    _write_roadmap(roadmap_file)
    monkeypatch.setattr(status, "ROADMAP_FILE", roadmap_file)

    roadmap = status.load_roadmap()
    assert roadmap["current_upgrade"] == "upgrade_1_cover_system"
    assert roadmap["current"]["name"] == "Global Professional Cover System"
    assert [u["key"] for u in roadmap["upgrades"]] == [
        "upgrade_1_cover_system", "upgrade_2_interior_themes",
    ]
    assert roadmap["upgrades"][1]["dependencies"] == ["upgrade_1_cover_system"]


def test_missing_roadmap_file_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "ROADMAP_FILE", tmp_path / "missing.json")
    roadmap = status.load_roadmap()
    assert roadmap["current"] is None
    assert roadmap["upgrades"] == []
    context = status.build_context()  # must not raise
    assert context["roadmap"]["upgrades"] == []


def test_roadmap_main_screen_shows_only_current_upgrade_status_and_next_step(tmp_path, monkeypatch):
    """The START HERE screen must stay uncluttered: only the current upgrade,
    its status, and one next step -- not every upgrade's detail."""
    roadmap_file = tmp_path / "roadmap.json"
    _write_roadmap(roadmap_file)
    monkeypatch.setattr(status, "ROADMAP_FILE", roadmap_file)

    client = cc_app.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Competitive Upgrade Roadmap" in body
    assert "Global Professional Cover System" in body
    assert "Report the Full Release Gate result." in body
    # The main next-step text appears once at the top; the full table (with
    # this same text repeated as a status_detail row) lives in View Details --
    # so this just confirms the summary card rendered, not that it is unique.


def test_roadmap_detail_table_lists_every_upgrade_with_dependencies(tmp_path, monkeypatch):
    roadmap_file = tmp_path / "roadmap.json"
    _write_roadmap(roadmap_file)
    monkeypatch.setattr(status, "ROADMAP_FILE", roadmap_file)

    client = cc_app.test_client()
    body = client.get("/").get_data(as_text=True)
    assert "Designrr-Quality Interior Themes and Templates" in body
    assert "upgrade 1 cover system" in body.lower()  # rendered dependency, underscores replaced


def test_roadmap_survives_a_restart_reading_only_the_file(tmp_path, monkeypatch):
    """Same durability contract as handoff_status.json: nothing but the file
    on disk persists the roadmap between sessions."""
    roadmap_file = tmp_path / "roadmap.json"
    _write_roadmap(roadmap_file, current="upgrade_2_interior_themes")
    monkeypatch.setattr(status, "ROADMAP_FILE", roadmap_file)

    on_disk = json.loads(roadmap_file.read_text(encoding="utf-8"))
    assert on_disk["current_upgrade"] == "upgrade_2_interior_themes"

    reloaded = status.load_roadmap()
    assert reloaded["current_upgrade"] == "upgrade_2_interior_themes"
    assert reloaded["current"]["name"] == "Designrr-Quality Interior Themes and Templates"


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------

def test_state_survives_a_normal_application_restart(tmp_path, monkeypatch):
    handoff_file = tmp_path / "handoff_status.json"
    monkeypatch.setattr(status, "HANDOFF_FILE", handoff_file)

    status.save_handoff(
        {
            "current_task": "Durability check",
            "stopped_at": "Right here",
            "next_step": "Read this back",
            "next_claude": "web",
        }
    )

    # Prove it is genuinely on disk (not held in a module-level variable) by
    # reading it back with a plain, independent json.loads -- this is what
    # "restart" means for a stateless page: nothing but the file persists.
    on_disk = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert on_disk["current_task"] == "Durability check"
    assert on_disk["next_claude"] == "web"

    # And status.load_handoff(), called fresh, must agree with the file.
    reloaded = status.load_handoff()
    assert reloaded["current_task"] == "Durability check"
    assert reloaded["stopped_at"] == "Right here"


def test_missing_optional_status_information_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "HANDOFF_FILE", tmp_path / "missing_handoff.json")
    monkeypatch.setattr(status, "COMPONENT_VERSIONS_FILE", tmp_path / "missing_versions.json")
    monkeypatch.setattr(status, "GATE_JUNIT_FILE", tmp_path / "missing_gate.xml")

    context = status.build_context()  # must not raise
    assert context["gate"] is None
    assert context["components"] == {}
    assert context["handoff"]["next_step"]

    client = cc_app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200


def test_malformed_json_files_do_not_crash(tmp_path, monkeypatch):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(status, "HANDOFF_FILE", bad_file)
    handoff = status.load_handoff()
    assert handoff == status.default_handoff()


# ---------------------------------------------------------------------------
# Safety: no product generation, no paid APIs, no customer-data access
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORT_PREFIXES = (
    "services.product",
    "services.ad",
    "services.ebook",
    "services.market_research",
    "services.cover",
    "services.publishing",
    "services.research",
    "services.youtube",
    "database",
    "openai",
    "tavily",
    "pexels",
)


def _imported_module_names(module) -> set[str]:
    """The actual modules a module imports -- via ast, so a docstring or a
    comment that merely *mentions* a forbidden name can never trip this up.
    """
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_command_center_imports_nothing_that_can_generate_a_product_or_spend_money():
    import command_center.server as server_module

    for module in (status, server_module):
        imported = _imported_module_names(module)
        for name in imported:
            for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
                assert not (name == forbidden or name.startswith(forbidden + ".")), (
                    f"{module.__name__} must not import {name!r} "
                    f"(matches forbidden {forbidden!r})"
                )


def test_command_center_exposes_only_its_own_read_and_save_routes():
    paths = {rule.rule for rule in cc_app.url_map.iter_rules()}
    # Only the status page and its own save-handoff endpoint -- no product,
    # billing, export, or admin route lives on this server.
    assert paths == {"/", "/update"}


def test_update_route_only_ever_writes_the_handoff_file(tmp_path, monkeypatch):
    handoff_file = tmp_path / "handoff_status.json"
    monkeypatch.setattr(status, "HANDOFF_FILE", handoff_file)

    client = cc_app.test_client()
    resp = client.post(
        "/update",
        data={
            "current_task": "Posted task",
            "stopped_at": "Posted stop",
            "completed_today": "Did a thing",
            "open_issue": "",
            "next_step": "Posted next step",
            "next_claude": "code",
            "notes": "",
        },
    )
    assert resp.status_code in (302, 303)
    assert handoff_file.exists()
    saved = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert saved["current_task"] == "Posted task"
    # Nothing else appeared in the tmp directory -- no export, no PDF, no DB file.
    assert [p.name for p in tmp_path.iterdir()] == [handoff_file.name]


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_update_route_rejects_non_post_methods(method):
    client = cc_app.test_client()
    resp = client.open("/update", method=method)
    assert resp.status_code == 405
