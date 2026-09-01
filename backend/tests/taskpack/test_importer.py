"""Importer / Watcher 测试（V3.0 方案 §40-§48/§69 Task 5）。

覆盖：状态机判定（目录+marker）、八步 Gate（§46）、stale（§48）、rescan/archive/list。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.taskpack.importer import (
    ARCHIVED,
    COMPLETED,
    FAILED,
    IMPORTED,
    INVALID_RESULT,
    READY,
    TaskPackImporter,
)
from app.taskpack.manifest import sha256_file


def _make_importer(env) -> TaskPackImporter:
    return TaskPackImporter(env["cfg"], env["conn"], None)


def _valid_result(pack: Path, chunk_id: str = "M04:ch1:0001") -> dict:
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
                "evidence_refs": [chunk_id],
            }
        ],
        "tensions": [],
        "uncertainties": [],
        "open_questions": [],
        "additional_evidence_needed": [],
        "worker": {"tool": "trae", "model": "test-model"},
        "generated_at": "2026-08-30T10:00:00+08:00",
    }


def _valid_run_meta(pack: Path) -> dict:
    return {
        "worker_tool": "trae",
        "model": "test-model",
        "prompt_version": "taskpack-synthesis-v1",
        "prompt_sha256": sha256_file(pack / "AGENT_INSTRUCTION.md"),
        "task_manifest_sha256": sha256_file(pack / "manifest.json"),
        "started_at": "2026-08-30T09:55:00+08:00",
        "completed_at": "2026-08-30T10:00:00+08:00",
    }


def _move_to_completed(env, pack: Path) -> Path:
    """模拟 Worker 完成任务：把包从 outbox 移到 completed/ 并写 result 三件套。"""
    from app.taskpack.builder import TaskPackBuilder

    builder = TaskPackBuilder(env["cfg"], env["conn"], None)
    completed = env["root"] / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    dst = completed / pack.name
    shutil.move(str(pack), str(dst))
    (dst / "result").mkdir(parents=True, exist_ok=True)
    res = _valid_result(dst)
    meta = _valid_run_meta(dst)
    (dst / "result" / "result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    (dst / "result" / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (dst / "result" / "DONE").write_text("", encoding="utf-8")
    return dst


@pytest.fixture()
def tk_imp(tk_env) -> TaskPackImporter:
    return _make_importer(tk_env)


def _create(env, *, task_type="summary"):
    from datetime import datetime

    from app.synthesis.schemas import EvidenceRef

    refs = [
        EvidenceRef(source_type="report", document_id="M04",
                    chunk_id="M04:ch1:0001", content_hash=env["hashes"][0]),
    ]
    created = env["builder"].create_task(
        task_type=task_type,
        query="HBM4 接口",
        evidence_refs=refs,
        now=datetime(2026, 8, 30, 4, 0, 0),
    )
    return created


def test_status_ready_after_create(tk_env, tk_imp):
    created = _create(tk_env)
    assert tk_imp.status_of(created.task_path) == READY


def test_scan_imports_completed_with_done(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    reports = tk_imp.scan()
    assert len(reports) == 1
    rep = reports[0]
    assert rep.passed is True
    assert all(g.passed for g in rep.gates)
    assert rep.citation_coverage == 1.0
    # 状态机：completed + DONE + 无 INVALID -> COMPLETED
    assert tk_imp.status_of(completed) == COMPLETED


def test_import_accepts_utf8_bom_in_external_json(tk_env, tk_imp):
    """External Windows tools may emit BOM-prefixed result and run metadata JSON."""
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    for name in ("result.json", "run_meta.json"):
        path = completed / "result" / name
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

    rep = tk_imp.import_task(completed)
    assert rep.passed is True
    assert all(g.passed for g in rep.gates)


def test_scan_skips_without_done(tk_env, tk_imp):
    """§44：无 DONE 不导入（避免半写 JSON）。"""
    created = _create(tk_env)
    completed = tk_env["root"] / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    dst = completed / created.task_id
    shutil.move(str(created.task_path), str(dst))
    # 不写 DONE，只写 result.json
    (dst / "result").mkdir(parents=True, exist_ok=True)
    (dst / "result" / "result.json").write_text("{}", encoding="utf-8")
    reports = tk_imp.scan()
    assert reports == []
    # completed 无 DONE -> 视为结果未就绪
    assert tk_imp.status_of(dst) != COMPLETED


def test_prompt_sha_mismatch_invalidates(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # 篡改 run_meta.prompt_sha256 使其与 AGENT_INSTRUCTION.md 失配（输入文件保持原样，
    # 避免触发 manifest gate——本测试专门检验第 4 步 prompt_sha gate）
    meta = json.loads((completed / "result" / "run_meta.json").read_text(encoding="utf-8"))
    meta["prompt_sha256"] = "f" * 64
    (completed / "result" / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    rep = tk_imp.import_task(completed)
    assert rep.passed is False
    assert any(g.name == "prompt_sha" and not g.passed for g in rep.gates)
    assert tk_imp.status_of(completed) == INVALID_RESULT


def test_evidence_membership_invalidates(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # result 引用未提供的 chunk_id
    res = json.loads((completed / "result" / "result.json").read_text(encoding="utf-8"))
    res["claims"][0]["evidence_refs"] = ["M05:ch1:9999"]
    (completed / "result" / "result.json").write_text(json.dumps(res), encoding="utf-8")
    rep = tk_imp.import_task(completed)
    assert rep.passed is False
    assert any(g.name == "evidence_membership" and not g.passed for g in rep.gates)
    assert tk_imp.status_of(completed) == INVALID_RESULT


def test_low_coverage_invalidates(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # 一个 supported claim 无 evidence_refs -> coverage 0
    res = json.loads((completed / "result" / "result.json").read_text(encoding="utf-8"))
    res["claims"][0]["evidence_refs"] = []
    (completed / "result" / "result.json").write_text(json.dumps(res), encoding="utf-8")
    rep = tk_imp.import_task(completed)
    assert rep.passed is False
    assert any(g.name == "citation_coverage" and not g.passed for g in rep.gates)
    assert tk_imp.status_of(completed) == INVALID_RESULT


def test_stale_evidence_marked_but_not_rewritten(tk_env, tk_imp):
    """§48：stale 标 INVALID + stale=True；不自动改 TaskPack evidence."""
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # 改 catalog 中 chunk 的正文，使 content_hash 失配
    from tests.synthesis.helpers import seed_chunk

    tk_env["conn"].execute("DELETE FROM chunks WHERE id='M04:ch1:0001'")
    tk_env["conn"].commit()
    seed_chunk(tk_env["conn"], "M04:ch1:0001", "HBM4 接口位宽已改写。", doc_id="M04")
    rep = tk_imp.import_task(completed)
    assert rep.passed is False
    assert rep.stale is True
    assert any(g.name == "stale" and not g.passed for g in rep.gates)
    # evidence.jsonl 内容不被改写
    ev_text = (completed / "evidence.jsonl").read_text(encoding="utf-8")
    assert "M04:ch1:0001" in ev_text
    assert tk_imp.status_of(completed) == INVALID_RESULT


def test_rescan_task_refreshes_status(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # 篡改 result 使其失效，rescan 后应判定 INVALID
    res = json.loads((completed / "result" / "result.json").read_text(encoding="utf-8"))
    res["claims"][0]["evidence_refs"] = []
    (completed / "result" / "result.json").write_text(json.dumps(res), encoding="utf-8")
    rep = tk_imp.rescan_task(created.task_id)
    assert rep is not None and rep.passed is False
    assert tk_imp.status_of(completed) == INVALID_RESULT


def test_archive_moves_to_archive(tk_env, tk_imp):
    created = _create(tk_env)
    target = tk_imp.archive_task(created.task_id)
    assert target.name == created.task_id
    assert tk_imp.status_of(target) == ARCHIVED
    assert tk_imp.locate(created.task_id) == target


def test_archive_collision_is_rejected_without_moving_source(tk_env, tk_imp):
    created = tk_env["builder"].create_task(
        task_type="summary", query="archive collision", evidence_refs=tk_env["refs"]
    )
    target = tk_env["root"] / "archive" / created.task_id
    target.mkdir(parents=True)
    (target / "sentinel").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="归档目标已存在"):
        tk_imp.archive_task(created.task_id)
    assert created.task_path.is_dir()
    assert (target / "sentinel").read_text(encoding="utf-8") == "existing"


def test_list_tasks_includes_all_states(tk_env, tk_imp):
    a = _create(tk_env, task_type="summary")
    b = _create(tk_env, task_type="summary")
    _move_to_completed(tk_env, b.task_path)
    tasks = {t.task_id: t for t in tk_imp.list_tasks()}
    assert a.task_id in tasks and b.task_id in tasks
    assert tasks[a.task_id].status == READY
    assert tasks[b.task_id].status == COMPLETED


def test_imported_marker_after_viewer(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    # 用户打开并接受到 Viewer -> IMPORTED
    (completed / "result" / "IMPORTED").write_text("", encoding="utf-8")
    assert tk_imp.status_of(completed) == IMPORTED


def test_import_failure_marks_file(tk_env, tk_imp):
    created = _create(tk_env)
    completed = _move_to_completed(tk_env, created.task_path)
    (completed / "result" / "result.json").write_text("{not json", encoding="utf-8")
    rep = tk_imp.import_task(completed)
    assert rep.passed is False
    assert (completed / "result" / "INVALID").exists()
    invalid = json.loads((completed / "result" / "INVALID").read_text(encoding="utf-8"))
    assert invalid["passed"] is False
