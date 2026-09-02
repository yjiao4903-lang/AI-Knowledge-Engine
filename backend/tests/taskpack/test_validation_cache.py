"""P1 TaskPack Validation Cache deterministic contracts."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from app.synthesis.schemas import EvidenceRef
from app.taskpack.manifest import sha256_file
from app.taskpack.validation_cache import (
    VALIDATION_CACHE_FILE,
    VALIDATION_VERSION,
    CachingTaskPackImporter,
)


def _valid_result(pack: Path) -> dict:
    return {
        "schema_version": "1.0",
        "task_id": pack.name,
        "task_type": "summary",
        "query": "HBM4 接口",
        "summary": "test",
        "claims": [
            {
                "id": "claim_001",
                "text": "HBM4 的接口位宽相比 HBM3E 显著提高。",
                "epistemic_state": "supported",
                "evidence_refs": ["M04:ch1:0001"],
            }
        ],
        "tensions": [],
        "uncertainties": [],
        "open_questions": [],
        "additional_evidence_needed": [],
        "worker": {"tool": "trae", "model": "test-model"},
        "generated_at": "2026-09-02T10:00:00+08:00",
    }


def _valid_run_meta(pack: Path) -> dict:
    return {
        "worker_tool": "trae",
        "model": "test-model",
        "prompt_version": "taskpack-synthesis-v1",
        "prompt_sha256": sha256_file(pack / "AGENT_INSTRUCTION.md"),
        "task_manifest_sha256": sha256_file(pack / "manifest.json"),
        "started_at": "2026-09-02T09:55:00+08:00",
        "completed_at": "2026-09-02T10:00:00+08:00",
    }


def _create_completed(env) -> Path:
    ref = EvidenceRef(
        source_type="report",
        document_id="M04",
        chunk_id="M04:ch1:0001",
        content_hash=env["hashes"][0],
    )
    created = env["builder"].create_task(
        task_type="summary",
        query="HBM4 接口",
        evidence_refs=[ref],
        now=datetime(2026, 9, 2, 4, 0, 0),
    )
    completed_root = env["root"] / "completed"
    completed_root.mkdir(parents=True, exist_ok=True)
    pack = completed_root / created.task_id
    shutil.move(str(created.task_path), str(pack))
    (pack / "result").mkdir(parents=True, exist_ok=True)
    (pack / "result" / "result.json").write_text(
        json.dumps(_valid_result(pack), ensure_ascii=False), encoding="utf-8"
    )
    (pack / "result" / "run_meta.json").write_text(
        json.dumps(_valid_run_meta(pack), ensure_ascii=False), encoding="utf-8"
    )
    (pack / "result" / "DONE").write_text("", encoding="utf-8")
    return pack


def _importer(env) -> CachingTaskPackImporter:
    return CachingTaskPackImporter(env["cfg"], env["conn"], None)


def test_first_validation_writes_result_hash_version_and_timestamp(tk_env):
    pack = _create_completed(tk_env)
    importer = _importer(tk_env)

    reports = importer.scan()
    assert len(reports) == 1 and reports[0].passed is True

    cache = json.loads((pack / VALIDATION_CACHE_FILE).read_text(encoding="utf-8"))
    assert cache["validation_version"] == VALIDATION_VERSION
    assert cache["result_hash"] == sha256_file(pack / "result" / "result.json")
    assert cache["validated_at"]
    assert cache["report"]["passed"] is True


def test_unchanged_result_reuses_cache_without_static_gate_rerun(tk_env, monkeypatch):
    _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True

    def should_not_run(_pack):
        raise AssertionError("static Gate should be served from cache")

    monkeypatch.setattr(importer, "_gate_manifest", should_not_run)
    reports = importer.scan()
    assert len(reports) == 1 and reports[0].passed is True


def test_changed_result_hash_forces_full_validation(tk_env, monkeypatch):
    pack = _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True

    result_path = pack / "result" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["summary"] = "changed but still valid"
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    original = importer._gate_manifest
    calls = {"count": 0}

    def counted(target):
        calls["count"] += 1
        return original(target)

    monkeypatch.setattr(importer, "_gate_manifest", counted)
    reports = importer.scan()
    assert reports[0].passed is True
    assert calls["count"] == 1


def test_validation_version_change_forces_full_validation(tk_env, monkeypatch):
    _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True

    import app.taskpack.validation_cache as cache_module

    monkeypatch.setattr(cache_module, "VALIDATION_VERSION", "taskpack-gates-v2")
    original = importer._gate_manifest
    calls = {"count": 0}

    def counted(target):
        calls["count"] += 1
        return original(target)

    monkeypatch.setattr(importer, "_gate_manifest", counted)
    reports = importer.scan()
    assert reports[0].passed is True
    assert calls["count"] == 1


def test_explicit_rescan_bypasses_matching_cache(tk_env, monkeypatch):
    pack = _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True

    original = importer._gate_manifest
    calls = {"count": 0}

    def counted(target):
        calls["count"] += 1
        return original(target)

    monkeypatch.setattr(importer, "_gate_manifest", counted)
    report = importer.rescan_task(pack.name)
    assert report is not None and report.passed is True
    assert calls["count"] == 1


def test_cache_hit_still_rechecks_catalog_staleness(tk_env):
    pack = _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True

    from tests.synthesis.helpers import seed_chunk

    tk_env["conn"].execute("DELETE FROM chunks WHERE id='M04:ch1:0001'")
    tk_env["conn"].commit()
    seed_chunk(tk_env["conn"], "M04:ch1:0001", "catalog changed", doc_id="M04")

    reports = importer.scan()
    assert len(reports) == 1
    assert reports[0].passed is False
    assert reports[0].stale is True
    assert (pack / "result" / "INVALID").exists()


def test_corrupt_cache_falls_back_to_full_validation(tk_env, monkeypatch):
    pack = _create_completed(tk_env)
    importer = _importer(tk_env)
    assert importer.scan()[0].passed is True
    (pack / VALIDATION_CACHE_FILE).write_text("{broken", encoding="utf-8")

    original = importer._gate_manifest
    calls = {"count": 0}

    def counted(target):
        calls["count"] += 1
        return original(target)

    monkeypatch.setattr(importer, "_gate_manifest", counted)
    reports = importer.scan()
    assert reports[0].passed is True
    assert calls["count"] == 1
