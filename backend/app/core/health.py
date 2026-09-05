"""健康检查聚合（M1-07）。

返回 sqlite / qdrant / inference 设备状态。模型冒烟结果从
data/runtime_profile.json 读取（M0 产物），避免 health 检查加载模型。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.chunking.chunk_models import CHUNKER_VERSION
from app.core.config import LEXICAL_VERSION, SCHEMA_VERSION, Config
from app.inference.device import torch_info
from app.storage.migrations import check_fts_capability
from app.storage.sqlite import connect


def _runtime_profile(data_dir: Path) -> dict:
    p = data_dir / "runtime_profile.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _index_generation(cfg: Config) -> dict:
    """I0：catalog 世代信息（schema/parser/chunker 版本 + 最近全量扫描）。"""
    try:
        conn = connect(cfg.sqlite.path, read_only=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n, MIN(parser_version) AS pv, "
                "MIN(chunker_version) AS cv, MIN(schema_version) AS sv FROM documents"
            ).fetchone()
            from app.storage.migrations import get_meta

            last_scan = get_meta(conn, "last_full_scan")
        finally:
            conn.close()
        return {
            "documents": row["n"] or 0,
            "schema_version": row["sv"] or SCHEMA_VERSION,
            "parser_version": row["pv"] or "0.1.0",
            "chunker_version": row["cv"] or CHUNKER_VERSION,
            "lexical_version": LEXICAL_VERSION,
            "last_full_scan": last_scan,
        }
    except Exception:
        return {"documents": 0, "status": "error"}


def _qdrant_health(cfg: Config) -> dict:
    """Optional dense-index health without making qdrant_client a base import."""
    try:
        from app.storage.qdrant import QdrantStore

        return QdrantStore(cfg.qdrant).health()
    except Exception as exc:
        return {
            "status": "unavailable",
            "url": cfg.qdrant.url,
            "error": f"{type(exc).__name__}: {exc}",
        }


def collect_health(cfg: Config) -> dict:
    # sqlite + FTS
    sqlite_status = {"status": "error", "fts5": False, "trigram": False}
    try:
        conn = connect(cfg.sqlite.path, read_only=True)
        try:
            fts = check_fts_capability(conn)
            sqlite_status = {"status": "ok", "fts5": fts["fts5"], "trigram": fts["trigram"]}
        finally:
            conn.close()
    except Exception:
        pass

    # qdrant is an optional derived index for the base lexical runtime.
    qdrant_status = _qdrant_health(cfg)

    # I6：cognition 只读语义检索状态（独立 collection + 独立 catalog）
    cognition_status: dict = {"enabled": cfg.cognition.enabled}
    if cfg.cognition.enabled:
        try:
            from app.storage.qdrant import QdrantStore

            cog_conn = connect(cfg.cognition.catalog_path, read_only=True)
            try:
                cognition_status["catalog_documents"] = cog_conn.execute(
                    "SELECT count(*) FROM documents").fetchone()[0]
            finally:
                cog_conn.close()
            info = QdrantStore(cfg.qdrant).client.get_collection(
                cfg.cognition.chunks_collection)
            cognition_status["collection"] = cfg.cognition.chunks_collection
            cognition_status["points_count"] = info.points_count
            cognition_status["status"] = "ok"
        except Exception as exc:
            cognition_status["status"] = "error"
            cognition_status["error"] = str(exc)

    # inference（来自 M0 runtime_profile；模型未加载时不做实际推理）
    profile = _runtime_profile(Path(cfg.paths.data_dir))
    torch = torch_info()
    inference_status = {
        "device": profile.get("inference_device"),
        "fallback_used": profile.get("fallback_used"),
        "torch_available": torch.get("available", False),
        "torch_version": torch.get("torch_version"),
        "hip_version": torch.get("hip_version"),
    }

    overall = (
        "ok"
        if sqlite_status["status"] == "ok" and qdrant_status["status"] == "ok"
        else "degraded"
    )
    return {
        "status": overall,
        "sqlite": sqlite_status,
        "qdrant": qdrant_status,
        "cognition": cognition_status,
        "embedding": {"model": cfg.embedding.model, **{k: inference_status.get(k) for k in ("device",)}},
        "reranker": {"model": cfg.reranker.model, **{k: inference_status.get(k) for k in ("device",)}},
        "inference": inference_status,
        "index_generation": _index_generation(cfg),
    }
