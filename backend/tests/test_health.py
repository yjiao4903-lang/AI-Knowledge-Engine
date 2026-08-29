"""M1-07 health 聚合 + FastAPI /api/health。"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.migrations import init_schema
from app.storage.sqlite import connect


def test_collect_health(tmp_config):
    # 先初始化 sqlite，使 sqlite 检查为 ok
    conn = connect(tmp_config.sqlite.path)
    init_schema(conn)
    conn.close()

    from app.core.health import collect_health

    health = collect_health(tmp_config)
    assert health["status"] in ("ok", "degraded")  # qdrant 未启动时为 degraded
    assert health["sqlite"]["status"] == "ok"
    assert health["sqlite"]["fts5"] is True
    assert "qdrant" in health and "inference" in health


def test_health_endpoint(tmp_config):
    app = create_app(tmp_config)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert {"status", "sqlite", "qdrant", "embedding", "reranker", "inference"} <= set(body.keys())
