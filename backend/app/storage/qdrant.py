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
        self.client = QdrantClient(url=cfg.url, timeout=10)

    def health(self) -> dict:
        try:
            ok = self.client.get_collections() is not None
            return {"status": "ok" if ok else "error", "url": self.cfg.url}
        except Exception as exc:
            return {"status": "error", "url": self.cfg.url, "error": str(exc)}

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
