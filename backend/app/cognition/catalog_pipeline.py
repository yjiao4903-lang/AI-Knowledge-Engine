"""Model-free read-only Cognition catalog pipeline (DL-01C).

Cognition source Markdown remains owned by the external Cognition application.
This module only builds KE's derived SQLite/FTS catalog and durable vector-sync
markers. It never imports Qdrant/model code and never writes source Markdown.
"""

from __future__ import annotations

import time

from app.cognition.identity import cognition_doc_id
from app.indexing.catalog_pipeline import CatalogIndexPipeline
from app.storage.migrations import set_meta


class CognitionCatalogPipeline(CatalogIndexPipeline):
    """Maintain KE's local Cognition-derived SQLite/FTS catalog only."""

    def index_file(self, path, *, state=None, doc_id: str | None = None) -> dict:
        stable_id = doc_id or (state.document_id if state is not None else None)
        stable_id = stable_id or cognition_doc_id(self.cfg, path)
        return super().index_file(path, state=state, doc_id=stable_id)

    def apply_scan(self, scan_result, *, reindex_modified: bool = True) -> dict:
        """Apply Cognition scanner states without report doc-id policy.

        The scanner carries an existing ``document_id`` for MODIFIED/RENAMED
        objects, preserving the current stable-id-across-rename behavior.
        """

        stats = {
            "indexed": 0,
            "renamed": 0,
            "deleted": 0,
            "unchanged": 0,
            "errors": [],
        }
        for state in scan_result.states:
            try:
                if state.status == "UNCHANGED":
                    stats["unchanged"] += 1
                elif state.status in ("NEW", "MODIFIED") and reindex_modified:
                    doc_id = state.document_id or cognition_doc_id(self.cfg, state.path)
                    self.index_file(state.path, state=state, doc_id=doc_id)
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
                stats["errors"].append(
                    {
                        "path": state.path,
                        "status": state.status,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        set_meta(self.conn, "last_cognition_scan", time.strftime("%Y-%m-%dT%H:%M:%S"))
        stats["vector_pending"] = len(self.pending_vector_sync())
        return stats
