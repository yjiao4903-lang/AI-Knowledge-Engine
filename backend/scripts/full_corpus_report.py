"""I0 Full Corpus 统计报告（主计划 §11）。

聚合 data/last_scan.json（scan 产物）+ catalog_full.db + Qdrant 计数，
输出 data/full_corpus_stats.json 与 docs/FULL_CORPUS_REPORT.md 的数据底稿。

用法：
  KE_CONFIG=config/config.full.yaml python backend/scripts/full_corpus_report.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402


def main() -> int:
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    from app.storage.qdrant import QdrantStore
    from app.storage.sqlite import connect

    conn = connect(cfg.sqlite.path, read_only=True)
    scan_data = {}
    scan_path = PROJECT_ROOT / "data" / "last_scan.json"
    if scan_path.exists():
        scan_data = json.loads(scan_path.read_text(encoding="utf-8"))

    catalog_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    sections = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts_terms = conn.execute("SELECT COUNT(*) FROM chunks_fts_terms").fetchone()[0]
    fts_trigram = conn.execute("SELECT COUNT(*) FROM chunks_fts_trigram").fetchone()[0]

    store = QdrantStore(cfg.qdrant)
    qdrant_points = 0
    qdrant_sections_points = 0
    for name, attr in ((cfg.qdrant.chunks_collection, "qdrant_points"),
                       (cfg.qdrant.sections_collection, "qdrant_sections_points")):
        try:
            info = store.collection_info(name)
            n = info.get("points_count") or 0
        except Exception:
            n = -1  # collection 缺失/不可达：显式标记，禁止静默当 0
        if attr == "qdrant_points":
            qdrant_points = n
        else:
            qdrant_sections_points = n

    # 排除与失败（来自 scan 产物）
    excluded = scan_data.get("excluded", [])
    reasons = Counter(e.get("reason", "?") for e in excluded)
    errors = scan_data.get("errors", [])
    encoding_failures = [e for e in errors if "UnicodeDecode" in e.get("error", "")
                         or "编码" in e.get("error", "")]
    total_md = sum(len(v) for v in scan_data.get("states", {}).values()) + scan_data.get("indexed_count", 0)
    # states 只记录未收录文件；总数用 preflight 基准
    preflight_path = PROJECT_ROOT / "data" / "full_corpus_preflight.json"
    preflight_total = 0
    if preflight_path.exists():
        preflight_total = json.loads(preflight_path.read_text(encoding="utf-8")).get("total_md_files", 0)

    oversized = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE LENGTH(plain_text) > ?",
        (cfg.chunking.hard_max_chars,)).fetchone()[0]
    doc_ids = [r[0] for r in conn.execute("SELECT id FROM documents").fetchall()]
    dup_ids = [k for k, v in Counter(doc_ids).items() if v > 1]

    stats = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {"roots": cfg.knowledge_base.roots, "sqlite": cfg.sqlite.path,
                   "collections": [cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection]},
        "total_files_scanned": preflight_total or total_md,
        "indexed_files": scan_data.get("indexed_count", catalog_docs),
        "parsed_files": catalog_docs,
        "skipped_files": len(excluded),
        "skipped_by_reason": dict(reasons),
        "failed_files": len(errors),
        "errors_sample": errors[:20],
        "encoding_failures": len(encoding_failures),
        "total_sections": sections,
        "total_chunks": chunks,
        "fts_terms_count": fts_terms,
        "fts_trigram_count": fts_trigram,
        "qdrant_points": qdrant_points,
        "qdrant_sections_points": qdrant_sections_points,
        "duplicate_document_ids_in_catalog": len(dup_ids),
        "disambiguated_ids": scan_data.get("disambiguated", 0),
        "oversized_chunks_gt_hardmax": oversized,
        "parser_warnings": "not_tracked(v0.1.1 无告警通道)",
        "chunker_warnings": "not_tracked",
        "consistency": {
            "chunks": chunks, "fts_terms": fts_terms,
            "fts_trigram": fts_trigram, "qdrant_points": qdrant_points,
            "equal": chunks == fts_terms == fts_trigram == qdrant_points,
        },
    }
    (PROJECT_ROOT / "data" / "full_corpus_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["consistency"]["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
