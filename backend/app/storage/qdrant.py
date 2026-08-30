"""Qdrant client 封装（M1-06）。

- Qdrant 是可重建的 Dense Index，不是正文 Source of Truth；
- collection 设计见 spec §9：kb_chunks_v1 / kb_sections_v1，dense 1024 COSINE；
- ensure_collections 幂等。
"""

from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.core.config import QdrantConfig
from app.core.errors import QdrantError

logger = logging.getLogger(__name__)


class QdrantStore:
    def __init__(self, cfg: QdrantConfig, embedding_dimension: int = 1024) -> None:
        self.cfg = cfg
        self.dimension = embedding_dimension
        self._client_invalid = False
        self._recoveries = 0
        self._last_error: str | None = None
        self._client = self._new_client()

    def _new_client(self) -> QdrantClient:
        return QdrantClient(url=self.cfg.url, timeout=10)

    @property
    def client(self) -> QdrantClient:
        """当前 client；若被标记失效则懒重建（供检索/health 自动恢复，无需重启 KE）。"""
        if self._client_invalid:
            self._recover()
        return self._client

    def _recover(self) -> None:
        self._client = self._new_client()
        self._client_invalid = False
        self._recoveries += 1
        logger.warning("Qdrant client recreated (recoveries=%s, last_error=%s)",
                       self._recoveries, self._last_error)

    def mark_invalid(self, exc: Exception) -> None:
        """连接类失败时标记 client 失效；下次访问经 @property 自动重建。"""
        self._client_invalid = True
        self._last_error = str(exc)

    def recover(self) -> None:
        """立即重建 client（供检索路径失败后原地重试）。"""
        self._recover()

    def health(self) -> dict:
        # 单次探活即返回，不做慢速 recover 重试（避免 qdrant down 时 health 超时）。
        # 真正的恢复由检索路径（dense.search 失败->重建重试）与 client @property 懒重建承担；
        # health 每次新建实例本就携带新 client，恢复后下次调用自动返回 ok。
        base = {"url": self.cfg.url, "recoveries": self._recoveries}
        try:
            self.client.get_collections()
            return {"status": "ok", **base}
        except Exception as exc:
            self.mark_invalid(exc)
            return {"status": "error", "error": str(exc), **base}

    def ensure_collections(self) -> None:
        """幂等创建 chunks / sections 两个 collection。"""
        vectors = {"dense": qm.VectorParams(size=self.dimension, distance=qm.Distance.COSINE)}
        try:
            existing = {c.name for c in self.client.get_collections().collections}
            for name in (self.cfg.chunks_collection, self.cfg.sections_collection):
                if name not in existing:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=vectors,
                    )
                    logger.info("created qdrant collection: %s", name)
        except Exception as exc:
            raise QdrantError(f"Qdrant collection 初始化失败: {exc}") from exc

    def collection_info(self, name: str) -> dict:
        try:
            info = self.client.get_collection(name)
            return {"points_count": info.points_count, "status": str(info.status)}
        except Exception as exc:
            raise QdrantError(f"获取 collection 信息失败: {name}", detail={"error": str(exc)}) from exc
