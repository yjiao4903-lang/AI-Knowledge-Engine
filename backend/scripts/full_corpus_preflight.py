"""I0 预检：对全量归档做只读快速扫描，输出 data/full_corpus_preflight.json。

目的（HANDOFF_I0 §0 就绪性检查）：
  - 统计 .md 文件总数与目录分布；
  - 检测非 UTF-8 文件（pipeline 将计入 Failed Files）；
  - 检测重复 document_id（report_code / stem 冲突会导致 pipeline 静默覆盖，
    必须在索引前知晓规模）；
  - 检测空文件 / 超大文件。

只读操作，不修改任何归档文件。
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.parser.markdown_parser import parse_markdown  # noqa: E402


def doc_id_for(path: Path, text: str) -> str:
    parsed = parse_markdown(text)
    return parsed.metadata.get("report_code") or path.stem


def main() -> int:
    cfg = load_config()
    exts = {e.lower() for e in cfg.knowledge_base.extensions}
    roots = [Path(r) for r in cfg.knowledge_base.roots]

    files: list[Path] = []
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$"):
                files.append(p)

    total = len(files)
    non_utf8: list[str] = []
    empty: list[str] = []
    oversized: list[dict] = []
    id_map: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    dir_counts: Counter = Counter()
    size_total = 0

    for p in files:
        rel_top = p.relative_to(roots[0]).parts[0] if len(p.relative_to(roots[0]).parts) > 1 else "."
        dir_counts[rel_top] += 1
        try:
            raw = p.read_bytes()
        except OSError as exc:
            non_utf8.append(f"{p} (read error: {exc})")
            continue
        size_total += len(raw)
        if len(raw) > 5_000_000:
            oversized.append({"path": str(p), "bytes": len(raw)})
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            non_utf8.append(f"{p} ({exc})")
            continue
        if not text.strip():
            empty.append(str(p))
            continue
        did = doc_id_for(p, text)
        if did in id_map:
            duplicates.setdefault(did, [id_map[did]]).append(str(p))
        else:
            id_map[did] = str(p)

    report = {
        "roots": [str(r) for r in roots],
        "total_md_files": total,
        "total_bytes": size_total,
        "unique_document_ids": len(id_map),
        "duplicate_document_ids": len(duplicates),
        "duplicate_files_involved": sum(len(v) for v in duplicates.values()),
        "non_utf8_files": len(non_utf8),
        "empty_files": len(empty),
        "oversized_files_gt5mb": oversized,
        "files_by_top_dir": dict(dir_counts.most_common()),
        "duplicates_detail": duplicates,
        "non_utf8_detail": non_utf8[:200],
        "empty_detail": empty[:100],
    }
    out = PROJECT_ROOT / "data" / "full_corpus_preflight.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if not k.endswith("_detail") and k != "files_by_top_dir"},
                     ensure_ascii=False, indent=2))
    print("files_by_top_dir:", json.dumps(report["files_by_top_dir"], ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
