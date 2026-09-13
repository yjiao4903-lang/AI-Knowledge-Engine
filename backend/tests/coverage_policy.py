"""Hosted-safe pytest coverage classification for Issue #63.

The checked-in inventory is the single classification authority for backend
``test_*.py`` modules. Pytest discovers the filesystem normally; this helper
only prevents explicitly classified LOCAL_ONLY / EXTERNAL_PROHIBITED modules
from being imported by the hosted/default run.

A newly added test module that is missing from the inventory fails collection
instead of silently falling outside CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = TESTS_ROOT.parent
INVENTORY_PATH = TESTS_ROOT / "coverage_inventory.json"
ALLOWED_CLASSIFICATIONS = {"HOSTED_SAFE", "LOCAL_ONLY", "EXTERNAL_PROHIBITED", "OBSOLETE/DEAD"}


def load_inventory() -> dict[str, dict[str, str]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported coverage inventory schema")
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        raise RuntimeError("coverage inventory modules must be an object")
    return modules


def discover_test_modules() -> set[str]:
    return {
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in TESTS_ROOT.rglob("test_*.py")
        if path.is_file()
    }


def inventory_errors() -> list[str]:
    modules = load_inventory()
    discovered = discover_test_modules()
    declared = set(modules)
    errors: list[str] = []

    missing = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    if missing:
        errors.append(f"unclassified test modules: {missing}")
    if stale:
        errors.append(f"inventory entries without test modules: {stale}")

    for path, entry in sorted(modules.items()):
        if not isinstance(entry, dict):
            errors.append(f"{path}: inventory entry must be an object")
            continue
        classification = entry.get("classification")
        reason = entry.get("reason")
        if classification not in ALLOWED_CLASSIFICATIONS:
            errors.append(f"{path}: invalid classification {classification!r}")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{path}: classification requires a non-empty reason")
    return errors


def classification_for(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(BACKEND_ROOT.resolve()).as_posix()
    except ValueError:
        return "HOSTED_SAFE"
    entry = load_inventory().get(rel)
    if entry is None:
        raise pytest.UsageError(
            f"Issue #63 coverage contract: {rel} is an unclassified test module"
        )
    classification = entry.get("classification")
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise pytest.UsageError(
            f"Issue #63 coverage contract: {rel} has invalid classification {classification!r}"
        )
    return classification


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("hosted-safe coverage")
    group.addoption(
        "--include-local-only",
        action="store_true",
        default=False,
        help="Explicitly collect LOCAL_ONLY modules. Never enabled by hosted CI.",
    )


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    path = Path(collection_path)
    if not (path.is_file() and path.name.startswith("test_") and path.suffix == ".py"):
        return None
    try:
        path.resolve().relative_to(TESTS_ROOT.resolve())
    except ValueError:
        return None

    classification = classification_for(path)
    if classification == "HOSTED_SAFE":
        return None
    if classification == "LOCAL_ONLY":
        return not bool(config.getoption("--include-local-only"))
    # EXTERNAL_PROHIBITED and OBSOLETE/DEAD are never part of automatic/default runs.
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        classification = classification_for(Path(str(item.path)))
        marker_name = {
            "HOSTED_SAFE": "hosted_safe",
            "LOCAL_ONLY": "local_only",
            "EXTERNAL_PROHIBITED": "external_prohibited",
            "OBSOLETE/DEAD": "obsolete_dead",
        }[classification]
        item.add_marker(getattr(pytest.mark, marker_name))
