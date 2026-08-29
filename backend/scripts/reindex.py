"""运维 CLI：全量增量扫描 / 一致性检查 / 修复（M8；I0 扩展）。

用法：
  python backend/scripts/reindex.py scan [--config PATH]    # 全量 manifest 扫描 + 应用变更
  python backend/scripts/reindex.py check [--config PATH]   # 一致性检查（SQLite vs FTS vs Qdrant）
  python backend/scripts/reindex.py repair [--config PATH]  # 修复 Qdrant 缺失/孤儿

scan 结果摘要写入 data/last_scan.json（供 FULL_CORPUS_REPORT 统计）。
配置选择：--config > 环境变量 KE_CONFIG > config/config.yaml > config.example.yaml。
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
    ap.add_argument("cmd", choices=["scan", "check", "repair"])
    ap.add_argument("--config", default=None, help="配置文件路径（缺省 KE_CONFIG 或 config.yaml）")
    args = ap.parse_args()

    cfg = load_config(args.config)
    from app.indexing.pipeline import EmbedderAdapter, IndexPipeline
    from app.indexing.reconcile import check_consistency, repair
    from app.indexing.scanner import scan
    from app.inference.manager import InferenceManager
    from app.storage.sqlite import connect

    conn = connect(cfg.sqlite.path)

    if args.cmd == "check":
        report = check_consistency(cfg, conn)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["consistent"] else 1

    mgr = InferenceManager(cfg)
    try:
        pipeline = IndexPipeline(cfg, conn, EmbedderAdapter(cfg, mgr))
        if args.cmd == "scan":
            t0 = time.perf_counter()
            result = scan(cfg, conn)
            print("states:", {s: len(result.by_status(s)) for s in
                              ("NEW", "MODIFIED", "RENAMED", "DELETED", "UNCHANGED", "ERROR")})
            stats = pipeline.apply_scan(result)
            stats["scan_seconds"] = round(time.perf_counter() - t0, 1)
            print(json.dumps({k: v for k, v in stats.items() if k != "details"},
                             ensure_ascii=False, indent=2, default=str))
            out = PROJECT_ROOT / "data" / "last_scan.json"
            out.write_text(json.dumps({
                "config": str(args.config or ""),
                "roots": cfg.knowledge_base.roots,
                "sqlite_path": cfg.sqlite.path,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "states": {s: [st.path for st in result.by_status(s)]
                           for s in ("NEW", "MODIFIED", "RENAMED", "DELETED", "ERROR")},
                "excluded": stats.get("excluded", []),
                "disambiguated": stats.get("disambiguated", 0),
                "errors": stats.get("errors", []),
                "indexed_count": stats.get("indexed", 0),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0 if not stats["errors"] else 1
        if args.cmd == "repair":
            stats = repair(cfg, conn, embedder=pipeline.embedder)
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            return 0
        return 2
    finally:
        mgr.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
