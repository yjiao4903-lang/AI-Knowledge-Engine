"""M1-06 Qdrant client 集成测试（需要 Qdrant Docker 运行；不可达则跳过）。"""

import pytest

from app.storage.qdrant import QdrantStore


def _store_available(cfg) -> bool:
    try:
        QdrantStore(cfg.qdrant).client.get_collections()
        return True
    except Exception:
        return False


def test_qdrant_health_and_ensure_collections(tmp_config):
    if not _store_available(tmp_config):
        pytest.skip("Qdrant 不可达（docker compose up -d 未运行？）")

    store = QdrantStore(tmp_config.qdrant, embedding_dimension=1024)
    assert store.health()["status"] == "ok"

    # 幂等：连续两次创建不抛错
    store.ensure_collections()
    store.ensure_collections()

    info = store.collection_info(tmp_config.qdrant.chunks_collection)
    assert "points_count" in info and "status" in info
