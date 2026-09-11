"""Index Pipeline（M8，Addendum §34-38 + spec §23/§52）。

流程（MODIFIED/NEW 相同，禁止先删旧数据）：
  Read -> Parse -> Chunk -> Lexical -> Embedding（全部 staging，内存中）
  -> SQLite 单事务原子替换（documents/sections/chunks/FTS）
  -> Qdrant delete-by-document + upsert
任何 staging 步骤失败 => 旧版本继续可搜索。

Delete：tombstone + FTS/Qdrant 级联清理。Rename：仅更新 manifest，不重嵌入。
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from qdrant_client import models as qm

from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import SCHEMA_VERSION, Config
from app.core.errors import IndexInconsistencyError, SourceFileError
from app.core.health import _runtime_profile  # noqa: F401  (保持 import 兼容)
from app.indexing.scanner import FileState, sha256_file
from app.parser.markdown_parser import parse_markdown
from app.retrieval.dense import build_section_records, point_id, section_point_id
from app.storage.migrations import get_meta, init_schema, set_meta
from app.storage.repositories.knowledge import (
    ChunkRepository,
    DocumentRepository,
    SectionRepository,
)

logger = logging.getLogger(__name__)


class IndexPipeline:
    def __init__(self, cfg: Config, conn: sqlite3.Connection, embedder) -> None:
        """embedder: 提供 embed_documents(texts, batch_size) 的对象
        （通常为 InferenceManager 的包装）。"""
        self.cfg = cfg
        self.conn = conn
        self.chunker = SemanticChunker(cfg.chunking)
        self.embedder = embedder
        init_schema(conn)
        # 幂等创建 Qdrant collections（全新 catalog/collection 场景，如 I0 全量索引）
        from app.storage.qdrant import QdrantStore

        QdrantStore(cfg.qdrant).ensure_collections()

    # ---- 索引 / 重索引 ----
    def index_file(self, path: str | Path, *, state: FileState | None = None,
                   doc_id: str | None = None) -> dict:
        """NEW 或 MODIFIED：staging 全部成功后才原子替换。

        doc_id: 索引计划（docid_policy）覆盖值；缺省用 metadata report_code 或 stem。
        """
        path = Path(path)
        t0 = time.perf_counter()
        # 1) staging：读 + 解析 + 分块（失败即抛，不动旧数据）
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceFileError(f"读取失败: {path}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise SourceFileError(f"编码错误: {path}: {exc}") from exc

        parsed = parse_markdown(text)
        doc_id = doc_id or parsed.metadata.get("report_code") or path.stem
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

        # 2) Embedding（staging 内完成；失败则旧版本不受影响）
        batch = self.cfg.embedding.batch_size_gpu if self.embedder.device_kind != "cpu" \
            else self.cfg.embedding.batch_size_cpu
        vectors = self.embedder.embed_documents(
            [c.embedding_text for c in chunks], batch_size=batch)
        domain = doc_row["domain"]
        completed_at = doc_row["completed_at"]
        points = [
            qm.PointStruct(
                id=point_id(c.chunk_id),
                vector={"dense": vec},
                payload={
                    "chunk_id": c.chunk_id, "document_id": doc_id,
                    "section_id": c.section_id, "content_type": c.content_type,
                    "evidence_level": c.evidence_level, "domain": domain,
                    "completed_at": completed_at,
                },
            )
            for c, vec in zip(chunks, vectors)
        ]

        # sections 向量（M10 教训：sections 由单独管线负责，漏掉会导致
        # sections collection 空 -> Parent Boost 无从检索；I0 起随 chunks 同批嵌入）
        section_points = []
        section_records = build_section_records(parsed, doc_id)
        if section_records:
            svecs = self.embedder.embed_documents(
                [r["embedding_text"] for r in section_records], batch_size=batch)
            section_points = [
                qm.PointStruct(
                    id=section_point_id(doc_id, r["section_id"]),
                    vector={"dense": vec},
                    payload={
                        "section_id": r["section_id"], "document_id": doc_id,
                        "heading": r["heading"], "section_type": r["section_type"],
                    },
                )
                for r, vec in zip(section_records, svecs)
            ]

        # 3) SQLite 原子替换（单事务；删除顺序：chunks/FTS -> sections，避免 FK 冲突）
        doc_repo = DocumentRepository(self.conn)
        sec_repo = SectionRepository(self.conn)
        chunk_repo = ChunkRepository(self.conn)
        with self.conn:
            doc_repo.upsert(doc_row)
            # 旧数据删除（此时新版本已验证可用，符合 §35/52）
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_terms WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_trigram WHERE document_id = ?", (doc_id,))
            sec_repo.replace_for_document(section_rows)
            chunk_repo.upsert_batch(chunk_rows)

        # 4) Qdrant 替换（SQLite 已提交；失败交给 reconcile repair）
        self._qdrant_replace(doc_id, points, section_points)

        ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("indexed %s: chunks=%d points=%d sections=%d in %dms",
                    doc_id, len(chunks), len(points), len(section_points), ms)
        return {"document_id": doc_id, "chunks": len(chunks),
                "sections": len(section_points), "points": len(points), "ms": ms}

    def _qdrant_replace(self, doc_id: str, points: list[qm.PointStruct],
                        section_points: list[qm.PointStruct] | None = None) -> None:
        flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=doc_id))])
        client = self.qdrant_client()
        client.delete(collection_name=self.cfg.qdrant.chunks_collection,
                      points_selector=qm.FilterSelector(filter=flt))
        for i in range(0, len(points), 64):
            client.upsert(collection_name=self.cfg.qdrant.chunks_collection,
                          points=points[i:i + 64], wait=True)
        if section_points:
            client.delete(collection_name=self.cfg.qdrant.sections_collection,
                          points_selector=qm.FilterSelector(filter=flt))
            for i in range(0, len(section_points), 64):
                client.upsert(collection_name=self.cfg.qdrant.sections_collection,
                              points=section_points[i:i + 64], wait=True)

    def qdrant_client(self):
        if getattr(self, "_client", None) is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self.cfg.qdrant.url, timeout=30)
        return self._client

    # ---- 删除 / 改名 ----
    def remove_document(self, doc_id: str, source_path: str) -> None:
        """DELETED：tombstone + 级联清理（Addendum §37）。"""
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
        for collection in (self.cfg.qdrant.chunks_collection, self.cfg.qdrant.sections_collection):
            self.qdrant_client().delete(collection_name=collection,
                                        points_selector=qm.FilterSelector(filter=flt))

    def rename_document(self, doc_id: str, old_path: str, new_path: str) -> None:
        """RENAMED：仅更新 manifest 路径，零重嵌入（Addendum §38）。"""
        with self.conn:
            self.conn.execute(
                "UPDATE documents SET source_path = ?, file_name = ?, file_mtime_ns = ? WHERE id = ?",
                (new_path, Path(new_path).name, Path(new_path).stat().st_mtime_ns, doc_id),
            )

    # ---- 同步入口 ----
    def apply_scan(self, scan_result, *, reindex_modified: bool = True) -> dict:
        """按 ScanResult 执行全部变更（I0 起经 docid_policy 收录/命名计划）。"""
        from app.indexing.docid_policy import build_index_plan

        plan = build_index_plan(scan_result, self.conn)
        stats = {"indexed": 0, "renamed": 0, "deleted": 0, "unchanged": 0,
                 "excluded": plan.exclusions, "disambiguated": plan.disambiguated,
                 "errors": []}
        for st in scan_result.states:
            try:
                if st.status == "UNCHANGED":
                    stats["unchanged"] += 1
                elif st.status in ("NEW", "MODIFIED") and reindex_modified:
                    if st.path in plan.excluded_paths:
                        continue
                    assigned = plan.assignments.get(st.path)
                    if assigned is None:
                        # 计划未分配身份的候选禁止回退到默认 doc_id：
                        # 该 doc_id 可能已被既有文档占用，写入即静默覆盖。
                        raise IndexInconsistencyError(f"索引计划未分配 doc_id: {st.path}")
                    r = self.index_file(st.path, state=st, doc_id=assigned)
                    stats["indexed"] += 1
                    stats.setdefault("details", []).append(r)
                elif st.status == "RENAMED":
                    self.rename_document(st.document_id, st.renamed_from, st.path)
                    stats["renamed"] += 1
                elif st.status == "DELETED":
                    self.remove_document(st.document_id, st.path)
                    stats["deleted"] += 1
                elif st.status == "ERROR":
                    stats["errors"].append({"path": st.path, "error": st.error})
            except Exception as exc:
                logger.exception("apply %s 失败", st.path)
                stats["errors"].append({"path": st.path, "status": st.status,
                                        "error": f"{type(exc).__name__}: {exc}"})
        set_meta(self.conn, "last_full_scan", time.strftime("%Y-%m-%dT%H:%M:%S"))
        return stats


class EmbedderAdapter:
    """把 InferenceManager 适配成 pipeline 需要的 embed_documents 接口。"""

    def __init__(self, cfg: Config, manager) -> None:
        self.cfg = cfg
        self.manager = manager
        self.device_kind = manager.device_kind or "rocm"

    def embed_documents(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        return self.manager.call(
            "embed_documents", {"texts": texts, "batch_size": batch_size},
            timeout=max(self.cfg.inference.worker_timeout_seconds, 300),
        )
