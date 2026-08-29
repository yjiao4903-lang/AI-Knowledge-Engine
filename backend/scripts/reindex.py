"""运维 CLI：全量增量扫描 / 一致性检查 / 修复（M8）。

用法：
  python backend/scripts/reindex.py scan                 # 全量 manifest 扫描 + 应用变更
  python backend/scripts/reindex.py check                # 一致性检查（SQLite vs FTS vs Qdrant）
  python backend/scripts/reindex.py repair               # 修复 Qdrant 缺失/孤儿
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    cfg = load_config()
    from app.indexing.pipeline import EmbedderAdapter, IndexPipeline
    from app.indexing.reconcile import check_consistency, repair
    from app.indexing.scanner import scan
    from app.inference.manager import InferenceManager
    from app.storage.sqlite import connect

    conn = connect(cfg.sqlite.path)

    if cmd == "check":
        report = check_consistency(cfg, conn)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["consistent"] else 1

    mgr = InferenceManager(cfg)
    try:
        pipeline = IndexPipeline(cfg, conn, EmbedderAdapter(cfg, mgr))
        if cmd == "scan":
            result = scan(cfg, conn)
            print("states:", {s: len(result.by_status(s)) for s in
                              ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")})
            stats = pipeline.apply_scan(result)
            print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
            return 0 if not stats["errors"] else 1
        if cmd == "repair":
            stats = repair(cfg, conn, embedder=pipeline.embedder)
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            return 0
        print(f"unknown command: {cmd}")
        return 2
    finally:
        mgr.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
