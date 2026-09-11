# -*- coding: utf-8 -*-
"""P8-0：冻结 P7 基线（只读；产物一律写 E 盘；**不覆盖已发布的 P7 回归产物**）。

规范依据：`_meta/P8_开发建议与执行规范_v1.0.md` §4（P8-0）。
交接依据：`P8_新窗口交接说明_20260911.md` §7.1。

产出 `_golden/baseline_p7_20260911/`：
  full_corpus_regression.json          ← 现有 P7 发布副本（原样复制）
  full_corpus_regression_failures.json ← 现有 P7 发布副本（原样复制）
  config_snapshot.yaml                 ← D 盘 config.yaml 快照（权威生产配置）
  config_full_snapshot.yaml            ← D 盘 config.full.yaml 快照（历史/对照）
  index_status.json                    ← /api/index/status 原始响应（或直连等价计数）
  corpus_status.json                   ← 四方计数
  manifest_snapshot.json               ← documents 全表关键字段
  flagship_doc_ids.json                ← D 盘旗舰归档 doc_id 列表（隔离探针用）
  metrics_summary.md                   ← 参数 + 全指标 + Wilson 95% CI + 语料漂移说明
  README.md                            ← 只读/禁止覆盖标记 + 溯源 + 哈希

红线：只读 catalog 与 D 盘；只复制、不改写引擎与已发布回归产物。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

E = Path(r"E:\研报提取资料库")
ENGINE = Path(r"D:\AI-Knowledge-Engine")
BASELINE = E / "_golden" / "baseline_p7_20260911"
PUBLISHED = E / "_golden"
CATALOG = ENGINE / "data" / "catalog_full.db"
QDRANT = "http://127.0.0.1:16333"
CHUNKS_COL = "kb_chunks_full_v1"
SECTIONS_COL = "kb_sections_full_v1"
API = "http://127.0.0.1:8765/api/index/status"
CONFIGS = {"config_snapshot.yaml": ENGINE / "config" / "config.yaml",
           "config_full_snapshot.yaml": ENGINE / "config" / "config.full.yaml"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ro_conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{CATALOG.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def qdrant_count(col: str) -> int | None:
    try:
        req = urllib.request.Request(
            f"{QDRANT}/collections/{col}/points/count",
            data=json.dumps({"exact": True}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return int(json.loads(r.read())["result"]["count"])
    except Exception as exc:  # noqa: BLE001
        print(f"WARN qdrant count {col}: {exc}")
        return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% 置信区间。"""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (round((c - m) / d, 4), round((c + m) / d, 4))


def main() -> int:
    BASELINE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest: list[dict] = []

    # 1) 复制已发布 P7 回归产物（原样；绝不重跑覆盖）
    for name in ("full_corpus_regression.json", "full_corpus_regression_failures.json"):
        src, dst = PUBLISHED / name, BASELINE / name
        shutil.copy2(src, dst)
        manifest.append({"file": name, "sha256": sha256_file(dst), "bytes": dst.stat().st_size,
                         "source": str(src)})

    # 2) 配置快照 + 哈希
    cfg_hashes = {}
    for dst_name, src in CONFIGS.items():
        if src.exists():
            shutil.copy2(src, BASELINE / dst_name)
            h = sha256_file(src)
            cfg_hashes[dst_name] = {"source": str(src), "sha256": h}
            manifest.append({"file": dst_name, "sha256": h, "bytes": (BASELINE / dst_name).stat().st_size,
                             "source": str(src)})

    # 3) index_status：优先 API 原始响应，否则直连等价计数
    conn = ro_conn()
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    sections = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    fts_terms = conn.execute("SELECT COUNT(*) FROM chunks_fts_terms").fetchone()[0]
    fts_trigram = conn.execute("SELECT COUNT(*) FROM chunks_fts_trigram").fetchone()[0]

    status, status_src = None, "direct_sqlite+qdrant"
    try:
        with urllib.request.urlopen(API, timeout=8) as r:
            status = json.loads(r.read())
            status_src = "api:/api/index/status"
    except Exception as exc:  # noqa: BLE001
        print(f"WARN api status unavailable ({exc}); using direct counts")

    qpoints = qdrant_count(CHUNKS_COL)
    if status is None:
        counts = {"documents": docs, "sections": sections, "chunks": chunks,
                  "fts_terms": fts_terms, "fts_trigram": fts_trigram, "qdrant_points": qpoints}
        consistent = len({chunks, fts_terms, fts_trigram, qpoints}) == 1
        status = {"counts": counts, "consistent": consistent,
                  "_note": "backend 不可达，直连 SQLite/Qdrant 等价计数"}
    (BASELINE / "index_status.json").write_text(
        json.dumps({"captured_at": stamp, "source": status_src, "response": status},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    manifest.append({"file": "index_status.json", "source": status_src})

    cur = status.get("counts", {})
    corpus_status = {
        "captured_at": stamp,
        "documents": cur.get("documents", docs),
        "sections": cur.get("sections", sections),
        "chunks": cur.get("chunks", chunks),
        "fts_terms": cur.get("fts_terms", fts_terms),
        "fts_trigram": cur.get("fts_trigram", fts_trigram),
        "qdrant_points": cur.get("qdrant_points", qpoints),
        "consistent": cur.get("consistent", status.get("consistent")),
        "qdrant_chunks_collection": CHUNKS_COL,
        "qdrant_sections_collection": SECTIONS_COL,
        "catalog": str(CATALOG),
    }
    (BASELINE / "corpus_status.json").write_text(
        json.dumps(corpus_status, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) manifest 快照（documents 全表关键字段）
    rows = conn.execute(
        "SELECT id, source_path, sha256, domain, completed_at, file_size FROM documents ORDER BY id"
    ).fetchall()
    mf = [dict(r) for r in rows]
    (BASELINE / "manifest_snapshot.json").write_text(
        json.dumps({"captured_at": stamp, "count": len(mf), "documents": mf},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    manifest.append({"file": "manifest_snapshot.json", "count": len(mf)})

    # 5) 旗舰归档 doc_id（隔离探针用；以 source_path 前缀判定，稳健于 domain 缺省）
    flag = [r["id"] for r in rows if (r["source_path"] or "").lower().startswith("d:\\ai")]
    (BASELINE / "flagship_doc_ids.json").write_text(
        json.dumps({"captured_at": stamp,
                    "criterion": "source_path LIKE 'D:\\AI%'",
                    "count": len(flag), "doc_ids": flag}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    manifest.append({"file": "flagship_doc_ids.json", "count": len(flag)})

    # 6) metrics_summary.md（参数 + 全指标 + Wilson CI + 语料漂移）
    reg = json.loads((BASELINE / "full_corpus_regression.json").read_text(encoding="utf-8"))
    cfg = json.loads(pathlib_yaml(BASELINE / "config_snapshot.yaml"))
    ret = cfg.get("retrieval", {})
    fus = cfg.get("fusion", {})
    rr = cfg.get("reranker", {})
    emb = cfg.get("embedding", {})
    n = reg["summary_by_arm"]["hybrid_rerank"]["n"]
    lines = [
        "# P8-0 · P7 基线冻结（只读快照）", "",
        f"- 冻结时间：{stamp}",
        f"- 生成脚本：`pipeline/p8_freeze_baseline.py`",
        f"- 权威生产配置：`D:/AI-Knowledge-Engine/config/config.yaml`（sha256 `{cfg_hashes.get('config_snapshot.yaml', {}).get('sha256', '-')}`）",
        f"- 回归产物发布时间：{reg.get('generated_at')}",
        "",
        "## 1. 语料规模（重要：发布回归与当前存在漂移）",
        "",
        f"- **发布回归时**（`full_corpus_regression.json`）：documents **{reg['corpus']['documents']}** / chunks **{reg['corpus']['chunks']}**",
        f"- **本快照冻结时**：documents **{corpus_status['documents']}** / sections {corpus_status['sections']} / chunks **{corpus_status['chunks']}** / qdrant {corpus_status['qdrant_points']} / consistent={corpus_status['consistent']}",
        f"- 文档数漂移：**{corpus_status['documents'] - reg['corpus']['documents']:+d}**；chunk 数漂移：**{corpus_status['chunks'] - reg['corpus']['chunks']:+d}**",
        "- 漂移原因：P7 收尾后多次 backend 启动 reconcile 重解析了 `M04`/`M09`/`_最终报告`（其中 `_最终报告` 为新增 doc_id）；"
        "同批文件的两次重解析得到过不同的 chunk 数（如 M09 45→77），说明**引擎重解析存在非确定性**，已作为 P8 观察项记录。",
        "- **统计口径**：P7 发布回归 JSON 为冻结的**权威历史基线**，本目录不重跑、不覆盖；后续实验以同脚本在**当前**语料复跑并单列。",
        "",
        "## 2. 索引构成",
        "",
        f"- 旗舰归档（`source_path LIKE 'D:\\AI%'`）：**{len(flag)}** 篇",
        f"- E 盘研报语料：**{corpus_status['documents'] - len(flag)}** 篇",
        "",
        "## 3. 检索链路参数（生产配置快照）",
        "",
        "| 参数 | 值 |",
        "|---|---|",
        f"| dense_k | {ret.get('dense_k')} |",
        f"| fts_terms_k | {ret.get('fts_terms_k')} |",
        f"| fts_trigram_k | {ret.get('fts_trigram_k')} |",
        f"| fused_k | {ret.get('fused_k')} |",
        f"| rerank_k（**死配置，未被引擎使用**） | {ret.get('rerank_k')} |",
        f"| final_k | {ret.get('final_k')} |",
        f"| reranker.candidate_k（**实际重排截断**） | {rr.get('candidate_k')} |",
        f"| rrf_k | {fus.get('rrf_k')} |",
        f"| fusion weights (dense/terms/trigram) | {fus.get('dense_weight')} / {fus.get('terms_weight')} / {fus.get('trigram_weight')} |",
        f"| parent_boost | {fus.get('parent_boost')}（enabled={fus.get('parent_boost_enabled')}, sections_k={fus.get('parent_boost_sections_k')}） |",
        f"| embedding | {emb.get('model')} @ {emb.get('local_path')} |",
        f"| reranker | {rr.get('model')} |",
        "",
        "> **层深事实**：`SearchEngine.search` 只用 `fused_k=30` 截断，随后把整段交给 `RerankerService`；后者按 `reranker.candidate_k=24` 再次截断。故**融合名次 25–30 的金标没有任何重排机会**（对应报告 §6.1 的候选深度问题）。",
        "",
        "## 4. 各臂指标（发布回归，n=%d）" % n,
        "",
        "| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) | Hit@5 Wilson 95%CI |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, v in reg["summary_by_arm"].items():
        k = round(v["hit5"] * v["n"])
        lo, hi = wilson(k, v["n"])
        lines.append(
            f"| {arm} | {v['hit1']} | {v['hit3']} | {v['hit5']} | {v['mrr']} | {v['ndcg']} | "
            f"{v['p50_ms']} | {v['p95_ms']} | [{lo}, {hi}] |")
    lines += [
        "",
        "## 5. Gate 判定（发布）",
        "",
        "| 指标 | 实测 | 门线 | 判定 | Wilson 95%CI |",
        "|---|---|---|---|---|",
    ]
    for key, label in (("hit5", "hybrid_rerank Hit@5"), ("mrr", "MRR"), ("ndcg", "NDCG"),
                       ("exact_hit5", "exact Hit@5"), ("semantic_hit5", "semantic Hit@5")):
        g = reg["gate"][key]
        ok = "PASS" if g["value"] >= g["threshold"] else "FAIL"
        ci = ""
        if key in ("hit5", "exact_hit5", "semantic_hit5"):
            nn = n if key == "hit5" else reg["per_type_hybrid_rerank"].get("exact" if key == "exact_hit5" else "semantic", {}).get("n", 0)
            lo, hi = wilson(round(g["value"] * nn), nn)
            ci = f"[{lo}, {hi}] (n={nn})"
        lines.append(f"| {label} | {g['value']} | {g['threshold']} | **{ok}** | {ci} |")
    lines += [
        "",
        f"**gate_pass = {reg['gate_pass']}**",
        "",
        "## 6. 失败构成（发布）",
        "",
        f"- 失败题数：{len(reg['failures'])} / {n}",
        "- 分型：" + json.dumps(
            {b: sum(1 for f in reg["failures"] if f["bucket"] == b)
             for b in sorted({f["bucket"] for f in reg["failures"]})}, ensure_ascii=False),
        "- 明细见 `full_corpus_regression_failures.json`",
        "",
        "## 7. 只读与禁止覆盖",
        "",
        "本目录为 P8-0 基线冻结快照，**禁止覆盖**。任何实验产物写 `_golden/p8_experiments/`。",
    ]
    (BASELINE / "metrics_summary.md").write_text("\n".join(lines), encoding="utf-8")
    manifest.append({"file": "metrics_summary.md"})

    # 7) README + manifest
    (BASELINE / "README.md").write_text(
        "# baseline_p7_20260911（P8-0 冻结基线）\n\n"
        f"冻结时间：{stamp}\n\n"
        "**只读 / 禁止覆盖**。本目录冻结 P7 收尾时的检索质量基线，供 P8 全部实验作对照。\n\n"
        "权威生产配置为 `D:/AI-Knowledge-Engine/config/config.yaml`；"
        "`config.full.yaml` 为历史/对照快照（roots 仅含 D 盘归档、qdrant 端口 6333，**非生产**）。\n\n"
        "语料漂移：发布回归为 3,565 篇 / 296,341 chunk；当前为 3,566 / 296,385（见 metrics_summary.md §1）。\n\n"
        "复现：`D:\\AI-Knowledge-Engine\\.venv\\Scripts\\python.exe pipeline\\p8_freeze_baseline.py`\n",
        encoding="utf-8")
    (BASELINE / "FREEZE_MANIFEST.json").write_text(
        json.dumps({"frozen_at": stamp, "generator": "pipeline/p8_freeze_baseline.py",
                    "read_only": True, "config_hashes": cfg_hashes,
                    "corpus_status": corpus_status, "artifacts": manifest},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    print(json.dumps({"baseline": str(BASELINE), "documents": corpus_status["documents"],
                      "chunks": corpus_status["chunks"], "flagship_docs": len(flag),
                      "config_sha256": {k: v["sha256"][:16] for k, v in cfg_hashes.items()}},
                     ensure_ascii=False, indent=2))
    return 0


def pathlib_yaml(p: Path) -> str:
    """转成 json（yaml 是 json 超集，配置无非标量键）。"""
    import yaml
    return json.dumps(yaml.safe_load(p.read_text(encoding="utf-8")))


if __name__ == "__main__":
    raise SystemExit(main())
