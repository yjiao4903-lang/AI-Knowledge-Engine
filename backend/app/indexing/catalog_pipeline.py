"""Model-free report catalog / FTS indexing pipeline (DL-01B).

This pipeline is the authoritative base ingestion path for report Markdown. It
updates SQLite + both FTS indexes without importing Qdrant, loading embedding
models, or starting the inference worker. Vector maintenance is recorded as an
explicit pending derived-index operation and can be executed separately.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

from app.chunking.semantic_chunker import SemanticChunker
from app.core.config import SCHEMA_VERSION, Config
from app.core.errors import IndexInconsistencyError, SourceFileError
from app.indexing.scanner import FileState, sha256_file
from app.parser.markdown_parser import parse_markdown
from app.storage.migrations import init_schema, set_meta
from app.storage.repositories.knowledge import (
    ChunkRepository,
    DocumentRepository,
    SectionRepository,
)

logger = logging.getLogger(__name__)

_VECTOR_PENDING_PREFIX = "vector_pending:"


class CatalogIndexPipeline:
    """Parse/chunk and atomically replace the local SQLite/FTS catalog only."""

    def __init__(self, cfg: Config, conn: sqlite3.Connection) -> None:
        self.cfg = cfg
        self.conn = conn
        self.chunker = SemanticChunker(cfg.chunking)
        init_schema(conn)

    def _pending_key(self, doc_id: str) -> str:
        return f"{_VECTOR_PENDING_PREFIX}{doc_id}"

    def _mark_vector_pending(
        self,
        doc_id: str,
        *,
        operation: str,
        source_path: str,
        sha256: str | None,
    ) -> None:
        payload = json.dumps(
            {
                "document_id": doc_id,
                "operation": operation,
                "source_path": source_path,
                "sha256": sha256,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._pending_key(doc_id), payload),
        )

    def pending_vector_sync(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE ? ORDER BY key",
            (f"{_VECTOR_PENDING_PREFIX}%",),
        ).fetchall()
        pending: list[dict] = []
        for row in rows:
            doc_id = row["key"][len(_VECTOR_PENDING_PREFIX):]
            try:
                item = json.loads(row["value"])
            except (TypeError, json.JSONDecodeError):
                item = {}
            item["document_id"] = doc_id
            item.setdefault("operation", "upsert")
            pending.append(item)
        return pending

    def clear_vector_pending(self, doc_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM meta WHERE key = ?", (self._pending_key(doc_id),))

    def index_file(
        self,
        path: str | Path,
        *,
        state: FileState | None = None,
        doc_id: str | None = None,
    ) -> dict:
        """Index one report into SQLite/FTS and mark vector maintenance pending."""

        path = Path(path)
        t0 = time.perf_counter()
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
                "id": f"{doc_id}:{s.section_id}",
                "document_id": doc_id,
                "parent_section_id": f"{doc_id}:{s.parent_id}" if s.parent_id else None,
                "level": s.level,
                "heading": s.heading,
                "heading_path": " > ".join(s.heading_path),
                "section_type": s.section_type,
                "ordinal": s.ordinal,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in parsed.sections
        ]
        chunk_rows = []
        for chunk in chunks:
            row = chunk.to_db_dict()
            row["section_id"] = f"{doc_id}:{chunk.section_id}"
            chunk_rows.append(row)

        with self.conn:
            DocumentRepository(self.conn).upsert(doc_row)
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_terms WHERE document_id = ?", (doc_id,))
            self.conn.execute("DELETE FROM chunks_fts_trigram WHERE document_id = ?", (doc_id,))
            SectionRepository(self.conn).replace_for_document(section_rows)
            ChunkRepository(self.conn).upsert_batch(chunk_rows)
            self._mark_vector_pending(
                doc_id,
                operation="upsert",
                source_path=str(path),
                sha256=sha,
            )

        ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.info("catalog indexed %s: chunks=%d in %.1fms; vector=pending", doc_id, len(chunks), ms)
        return {
            "document_id": doc_id,
            "chunks": len(chunks),
            "sections": len(section_rows),
            "ms": ms,
            "vector_status": "pending",
        }

    def remove_document(self, doc_id: str, source_path: str) -> None:
        row = self.conn.execute(
            "SELECT sha256 FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        last_sha = row["sha256"] if row else ""
        with self.conn:
            if row:
                self.conn.execute(
                    "INSERT OR REPLACE INTO document_tombstones "
                    "(source_path, document_id, last_sha256, deleted_at) VALUES (?,?,?,?)",
                    (source_path, doc_id, last_sha, time.strftime("%Y-%m-%dT%H:%M:%S")),
                )
            DocumentRepository(self.conn).delete(doc_id)
            self._mark_vector_pending(
                doc_id,
                operation="delete",
                source_path=source_path,
                sha256=last_sha or None,
            )

    def rename_document(self, doc_id: str, old_path: str, new_path: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE documents SET source_path = ?, file_name = ?, file_mtime_ns = ? WHERE id = ?",
                (new_path, Path(new_path).name, Path(new_path).stat().st_mtime_ns, doc_id),
            )
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = ?", (self._pending_key(doc_id),)
            ).fetchone()
            if row:
                try:
                    payload = json.loads(row["value"])
                except (TypeError, json.JSONDecodeError):
                    payload = {"document_id": doc_id, "operation": "upsert"}
                payload["source_path"] = new_path
                payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self.conn.execute(
                    "UPDATE meta SET value = ? WHERE key = ?",
                    (json.dumps(payload, ensure_ascii=False, sort_keys=True), self._pending_key(doc_id)),
                )

    def apply_scan(self, scan_result, *, reindex_modified: bool = True) -> dict:
        """Apply file changes to the model-free catalog; never touches Qdrant/models."""

        from app.indexing.docid_policy import build_index_plan

        plan = build_index_plan(scan_result, self.conn)
        stats = {
            "indexed": 0,
            "renamed": 0,
            "deleted": 0,
            "unchanged": 0,
            "excluded": plan.exclusions,
            "disambiguated": plan.disambiguated,
            "errors": [],
        }
        for state in scan_result.states:
            try:
                if state.status == "UNCHANGED":
                    stats["unchanged"] += 1
                elif state.status in ("NEW", "MODIFIED") and reindex_modified:
                    if state.path in plan.excluded_paths:
                        continue
                    assigned = plan.assignments.get(state.path)
                    if assigned is None:
                        # 计划未分配身份的候选禁止回退到默认 doc_id：
                        # 该 doc_id 可能已被既有文档占用，写入即静默覆盖。
                        raise IndexInconsistencyError(f"索引计划未分配 doc_id: {state.path}")
                    self.index_file(state.path, state=state, doc_id=assigned)
                    stats["indexed"] += 1
                elif state.status == "RENAMED":
                    self.rename_document(state.document_id, state.renamed_from, state.path)
                    stats["renamed"] += 1
                elif state.status == "DELETED":
                    self.remove_document(state.document_id, state.path)
                    stats["deleted"] += 1
                elif state.status == "ERROR":
                    stats["errors"].append({"path": state.path, "error": state.error})
            except Exception as exc:
                logger.exception("catalog apply %s 失败", state.path)
                stats["errors"].append(
                    {
                        "path": state.path,
                        "status": state.status,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        set_meta(self.conn, "last_full_scan", time.strftime("%Y-%m-%dT%H:%M:%S"))
        stats["vector_pending"] = len(self.pending_vector_sync())
        return stats
