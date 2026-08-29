"""一致性检查与修复（M8，Addendum §42-43）。

检查每文档 SQLite chunk 数 vs FTS 两表数 vs Qdrant 点数；
repair：Qdrant 缺失 -> 从 SQLite 重嵌入补齐；Qdrant 孤儿 -> 删除。
"""

from __future__ import annotations

import logging
import sqlite3

from qdrant_client import models as qm

from app.core.config import Config
from app.indexing.pipeline import EmbedderAdapter
from app.retrieval.dense import point_id

logger = logging.getLogger(__name__)


def check_consistency(cfg: Config, conn: sqlite3.Connection) -> dict:
    """返回 per-document 计数与总体一致性结论。"""
    client = None
    from qdrant_client import QdrantClient

    client = QdrantClient(url=cfg.qdrant.url, timeout=30)
    report: dict = {"documents": [], "consistent": True}
    rows = conn.execute("SELECT id FROM documents").fetchall()
    for r in rows:
        doc_id = r["id"]
        n_chunks = conn.execute(
            "SELECT count(*) FROM chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]
        n_terms = conn.execute(
            "SELECT count(*) FROM chunks_fts_terms WHERE document_id = ?", (doc_id,)).fetchone()[0]
        n_trigram = conn.execute(
            "SELECT count(*) FROM chunks_fts_trigram WHERE document_id = ?", (doc_id,)).fetchone()[0]
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=doc_id))])
        n_qdrant = client.count(
            collection_name=cfg.qdrant.chunks_collection, count_filter=flt, exact=True).count
        ok = n_chunks == n_terms == n_trigram == n_qdrant
        report["consistent"] &= ok
        report["documents"].append({
            "document_id": doc_id, "chunks": n_chunks, "fts_terms": n_terms,
            "fts_trigram": n_trigram, "qdrant": n_qdrant, "ok": ok,
        })
    return report


def repair(cfg: Config, conn: sqlite3.Connection, embedder: EmbedderAdapter | None = None) -> dict:
    """修复 Qdrant 与 SQLite 的差异（FTS 由仓储层保证，这里主要处理向量索引）。"""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=cfg.qdrant.url, timeout=30)
    collection = cfg.qdrant.chunks_collection
    stats = {"reindexed_documents": 0, "deleted_orphans": 0}

    sqlite_docs = {r["id"] for r in conn.execute("SELECT id FROM documents").fetchall()}

    # Qdrant 全量 point id -> document_id
    qdrant_points: dict[str, str] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, limit=256, offset=offset, with_payload=True,
            with_vectors=False,
        )
        for p in points:
            doc_id = (p.payload or {}).get("document_id", "")
            qdrant_points[str(p.id)] = doc_id
        if offset is None:
            break

    # 1) 孤儿点（文档已不存在，或文档仍在但点不在 SQLite chunk 集内）
    sqlite_ids = {
        point_id(r["id"]): r["id"]
        for r in conn.execute("SELECT id FROM chunks").fetchall()
    }
    orphans = [pid for pid, doc in qdrant_points.items()
               if doc not in sqlite_docs or pid not in sqlite_ids]
    if orphans:
        client.delete(collection_name=collection,
                      points_selector=qm.PointIdsList(points=orphans))
        stats["deleted_orphans"] = len(orphans)

    # 2) 缺失/不一致文档：从 SQLite 重嵌入补齐
    for doc_id in sqlite_docs:
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=doc_id))])
        n_qdrant = client.count(collection_name=collection, count_filter=flt, exact=True).count
        n_chunks = conn.execute(
            "SELECT count(*) FROM chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]
        if n_qdrant == n_chunks:
            continue
        logger.warning("repair: %s qdrant=%d sqlite=%d -> 重建", doc_id, n_qdrant, n_chunks)
        rows = conn.execute(
            "SELECT c.id, c.embedding_text, c.section_id, c.content_type, c.evidence_level, "
            "d.domain, d.completed_at FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.document_id = ?", (doc_id,)).fetchall()
        vectors = embedder.embed_documents([r["embedding_text"] for r in rows]) if embedder else None
        if vectors is None:
            continue
        client.delete(collection_name=collection,
                      points_selector=qm.FilterSelector(filter=flt))
        points = [
            qm.PointStruct(
                id=point_id(r["id"]), vector={"dense": vec},
                payload={
                    "chunk_id": r["id"], "document_id": doc_id,
                    "section_id": r["section_id"].split(":", 1)[1] if r["section_id"].count(":") > 1 else r["section_id"],
                    "content_type": r["content_type"], "evidence_level": r["evidence_level"],
                    "domain": r["domain"], "completed_at": r["completed_at"],
                },
            )
            for r, vec in zip(rows, vectors)
        ]
        for i in range(0, len(points), 64):
            client.upsert(collection_name=collection, points=points[i:i + 64], wait=True)
        stats["reindexed_documents"] += 1

    return stats
