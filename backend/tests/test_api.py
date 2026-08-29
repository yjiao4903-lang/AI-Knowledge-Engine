"""M10 API 测试（I0 解耦：tmp 语料 + tmp catalog + 独立 Qdrant collection）。

此前依赖 dev seed catalog（等待 documents>=10），config.yaml 切换全量归档后
会导致 startup reconcile 误索引全库。现在 fixture 自建 3 篇语料（M04/M07/M10
fixture 拷贝），完全不触碰真实 catalog 与知识源。
"""

import shutil
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SEED_DOCS = ["M04_sample.md", "M07_sample.md", "M10_sample.md"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient

    from app.core.config import load_config
    from app.main import create_app
    from app.storage.qdrant import QdrantStore

    root = tmp_path_factory.mktemp("api_test")
    kb = root / "kb"
    kb.mkdir()
    for name in SEED_DOCS:
        # 文件名须满足收录策略（终版报告命名，ADR-013 v2）；doc_id 由专题代号元数据决定
        shutil.copy(FIXTURES / name, kb / name.replace("_sample", "_测试_最终报告"))

    cfg = load_config()
    cfg.knowledge_base.roots = [str(kb)]
    cfg.sqlite.path = str(root / "catalog.db")
    cfg.qdrant.chunks_collection = "kb_chunks_apitest"
    cfg.qdrant.sections_collection = "kb_sections_apitest"
    cfg.indexing.periodic_reconcile_seconds = 0  # 测试期间禁用 watcher

    store = QdrantStore(cfg.qdrant)
    for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
        try:
            store.client.delete_collection(col)
        except Exception:
            pass

    app = create_app(cfg)
    with TestClient(app) as c:
        # 等待 startup reconcile 完成（3 篇 -> GPU 索引数十秒内）
        for _ in range(120):
            counts = c.get("/api/index/status").json()["counts"]
            if counts["documents"] >= len(SEED_DOCS):
                break
            time.sleep(1)
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] in ("ok", "degraded")
    assert body["sqlite"]["fts5"] is True


def test_search_endpoint(client):
    resp = client.post("/api/search", json={
        "query": "HBM4 的接口位宽是多少？",
        "options": {"mode": "hybrid", "rerank": True, "top_k": 5},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 5
    r0 = body["results"][0]
    assert {"rank", "chunk_id", "document_id", "title", "section_id", "heading_path",
            "content_type", "evidence_level", "snippet", "start_line", "end_line",
            "scores"} <= set(r0)
    assert r0["scores"]["reranker"] is not None
    assert "total_ms" in body["timing_ms"]


def test_search_modes_and_filters(client):
    dense = client.post("/api/search", json={
        "query": "液冷", "options": {"mode": "dense", "rerank": False, "top_k": 5}}).json()
    assert dense["results"] and dense["timing_ms"]["terms_ms"] == 0.0

    filtered = client.post("/api/search", json={
        "query": "液冷",
        "filters": {"document_ids": ["M07"]},
        "options": {"mode": "hybrid", "rerank": False, "top_k": 5}}).json()
    assert filtered["results"]
    assert all(r["document_id"] == "M07" for r in filtered["results"])


def test_documents_endpoints(client):
    docs = client.get("/api/documents").json()
    assert docs["total"] >= 3
    one = client.get("/api/documents/M04").json()
    assert one["id"] == "M04" and one["chunk_count"] > 50
    sections = client.get("/api/documents/M04/sections").json()
    assert len(sections["sections"]) >= 60
    assert client.get("/api/documents/NOPE").status_code == 404


def test_document_chunks_endpoint(client):
    """I0 新增：按文档列 chunks（替代前端 deterministic 枚举规避方案）。"""
    resp = client.get("/api/documents/M04/chunks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "M04"
    assert body["total"] == body["chunk_count"] > 50
    chunks = body["chunks"]
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))
    first = chunks[0]
    assert {"id", "document_id", "section_id", "ordinal", "content_type",
            "evidence_level", "start_line", "end_line", "plain_text"} <= set(first)
    assert all(c["document_id"] == "M04" for c in chunks)
    # 与 document 详情的 chunk_count 一致
    one = client.get("/api/documents/M04").json()
    assert body["total"] == one["chunk_count"]
    assert client.get("/api/documents/NOPE/chunks").status_code == 404


def test_chunk_endpoint(client):
    search_resp = client.post("/api/search", json={
        "query": "玻尔兹曼极限", "options": {"rerank": False, "top_k": 1}}).json()
    cid = search_resp["results"][0]["chunk_id"]
    chunk = client.get(f"/api/chunks/{cid}").json()
    assert chunk["id"] == cid and chunk["plain_text"]
    assert client.get("/api/chunks/NOPE:1").status_code == 404


def test_open_original_path_security(client):
    """Path Traversal 防护：catalog 外路径必须 403（spec §52）。"""
    from app.api.documents import _validate_in_roots
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _validate_in_roots("C:/Windows/notepad.exe", ["D:/AI-Knowledge-Engine/data/dev_kb"])
    assert exc.value.status_code == 403
    # 404：不存在的文档
    assert client.post("/api/documents/NOPE/open-original").status_code == 404


def test_index_status_and_jobs(client):
    status = client.get("/api/index/status").json()
    assert status["counts"]["documents"] >= 3
    assert status["consistent"] is True
    jobs = client.get("/api/index/jobs").json()
    assert "jobs" in jobs


def test_reindex_document_endpoint(client):
    resp = client.post("/api/index/reindex-document/M04")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "M04" and body["chunks"] > 50
    assert client.post("/api/index/reindex-document/NOPE").status_code == 404


def test_rebuild_requires_confirm(client):
    resp = client.post("/api/index/rebuild", json={"confirm": "no"})
    assert resp.status_code == 400


def test_evaluation_endpoints(client):
    latest = client.get("/api/evaluation/latest")
    assert latest.status_code == 200
    assert latest.json()["results"]["n_queries"] == 50
    run = client.post("/api/evaluation/run", json={"limit": 3, "rerank": False}).json()
    assert run["n"] == 3 and "ndcg10" in run


def test_settings_endpoint(client):
    body = client.get("/api/settings").json()
    assert body["retrieval"]["final_k"] == 10
    assert "query_instruction" in body["embedding"]
