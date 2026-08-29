"""Cognition 只读索引管线（I6，主计划 §48-50）。

复用现有 parser/chunker/embedder，不改技术栈；写独立 SQLite catalog
（catalog_cognition.db）与独立 Qdrant collection（kb_cognition_chunks_v1），
与报告 collection 物理隔离、禁止混用。

READ ONLY 硬约束：本模块只读消费 cognition Markdown，绝不写认知
（含 Proposal/Apply）；索引由 KE 侧单独触发（startup/periodic/CLI）。
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from qdrant_client import models as qm

from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import SCHEMA_VERSION, Config
from app.core.errors import SourceFileError
from app.indexing.scanner import FileState, sha256_file
from app.parser.markdown_parser import parse_markdown
from app.retrieval.dense import point_id
from app.storage.migrations import init_schema, set_meta
from app.storage.repositories.knowledge import (
    ChunkRepository,
    DocumentRepository,
    SectionRepository,
)

logger = logging.getLogger(__name__)


def cognition_doc_id(cfg: Config, path: str | Path) -> str:
    """doc_id = '{prefix}:{相对路径(去扩展名)}'，如 cog:03_问题池/变压器瓶颈…。

    相对路径保证 cognition collection 内唯一且可追溯源文件。
    """
    root = Path(cfg.cognition.root)
    rel = Path(path).relative_to(root).with_suffix("")
    return f"{cfg.cognition.docid_prefix}:{rel.as_posix()}"


def ensure_cognition_collection(cfg: Config) -> None:
    """幂等创建 cognition collection（与报告 chunks/sections 完全独立）。"""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=cfg.qdrant.url, timeout=10)
    existing = {c.name for c in client.get_collections().collections}
    if cfg.cognition.chunks_collection not in existing:
        client.create_collection(
            collection_name=cfg.cognition.chunks_collection,
            vectors_config={
                "dense": qm.VectorParams(
                    size=cfg.embedding.dimension, distance=qm.Distance.COSINE)
            },
        )
        logger.info("created qdrant collection: %s", cfg.cognition.chunks_collection)


class CognitionPipeline:
    """Cognition 只读索引管线（独立 catalog + 独立 collection）。"""

    def __init__(self, cfg: Config, conn: sqlite3.Connection, embedder) -> None:
        self.cfg = cfg
        self.conn = conn
        self.chunker = SemanticChunker(cfg.chunking)
        self.embedder = embedder
        init_schema(conn)
        ensure_cognition_collection(cfg)

    def index_file(self, path: str | Path, *, state: FileState | None = None) -> dict:
        """NEW/MODIFIED：staging 全部成功后才原子替换（语义同报告 pipeline）。"""
        path = Path(path)
        t0 = time.perf_counter()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceFileError(f"读取失败: {path}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise SourceFileError(f"编码错误: {path}: {exc}") from exc

        doc_id = cognition_doc_id(self.cfg, path)
        parsed = parse_markdown(text)
        chunks = self.chunker.chunk_document(parsed, doc_id)
        if not chunks:
            raise SourceFileError(f"分块结果为空: {path}")

        st = path.stat()
        sha = state.sha256 if state and state.sha256 else sha256_file(path)
        doc_row = {
            "id": doc_id,
            "report_code": doc_id,
            "title": parsed.metadata.get("title", parsed.title),
            "domain": parsed.metadata.get("domain", ""),
            "research_method": parsed.metadata.get("research_method", ""),
            "completed_at": parsed.metadata.get("completed_at", ""),
            "status": parsed.metadata.get("status", ""),
            "source_path": str(path),
            "file_name": path.name,
            "file_size": st.st_size,
            "file_mtime_ns": st.st_mtime_ns,
            "sha256": sha,
            "parser_version": "0.1.0",
            "chunker_version": self.chunker.chunker_version,
            "schema_version": SCHEMA_VERSION,
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        section_rows = [
            {
                "id": f"{doc_id}:{s.section_id}", "document_id": doc_id,
                "parent_section_id": f"{doc_id}:{s.parent_id}" if s.parent_id else None,
                "level": s.level, "heading": s.heading,
                "heading_path": " > ".join(s.heading_path), "section_type": s.section_type,
                "ordinal": s.ordinal, "start_line": s.start_line, "end_line": s.end_line,
            }
            for s in parsed.sections
        ]
        chunk_rows = []
        for c in chunks:
            d = c.to_db_dict()
            d["section_id"] = f"{doc_id}:{c.section_id}"
            chunk_rows.append(d)

        batch = self.cfg.embedding.batch_size_gpu if self.embedder.device_kind != "cpu" \
            else self.cfg.embedding.batch_size_cpu
        vectors = self.embedder.embed_documents(
            [c.embedding_text for c in chunks], batch_size=batch)
        points = [
            qm.PointStruct(
                id=point_id(c.chunk_id),
                vector={"dense": vec},
                payload={
                    "chunk_id": c.chunk_id, "document_id": doc_id,
                    "section_id": c.section_id, "content_type": c.content_type,
                    "evidence_level": c.evidence_level, "domain": doc_row["domain"],
                    "completed_at": doc_row["completed_at"],
                },
            )
            for c, vec in zip(chunks, vectors)
        ]

        with self.conn:
            DocumentRepository(self.conn).upsert(doc_row)
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_terms WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_trigram WHERE document_id = ?", (doc_id,))
            SectionRepository(self.conn).replace_for_document(section_rows)
            ChunkRepository(self.conn).upsert_batch(chunk_rows)

        self._qdrant_replace(doc_id, points)

        ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("cognition indexed %s: chunks=%d points=%d in %dms",
                    doc_id, len(chunks), len(points), ms)
        return {"document_id": doc_id, "chunks": len(chunks),
                "points": len(points), "ms": ms}

    def _qdrant_replace(self, doc_id: str, points: list[qm.PointStruct]) -> None:
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=doc_id))])
        client = self.qdrant_client()
        col = self.cfg.cognition.chunks_collection
        client.delete(collection_name=col, points_selector=qm.FilterSelector(filter=flt))
        for i in range(0, len(points), 64):
            client.upsert(collection_name=col, points=points[i:i + 64], wait=True)

    def qdrant_client(self):
        if getattr(self, "_client", None) is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self.cfg.qdrant.url, timeout=30)
        return self._client

    def remove_document(self, doc_id: str, source_path: str) -> None:
        """DELETED：tombstone + 级联清理（语义同报告 pipeline）。"""
        row = self.conn.execute(
            "SELECT sha256 FROM documents WHERE id = ?", (doc_id,)).fetchone()
        with self.conn:
            if row:
                self.conn.execute(
                    "INSERT OR REPLACE INTO document_tombstones "
                    "(source_path, document_id, last_sha256, deleted_at) VALUES (?,?,?,?)",
                    (source_path, doc_id, row["sha256"], time.strftime("%Y-%m-%dT%H:%M:%S")),
                )
            DocumentRepository(self.conn).delete(doc_id)
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=doc_id))])
        self.qdrant_client().delete(
            collection_name=self.cfg.cognition.chunks_collection,
            points_selector=qm.FilterSelector(filter=flt))

    def rename_document(self, doc_id: str, old_path: str, new_path: str) -> None:
        """RENAMED：仅更新 manifest 路径，零重嵌入。"""
        with self.conn:
            self.conn.execute(
                "UPDATE documents SET source_path = ?, file_name = ?, file_mtime_ns = ? WHERE id = ?",
                (new_path, Path(new_path).name, Path(new_path).stat().st_mtime_ns, doc_id),
            )

    def apply_scan(self, scan_result, *, reindex_modified: bool = True) -> dict:
        """按 ScanResult 执行全部变更。doc_id 由相对路径确定，无需 docid_policy。"""
        stats = {"indexed": 0, "renamed": 0, "deleted": 0, "unchanged": 0, "errors": []}
        for st in scan_result.states:
            try:
                if st.status == "UNCHANGED":
                    stats["unchanged"] += 1
                elif st.status in ("NEW", "MODIFIED") and reindex_modified:
                    self.index_file(st.path, state=st)
                    stats["indexed"] += 1
                elif st.status == "RENAMED":
                    self.rename_document(st.document_id, st.renamed_from, st.path)
                    stats["renamed"] += 1
                elif st.status == "DELETED":
                    self.remove_document(st.document_id, st.path)
                    stats["deleted"] += 1
                elif st.status == "ERROR":
                    stats["errors"].append({"path": st.path, "error": st.error})
            except Exception as exc:
                logger.exception("cognition apply %s 失败", st.path)
                stats["errors"].append({"path": st.path, "status": st.status,
                                        "error": f"{type(exc).__name__}: {exc}"})
        set_meta(self.conn, "last_cognition_scan", time.strftime("%Y-%m-%dT%H:%M:%S"))
        return stats
