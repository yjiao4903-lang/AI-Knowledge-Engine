"""健康检查聚合（M1-07）。

返回 sqlite / qdrant / inference 设备状态。模型冒烟结果从
data/runtime_profile.json 读取（M0 产物），避免 health 检查加载模型。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Config
from app.inference.device import torch_info
from app.storage.migrations import check_fts_capability
from app.storage.qdrant import QdrantStore
from app.storage.sqlite import connect


def _runtime_profile(data_dir: Path) -> dict:
    p = data_dir / "runtime_profile.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


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

    # qdrant
    qdrant_status = QdrantStore(cfg.qdrant).health()

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
        "embedding": {"model": cfg.embedding.model, **{k: inference_status.get(k) for k in ("device",)}},
        "reranker": {"model": cfg.reranker.model, **{k: inference_status.get(k) for k in ("device",)}},
        "inference": inference_status,
    }
