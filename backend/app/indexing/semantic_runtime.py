"""Runtime recovery helpers for optional semantic capabilities.

DL-01 keeps the local SQLite/FTS path authoritative and model-free. Semantic
services are optional and may be unavailable when KE starts. These helpers let
an explicit semantic action (dense/hybrid search or vector sync) retry
initialization later, without background polling or a process restart.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_REPORT_INIT_LOCK = threading.Lock()
_COGNITION_INIT_LOCK = threading.Lock()


def _build_report_pipeline(app):
    from app.indexing.pipeline import EmbedderAdapter, IndexPipeline

    return IndexPipeline(
        app.state.cfg,
        app.state.conn,
        EmbedderAdapter(app.state.cfg, app.state.manager),
    )


def _build_cognition_pipeline(app, cog):
    from app.cognition.pipeline import CognitionPipeline
    from app.indexing.pipeline import EmbedderAdapter

    return CognitionPipeline(
        app.state.cfg,
        cog["conn"],
        EmbedderAdapter(app.state.cfg, app.state.manager),
    )


def ensure_report_semantic(app) -> bool:
    """Ensure report semantic indexing/search capability is available.

    The function is idempotent. If startup initialization previously failed, an
    explicit semantic request can retry after Qdrant/service recovery. Failure
    never changes the lexical catalog path.
    """

    if getattr(app.state, "pipeline", None) is not None and getattr(
        app.state, "qdrant_available", False
    ):
        return True

    with _REPORT_INIT_LOCK:
        if getattr(app.state, "pipeline", None) is not None and getattr(
            app.state, "qdrant_available", False
        ):
            return True
        try:
            pipeline = _build_report_pipeline(app)
        except Exception as exc:
            app.state.pipeline = None
            app.state.qdrant_available = False
            app.state.semantic_last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("report semantic capability recovery failed: %s", exc)
            return False

        app.state.pipeline = pipeline
        app.state.qdrant_available = True
        app.state.semantic_last_error = None
        logger.info("report semantic capability recovered without process restart")
        return True


def ensure_cognition_semantic(app) -> bool:
    """Ensure optional Cognition semantic capability is available.

    Cognition's derived SQLite/FTS catalog remains usable even when this returns
    ``False``. Formal Cognition state is never written by this helper.
    """

    cog = getattr(app.state, "cognition", None) or {}
    if not cog.get("enabled"):
        return False
    if cog.get("semantic_pipeline") is not None and cog.get("semantic_available", False):
        return True

    with _COGNITION_INIT_LOCK:
        cog = getattr(app.state, "cognition", None) or {}
        if not cog.get("enabled"):
            return False
        if cog.get("semantic_pipeline") is not None and cog.get("semantic_available", False):
            return True
        try:
            pipeline = _build_cognition_pipeline(app, cog)
        except Exception as exc:
            cog["semantic_pipeline"] = None
            cog["semantic_available"] = False
            cog["semantic_last_error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("cognition semantic capability recovery failed: %s", exc)
            return False

        cog["semantic_pipeline"] = pipeline
        cog["semantic_available"] = True
        cog["semantic_last_error"] = None
        logger.info("cognition semantic capability recovered without process restart")
        return True
