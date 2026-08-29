"""M10 API 测试（TestClient + 真实 dev catalog/Qdrant/worker）。"""

import pytest

from app.core.config import load_config


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    cfg = load_config()
    app = create_app(cfg)
    with TestClient(app) as c:
        # 等待 startup reconcile 完成（有变更时在后台线程索引）
        import time

        for _ in range(60):
            counts = c.get("/api/index/status").json()["counts"]
            if counts["documents"] >= 10:
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
    assert docs["total"] >= 10
    one = client.get("/api/documents/M04").json()
    assert one["id"] == "M04" and one["chunk_count"] > 50
    sections = client.get("/api/documents/M04/sections").json()
    assert len(sections["sections"]) >= 60
    assert client.get("/api/documents/NOPE").status_code == 404


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
    assert status["counts"]["documents"] >= 10
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
