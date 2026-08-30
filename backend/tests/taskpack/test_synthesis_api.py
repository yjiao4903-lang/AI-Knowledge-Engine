"""TaskPack API 测试（V3.0 方案 §34-§36）。

用 create_app + 临时 taskpack root + 临时 catalog，覆盖：
- POST /api/synthesis/tasks 立即返回 READY
- GET   /api/synthesis/tasks （触发 scan，含 completed+DONE 任务）
- GET   /api/synthesis/tasks/{id}
- POST  /api/synthesis/tasks/{id}/rescan
- POST  /api/synthesis/tasks/{id}/archive
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.taskpack.manifest import sha256_file

SEED_QUERY = "HBM4 接口位宽是多少？"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient

    from app.core.config import Config
    from app.main import create_app
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    root = tmp_path_factory.mktemp("tp_api")
    cfg = Config()
    cfg.paths.data_dir = str(root / "data")
    cfg.paths.log_dir = str(root / "logs")
    cfg.sqlite.path = str(root / "catalog.db")
    cfg.taskpack.root_dir = str(root / "taskpacks")
    cfg.indexing.periodic_reconcile_seconds = 0
    cfg.indexing.startup_scan = False  # 避免 startup reconcile 触碰真实知识库根

    # 种入 M04 两个 chunk 供 grounding
    conn = connect(cfg.sqlite.path, check_same_thread=False)
    init_schema(conn)
    from tests.synthesis.helpers import seed_chunk, seed_doc

    seed_doc(conn, "M04")
    seed_chunk(conn, "M04:ch1:0001", "HBM4 的接口位宽相比 HBM3E 显著提高。" * 4, doc_id="M04")
    seed_chunk(conn, "M04:ch1:0002", "更宽接口进一步提高了先进封装工艺的系统价值量。" * 4, doc_id="M04")
    conn.commit()  # helpers 的 INSERT 未提交；close 前显式提交，供后续独立连接读取
    conn.close()

    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def taskpack_root(client, tmp_path_factory):
    from app.core.config import Config

    cfg = Config()
    # 定位 create_app 注入的 taskpack root：经由 app.state
    return Path(client.app.state.cfg.taskpack.root_dir)


def _evidence():
    return [{
        "source_type": "report",
        "document_id": "M04",
        "chunk_id": "M04:ch1:0001",
    }]


def _valid_result(pack: Path, chunk_id: str = "M04:ch1:0001") -> dict:
    return {
        "schema_version": "1.0",
        "task_id": pack.name,
        "task_type": "summary",
        "query": SEED_QUERY,
        "summary": "test",
        "claims": [{
            "id": "claim_001",
            "text": "HBM4 的接口位宽相比 HBM3E 显著提高。",
            "epistemic_state": "supported",
            "evidence_refs": [chunk_id],
        }],
        "tensions": [], "uncertainties": [], "open_questions": [],
        "additional_evidence_needed": [],
        "worker": {"tool": "trae", "model": "test-model"},
        "generated_at": "2026-08-30T10:00:00+08:00",
    }


def _valid_run_meta(pack: Path) -> dict:
    return {
        "worker_tool": "trae", "model": "test-model",
        "prompt_version": "taskpack-synthesis-v1",
        "prompt_sha256": sha256_file(pack / "AGENT_INSTRUCTION.md"),
        "task_manifest_sha256": sha256_file(pack / "manifest.json"),
    }


def _complete_task(taskpack_root: Path, pack: Path) -> None:
    """outbox -> completed/ 并写 result 三件套 + DONE。"""
    completed = taskpack_root / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    dst = completed / pack.name
    shutil.move(str(pack), str(dst))
    (dst / "result").mkdir(parents=True, exist_ok=True)
    (dst / "result" / "result.json").write_text(
        json.dumps(_valid_result(dst), ensure_ascii=False), encoding="utf-8")
    (dst / "result" / "run_meta.json").write_text(
        json.dumps(_valid_run_meta(dst), ensure_ascii=False), encoding="utf-8")
    (dst / "result" / "DONE").write_text("", encoding="utf-8")


def test_create_task_returns_ready_immediately(client, taskpack_root):
    resp = client.post("/api/synthesis/tasks", json={
        "task_type": "summary",
        "query": SEED_QUERY,
        "evidence_refs": _evidence(),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "READY"
    assert body["task_id"]
    task_path = Path(body["task_path"])
    assert task_path.parts[-3:] == ("taskpacks", "outbox", body["task_id"])
    assert (task_path / "manifest.json").exists()


def test_create_task_rejects_empty_evidence(client):
    resp = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": [],
    })
    assert resp.status_code == 400


def test_create_task_rejects_unknown_chunk(client):
    resp = client.post("/api/synthesis/tasks", json={
        "task_type": "summary",
        "query": SEED_QUERY,
        "evidence_refs": [{"source_type": "report", "document_id": "M04",
                          "chunk_id": "M04:ch1:9", "content_hash": "a" * 64}],
    })
    assert resp.status_code == 404


def test_list_and_get_task(client, taskpack_root):
    created = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": _evidence()}).json()
    task_id = created["task_id"]

    # 完成任务 -> GET list 触发 scan -> COMPLETED
    _complete_task(taskpack_root, Path(created["task_path"]))
    lst = client.get("/api/synthesis/tasks").json()
    assert lst["count"] >= 1
    row = next(t for t in lst["tasks"] if t["task_id"] == task_id)
    assert row["status"] == "COMPLETED"
    assert row["query"] == SEED_QUERY

    detail = client.get(f"/api/synthesis/tasks/{task_id}").json()
    assert detail["status"] == "COMPLETED"
    assert "result" in detail and detail["result"]["worker"]["tool"] == "trae"


def test_get_missing_task_404(client):
    assert client.get("/api/synthesis/tasks/NOPE").status_code == 404


def test_rescan_marks_invalid_on_bad_result(client, taskpack_root):
    created = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": _evidence()}).json()
    task_id = created["task_id"]
    pack = Path(created["task_path"])

    _complete_task(taskpack_root, pack)
    # 篡改 result 引用未提供证据 -> rescan 判 INVALID
    completed = taskpack_root / "completed" / task_id
    res = json.loads((completed / "result" / "result.json").read_text(encoding="utf-8"))
    res["claims"][0]["evidence_refs"] = ["M05:ch1:9999"]
    (completed / "result" / "result.json").write_text(json.dumps(res), encoding="utf-8")

    resp = client.post(f"/api/synthesis/tasks/{task_id}/rescan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is False
    assert body["status"] == "INVALID_RESULT"


def test_archive_task(client, taskpack_root):
    created = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": _evidence()}).json()
    task_id = created["task_id"]
    resp = client.post(f"/api/synthesis/tasks/{task_id}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ARCHIVED"
    assert (taskpack_root / "archive" / task_id).is_dir()
    assert (taskpack_root / "outbox" / task_id).exists() is False


def test_archive_missing_404(client):
    assert client.post("/api/synthesis/tasks/NOPE/archive").status_code == 404


def test_open_folder_succeeds_for_outbox_task(client, taskpack_root):
    created = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": _evidence()}).json()
    resp = client.post(f"/api/synthesis/tasks/{created['task_id']}/open-folder")
    assert resp.status_code == 200
    body = resp.json()
    assert body["opened"] is True
    assert f"taskpacks{chr(92)}outbox" in body["path"] or "/taskpacks/outbox/" in body["path"]


def test_open_folder_missing_404(client):
    assert client.post("/api/synthesis/tasks/NOPE/open-folder").status_code == 404


def test_task_prompt_returns_instruction(client, taskpack_root):
    created = client.post("/api/synthesis/tasks", json={
        "task_type": "summary", "query": SEED_QUERY, "evidence_refs": _evidence()}).json()
    task_id = created["task_id"]
    resp = client.get(f"/api/synthesis/tasks/{task_id}/prompt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"] == "AGENT_INSTRUCTION.md"
    assert body["content"]
    assert len(body["sha256"]) == 64
    pack = Path(created["task_path"])
    assert body["content"] == (pack / "AGENT_INSTRUCTION.md").read_text(encoding="utf-8")


def test_task_prompt_missing_404(client):
    assert client.get("/api/synthesis/tasks/NOPE/prompt").status_code == 404