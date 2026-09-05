"""Stable identifiers for KE's read-only Cognition-derived catalog."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Config


def cognition_doc_id(cfg: Config, path: str | Path) -> str:
    """Return the initial Cognition derived document id for a source path.

    The scanner preserves an existing id across pure renames by carrying the old
    manifest ``document_id``. This helper is therefore used for new objects only
    (or as a fallback when no manifest id exists).
    """

    root = Path(cfg.cognition.root)
    rel = Path(path).relative_to(root).with_suffix("")
    return f"{cfg.cognition.docid_prefix}:{rel.as_posix()}"
