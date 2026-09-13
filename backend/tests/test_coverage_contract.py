"""Issue #63: machine-enforced hosted-safe backend test coverage contract."""

from __future__ import annotations

from pathlib import Path

import coverage_policy
from coverage_policy import discover_test_modules, inventory_errors, load_inventory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def test_every_backend_test_module_is_classified() -> None:
    assert inventory_errors() == []
    inventory = load_inventory()
    assert set(inventory) == discover_test_modules()


def test_new_unclassified_test_module_fails_inventory_guard(monkeypatch) -> None:
    discovered = set(load_inventory()) | {"tests/test_new_unclassified.py"}
    monkeypatch.setattr(coverage_policy, "discover_test_modules", lambda: discovered)
    errors = coverage_policy.inventory_errors()
    assert errors == ["unclassified test modules: ['tests/test_new_unclassified.py']"]


def test_local_only_and_external_exclusions_are_explicitly_reasoned() -> None:
    inventory = load_inventory()
    excluded = {
        path: entry
        for path, entry in inventory.items()
        if entry["classification"] != "HOSTED_SAFE"
    }
    assert excluded, "current inventory is expected to document evidence-based local-only modules"
    for path, entry in excluded.items():
        assert entry["classification"] in {"LOCAL_ONLY", "EXTERNAL_PROHIBITED", "OBSOLETE/DEAD"}
        assert len(entry["reason"].strip()) >= 20, path


def test_security_and_provenance_regressions_remain_hosted_safe() -> None:
    inventory = load_inventory()
    required = {
        "tests/taskpack/test_issue_56_external_resource_policy.py",
        "tests/taskpack/test_external_worker_launcher.py",
        "tests/test_dl06_return_candidates.py",
        "tests/test_dl06_return_protocol.py",
        "tests/test_dl06_formal_cognition_adapter.py",
        "tests/test_dl08a_provenance_closure.py",
        "tests/test_dl08k1_reuse_trace.py",
    }
    assert all(inventory[path]["classification"] == "HOSTED_SAFE" for path in required)


def test_hosted_ci_uses_directory_discovery_not_filename_allowlist() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "i8-ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest tests -q" in workflow
    assert "tests/test_" not in workflow
