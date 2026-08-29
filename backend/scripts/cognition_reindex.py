"""运维 CLI：Cognition 只读索引（I6，主计划 §48-50）。

用法：
  python backend/scripts/cognition_reindex.py scan [--config PATH]
  python backend/scripts/cognition_reindex.py check [--config PATH]

scan ：扫描 cognition 白名单子目录并应用变更（独立 catalog + 独立 collection）。
check：一致性检查（SQLite chunks vs FTS vs Qdrant points）。
READ ONLY：本脚本只读消费 cognition Markdown，绝不写认知（含 Proposal/Apply）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "check"])
    ap.add_argument("--config", default=None, help="配置文件路径（缺省 KE_CONFIG 或 config.yaml）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not cfg.cognition.enabled:
        print("cognition 检索已禁用（config: cognition.enabled=false），跳过")
        return 0

    from app.cognition.pipeline import CognitionPipeline, ensure_cognition_collection
    from app.cognition.scanner import scan as cog_scan
    from app.indexing.pipeline import EmbedderAdapter
    from app.inference.manager import InferenceManager
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    conn = connect(cfg.cognition.catalog_path)
    init_schema(conn)

    if args.cmd == "check":
        chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        fts_terms = conn.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0]
        fts_trigram = conn.execute("SELECT count(*) FROM chunks_fts_trigram").fetchone()[0]
        docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        points = None
        try:
            ensure_cognition_collection(cfg)
            from qdrant_client import QdrantClient

            points = QdrantClient(url=cfg.qdrant.url, timeout=10).count(
                collection_name=cfg.cognition.chunks_collection, exact=True).count
        except Exception as exc:
            points = f"error: {exc}"
        report = {
            "documents": docs, "chunks": chunks,
            "fts_terms": fts_terms, "fts_trigram": fts_trigram,
            "qdrant_points": points,
            "consistent": chunks == fts_terms == fts_trigram,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["consistent"] else 1

    mgr = InferenceManager(cfg)
    try:
        pipeline = CognitionPipeline(cfg, conn, EmbedderAdapter(cfg, mgr))
        t0 = time.perf_counter()
        result = cog_scan(cfg, conn)
        print("states:", {s: len(result.by_status(s)) for s in
                          ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")})
        stats = pipeline.apply_scan(result)
        stats["scan_seconds"] = round(time.perf_counter() - t0, 1)
        print(json.dumps({k: v for k, v in stats.items()},
                         ensure_ascii=False, indent=2, default=str))
        return 0 if not stats["errors"] else 1
    finally:
        mgr.shutdown()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
