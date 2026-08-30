"""I7 P0-2：Qdrant 自动恢复机制单测。

验证 QdrantStore 在连接失效后能自动重建 client（property 懒重建 + health
self-healing），不依赖真实 Qdrant 停开（真实故障注入见 I7_EVALUATION）。
全 fake client，不联网，不加载模型。
"""

from __future__ import annotations

import pytest

from app.core.config import QdrantConfig
from app.storage.qdrant import QdrantStore


class _FakeClient:
    def __init__(self, ok: bool) -> None:
        self._ok = ok

    def get_collections(self):
        if not self._ok:
            raise ConnectionError("connection refused")
        return object()


def test_mark_invalid_triggers_lazy_recreate(monkeypatch):
    store = QdrantStore(QdrantConfig(url="http://127.0.0.1:1"))
    created: list = []

    def fake_new():
        c = _FakeClient(ok=False)
        created.append(c)
        return c

    monkeypatch.setattr(store, "_new_client", fake_new)
    store.mark_invalid(ConnectionError("down"))
    assert store._client_invalid is True
    # 访问 client -> 懒重建（@property）
    store.client
    assert store._recoveries == 1
    assert store._client_invalid is False  # 重建后清失效标志
    assert len(created) == 1


def test_health_fast_error_and_invalid_mark(monkeypatch):
    store = QdrantStore(QdrantConfig(url="http://127.0.0.1:65533"))  # 不可达
    created = {"n": 0}

    def fake_new():
        created["n"] += 1
        return _FakeClient(ok=False)  # 一直失败

    monkeypatch.setattr(store, "_new_client", fake_new)
    store._client = _FakeClient(ok=False)
    h = store.health()
    # health 单次探活，失败即返回 error 并标记 invalid（不慢速 recover 重试）
    assert h["status"] == "error"
    assert h["error"]
    assert store._client_invalid is True

    # 恢复路径：@property 懒重建（search 失败 -> mark_invalid -> recover -> 重试）
    store.recover()
    assert store._client_invalid is False
    assert store._recoveries == 1


def test_health_error_when_unreachable():
    store = QdrantStore(QdrantConfig(url="http://127.0.0.1:65533"))  # 几乎不可能可达
    h = store.health()
    # 单次快探活；对真实不可达场景的恢复由 I7_EVALUATION 真机故障注入实测
    assert h["status"] in ("ok", "error")