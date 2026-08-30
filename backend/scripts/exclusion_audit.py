"""I7 P1-3：Full Corpus Exclusion Audit。

对 D:/AI深度报告归档 全量文件按 docid_policy.exclusion_reason 重新分类统计，
并对每个 reason 随机抽查样本，确认排除主要属于旧版本/重复版本/非终版/中间产物，
判定是否存在"唯一资料被系统性误排除"。

只读扫描，不写入认知/不修改收录决策（ADR-013 v2 仅终版 不变）。
输出：data/exclusion_audit_{stats,sample}.json + stdout 摘要。
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.indexing.docid_policy import exclusion_reason  # noqa: E402

REASONS = ["EXCLUDED_DIR", "EXCLUDED_NON_FINAL", "EXCLUDED_PROCESS", "EXCLUDED_DUPLICATE"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    cfg = load_config()
    root = Path(cfg.knowledge_base.roots[0])
    exts = set(cfg.knowledge_base.extensions)
    random.seed(20260830)

    print(f"scanning {root} ...")
    buckets: dict[str, list[dict]] = defaultdict(list)  # reason -> [{path, full}]
    sha_to_paths: dict[str, list[str]] = defaultdict(list)
    total = 0
    for p in root.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$")):
            continue
        total += 1
        r = exclusion_reason(str(p))
        if r is None:
            continue
        buckets[r].append({"path": str(p), "full": None})
        if r == "EXCLUDED_DUPLICATE":
            continue  # DUP 需 sha 判定，单独计算
    print(f"total_md_scanned={total}")

    # DUPLICATE：非 DIR/PROCESS/NON_FINAL（即被判定为候选终版）却与前序文件 sha 相同的副本
    # 先收集未被上述三类排除、属于收录面之外的文件进行 sha 归类。
    # 本审计用"同 sha 出现多次（跨文件）"作为 duplicate 近似，对齐 stats 口径（EXCLUDED_DUPLICATE=27）。
    cand = [d["path"] for d in buckets["EXCLUDED_NON_FINAL"][:]]  # NON_FINAL 多为候选终版，这也可能重复
    # 对 DIR/PROCESS/NON_FINAL 三桶之外的 file 不算；我们仅对已排除对象内的重复做复证，避免重做收录决策。
    # DUP 明细以 stats.json（EXCLUDED_DUPLICATE=27）为准，这里复现抽样组。
    dup_probe = _find_dup_sample(root, exts)
    print(f"duplicate_probe_groups={len(dup_probe)}")

    stats = {
        "scanned_root": str(root),
        "total_md_scanned": total,
        "excluded_count": sum(len(b) for b in buckets.values()),
        "by_reason": {k: len(buckets[k]) for k in REASONS},
        "reason_percentage": {
            k: round(len(buckets[k]) / max(sum(len(b) for b in buckets.values()), 1) * 100, 2)
            for k in REASONS
        },
        "dup_probe_groups": len(dup_probe),
        "dup_probe_examples": [{"sha": g["sha"], "n": g["n"], "paths": g["paths"][:4]}
                               for g in dup_probe[:10]],
    }

    # ---- 抽样（每 reason 若干，供人工核对） ----
    samples: dict[str, list] = {}
    slice_map = {"EXCLUDED_DIR": 40, "EXCLUDED_NON_FINAL": 20, "EXCLUDED_PROCESS": 20}
    for k, n_slice in slice_map.items():
        lst = buckets[k]
        pick = random.sample(lst, min(n_slice, len(lst)))
        samples[k] = [p["path"] for p in pick]
    samples["EXCLUDED_DUPLICATE"] = [g["paths"][0] for g in dup_probe[:10]]

    (PROJECT_ROOT / "data" / "exclusion_audit_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (PROJECT_ROOT / "data" / "exclusion_audit_sample.json").write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== Exclusion Audit ====")
    print(f"excluded_count = {stats['excluded_count']}")
    for k in REASONS:
        print(f"  {k:18s} n={len(buckets[k]):5d}  pct={stats['reason_percentage'][k]:5.2f}%")
    print("sample (first 12 each):")
    for k, v in samples.items():
        print(f"  [{k}] n_slice={len(v)}")
        for p in v[:12]:
            print(f"      {p}")
    return 0


def _find_dup_sample(root: Path, exts: set):
    seen: dict[str, list[str]] = {}
    for p in root.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$")):
            continue
        try:
            s = sha256_file(p)
        except OSError:
            continue
        seen.setdefault(s, []).append(str(p))
    groups = [{"sha": s, "n": len(ps), "paths": ps} for s, ps in seen.items() if len(ps) > 1]
    groups.sort(key=lambda g: g["n"], reverse=True)
    return groups


if __name__ == "__main__":
    raise SystemExit(main())