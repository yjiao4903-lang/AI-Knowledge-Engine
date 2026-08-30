"""Dense Retrieval（M5，spec §16/§9 + Addendum §21-32）。

- SQLite 是 Canonical Catalog，Qdrant 是可重建的 Dense Index；
- 文档向量输入 = Chunk.embedding_text（不重建第二套模板）；
- 查询向量必须带 instruction（配置化）；
- Metadata Filter 在 Qdrant prefilter 阶段执行；
- 设备一律经 get_inference_device()，禁止裸 .cuda()。
"""

from __future__ import annotations

import logging
import time
import uuid

import json

from qdrant_client import models as qm

from app.core.config import Config
from app.core.errors import EmbeddingError, QdrantError
from app.inference.device import device_kind, get_inference_device
from app.inference.embedding_provider import TorchEmbeddingProvider
from app.storage.qdrant import QdrantStore

logger = logging.getLogger(__name__)

_NAMESPACE = uuid.NAMESPACE_OID


def point_id(chunk_id: str) -> str:
    """chunk_id -> 确定性 UUID（幂等 upsert）。"""
    return str(uuid.uuid5(_NAMESPACE, f"chunk:{chunk_id}"))


def section_point_id(document_id: str, section_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"section:{document_id}:{section_id}"))


class DenseRetriever:
    """Embedding + Qdrant 的统一入口（索引与检索）。"""

    def __init__(self, cfg: Config, *, device_override: str | None = None) -> None:
        self.cfg = cfg
        device, reason = get_inference_device(
            force_device=device_override or cfg.inference.force_device,
            preferred_device=cfg.inference.preferred_device,
            preferred_gpu_name=cfg.inference.preferred_gpu_name,
            fallback=cfg.embedding.fallback_device,
        )
        self.device = device
        self.device_kind = device_kind(device)
        self.device_reason = reason
        logger.info("DenseRetriever device=%s (%s)", device, reason)

        self.embedder = TorchEmbeddingProvider(
            cfg.embedding.local_path,
            device=device,
            dtype_gpu=cfg.embedding.dtype_gpu,
            max_length=cfg.embedding.max_tokens,
            query_instruction=cfg.embedding.query_instruction,
        )
        self.store = QdrantStore(cfg.qdrant, embedding_dimension=cfg.embedding.dimension)

    # ---- 索引 ----
    def ensure_collections(self) -> None:
        self.store.ensure_collections()

    def index_chunks(self, chunks: list, doc_meta: dict[str, dict], batch_size: int | None = None) -> dict:
        """chunks: Chunk 列表；doc_meta: {document_id: {domain, completed_at}}。"""
        batch = batch_size or (self.cfg.embedding.batch_size_gpu if self.device != "cpu"
                               else self.cfg.embedding.batch_size_cpu)
        texts = [c.embedding_text for c in chunks]
        t0 = time.perf_counter()
        vectors = self.embedder.embed_documents(texts, batch_size=batch)
        embed_ms = (time.perf_counter() - t0) * 1000

        points = []
        for c, vec in zip(chunks, vectors):
            meta = doc_meta.get(c.document_id, {})
            points.append(qm.PointStruct(
                id=point_id(c.chunk_id),
                vector={"dense": vec},
                payload={
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "section_id": c.section_id,
                    "content_type": c.content_type,
                    "evidence_level": c.evidence_level,
                    "domain": meta.get("domain", ""),
                    "completed_at": meta.get("completed_at", ""),
                },
            ))
        self._upsert(self.cfg.qdrant.chunks_collection, points)
        return {"chunks": len(points), "embed_ms": round(embed_ms, 1)}

    def index_sections(self, records: list[dict], batch_size: int | None = None) -> dict:
        """records: {section_id, document_id, heading, section_type, embedding_text}。"""
        batch = batch_size or (self.cfg.embedding.batch_size_gpu if self.device != "cpu" else 2)
        t0 = time.perf_counter()
        vectors = self.embedder.embed_documents([r["embedding_text"] for r in records], batch_size=batch)
        embed_ms = (time.perf_counter() - t0) * 1000
        points = [
            qm.PointStruct(
                id=section_point_id(r["document_id"], r["section_id"]),
                vector={"dense": vec},
                payload={
                    "section_id": r["section_id"],
                    "document_id": r["document_id"],
                    "heading": r["heading"],
                    "section_type": r["section_type"],
                },
            )
            for r, vec in zip(records, vectors)
        ]
        self._upsert(self.cfg.qdrant.sections_collection, points)
        return {"sections": len(points), "embed_ms": round(embed_ms, 1)}

    def _upsert(self, collection: str, points: list[qm.PointStruct]) -> None:
        try:
            for i in range(0, len(points), 64):
                self.store.client.upsert(collection_name=collection, points=points[i : i + 64], wait=True)
        except Exception as exc:
            self.store.mark_invalid(exc)
            # P0-2：Qdrant 连接失效 -> 重建 client 原地重试一次（自动恢复，无需重启 KE）
            self.store.recover()
            try:
                for i in range(0, len(points), 64):
                    self.store.client.upsert(collection_name=collection, points=points[i : i + 64], wait=True)
            except Exception as exc2:
                raise QdrantError(f"Qdrant upsert 失败: {collection}", detail={"error": str(exc2)}) from exc2

    def delete_document(self, document_id: str) -> None:
        """按 document_id 删除 chunks 与 sections 两 collection 的点（M8 复用）。"""
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))])
        for collection in (self.cfg.qdrant.chunks_collection, self.cfg.qdrant.sections_collection):
            try:
                self.store.client.delete(collection_name=collection, points_selector=qm.FilterSelector(filter=flt))
            except Exception as exc:
                self.store.mark_invalid(exc)
                self.store.recover()
                self.store.client.delete(collection_name=collection, points_selector=qm.FilterSelector(filter=flt))

    # ---- 检索 ----
    def search(
        self,
        query: str,
        k: int = 50,
        *,
        filters: dict | None = None,
        collection: str | None = None,
    ) -> tuple[list[dict], float]:
        """返回 (hits, embed_ms)。hit = payload + score。

        filters: {document_ids, domains, evidence_levels, content_types, date_from, date_to}
        """
        try:
            t0 = time.perf_counter()
            qvec = self.embedder.embed_query(query)
            embed_ms = (time.perf_counter() - t0) * 1000
        except Exception as exc:
            raise EmbeddingError(f"查询向量化失败: {exc}") from exc

        qfilter = build_qdrant_filter(filters)
        resolved_collection = collection or self.cfg.qdrant.chunks_collection
        try:
            resp = self.store.client.query_points(
                collection_name=resolved_collection,
                query=qvec,
                using="dense",
                limit=k,
                query_filter=qfilter,
                with_payload=True,
            )
        except Exception as exc:
            # P0-2：Qdrant 连接失效 -> 重建 client 原地重试一次（自动恢复，无需重启 KE）
            self.store.mark_invalid(exc)
            self.store.recover()
            try:
                resp = self.store.client.query_points(
                    collection_name=resolved_collection,
                    query=qvec,
                    using="dense",
                    limit=k,
                    query_filter=qfilter,
                    with_payload=True,
                )
            except Exception as exc2:
                raise QdrantError(f"Qdrant 检索失败: {exc2}", detail={"error": str(exc2)}) from exc2

        hits = [
            {"payload": dict(p.payload or {}), "score": float(p.score)}
            for p in resp.points
        ]
        return hits, round(embed_ms, 1)


def build_qdrant_filter(filters: dict | None) -> qm.Filter | None:
    """Metadata Filter -> Qdrant prefilter（M5-06）。"""
    if not filters:
        return None
    must: list = []
    multi = {
        "document_ids": "document_id",
        "domains": "domain",
        "content_types": "content_type",
    }
    for fkey, pkey in multi.items():
        values = filters.get(fkey)
        if values:
            must.append(qm.FieldCondition(key=pkey, match=qm.MatchAny(any=values)))
    levels = filters.get("evidence_levels")
    if levels:
        must.append(qm.FieldCondition(key="evidence_level", match=qm.MatchAny(any=levels)))
    date_from, date_to = filters.get("date_from"), filters.get("date_to")
    if date_from or date_to:
        must.append(qm.FieldCondition(
            key="completed_at",
            range=qm.DatetimeRange(gte=date_from, lte=date_to),
        ))
    return qm.Filter(must=must) if must else None


def build_section_records(doc, doc_id: str) -> list[dict]:
    """ParsedDocument -> section 向量化记录（spec §9.2）。"""
    records = []
    title = doc.metadata.get("title", doc.title)
    domain = doc.metadata.get("domain", "")
    for s in doc.sections:
        if s.ordinal == 0:
            continue  # 根节点（标题+元数据）不建 section 向量
        # summary：第一个有内容的 prose 块（截断 500 字）
        summary = ""
        for b in s.blocks:
            if b.block_type == "prose":
                summary = b.text[:500]
                break
        heading_path = " > ".join(s.heading_path)
        records.append({
            "section_id": s.section_id,
            "document_id": doc_id,
            "heading": s.heading,
            "section_type": s.section_type,
            "embedding_text": (
                f"Document: {title}\nDomain: {domain}\n"
                f"Section Path: {heading_path}\nHeading: {s.heading}\n\n{summary}"
            ),
            "evidence_level": s.evidence_level,
            "_db_section_id": f"{doc_id}:{s.section_id}",
        })
    return records
