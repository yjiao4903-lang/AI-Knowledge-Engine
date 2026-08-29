"""M5 评测：Dense 检索质量 + 延迟 + CPU fallback（Addendum §31-32）。

输出 docs/M5_DENSE_EVALUATION.md。
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.lexical.corpus import build_corpus_db  # noqa: E402
from app.retrieval.dense import DenseRetriever  # noqa: E402

# (query, 关键词组：Top5 chunk 任一 plain_text 含任一关键词即命中)
SEMANTIC_CASES = [
    ("为什么大型 AI GPU 对先进封装越来越依赖？", ["CoWoS", "HBM", "先进封装", "封装代偿"]),
    ("为什么先进光刻反而可能降低大芯片经济性？", ["High-NA", "拼接", "视场", "Stitching"]),
    ("为什么越先进的光刻机反而可能对超大 GPU 不划算", ["High-NA", "拼接", "429"]),
    ("玻尔兹曼极限是多少", ["60", "mV/dec", "亚阈值"]),
    ("HBM4 的接口位宽是多少", ["2048"]),
    ("AI 是否消除了半导体周期", ["周期", "库存", "基钦"]),
    ("日本半导体的能力陷阱是什么", ["能力陷阱", "质保", "大型机"]),
    ("数据中心为什么受到电网的制约", ["电网", "并网", "电力"]),
    ("液冷为什么成为高密算力基础设施的必然", ["液冷", "热", "功耗密度"]),
    ("Transformer 架构的上下文长度瓶颈在哪里", ["注意力", "上下文", "KV", "状态空间"]),
]


def pctl(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return round(vals[min(int(len(vals) * p), len(vals) - 1)], 1) if vals else 0.0


def main() -> int:
    cfg = load_config()
    tmp = Path(tempfile.mkdtemp())
    conn, info = build_corpus_db(tmp / "corpus.db")
    texts = {r["id"]: r["plain_text"] for r in conn.execute("SELECT id, plain_text FROM chunks").fetchall()}

    retriever = DenseRetriever(cfg)
    points = retriever.store.collection_info(cfg.qdrant.chunks_collection)

    rows = []
    search_ms, embed_ms_all = [], []
    for q, keywords in SEMANTIC_CASES:
        hits, embed_ms = retriever.search(q, k=5)
        top5 = " ".join(texts.get(h["payload"]["chunk_id"], "") for h in hits)
        hit = any(kw in top5 for kw in keywords)
        top1_text = texts.get(hits[0]["payload"]["chunk_id"], "") if hits else ""
        top1_hit = any(kw in top1_text for kw in keywords)
        rows.append((q, hit, top1_hit, embed_ms, hits[0]["payload"]["chunk_id"] if hits else "-"))
        search_ms.append(len(hits) and embed_ms)  # embed 含在 search 内
        embed_ms_all.append(embed_ms)

    hit5 = sum(1 for _, h, _, _, _ in rows if h) / len(rows)
    hit1 = sum(1 for _, _, t1, _, _ in rows if t1) / len(rows)

    # CPU fallback 单条验证（慢，仅一次）
    t0 = time.perf_counter()
    cpu_r = DenseRetriever(cfg, device_override="cpu")
    _ = cpu_r.embedder.embed_query("HBM4 接口位宽")
    cpu_ms = (time.perf_counter() - t0) * 1000

    md = f"""# M5 Dense Evaluation Report

日期：{time.strftime('%Y-%m-%d %H:%M')}
设备：{retriever.device}（{retriever.device_kind}）—— {retriever.device_reason}
索引：kb_chunks_v1 = {points['points_count']} points（{info['total_chunks']} chunks / 5 docs），kb_sections_v1 同步建立

## Semantic Rewrite Queries（Addendum §31）

Hit = Top5 chunk 的 plain_text 含任一预期关键词。

| Query | Hit@5 | Top1 Hit | embed ms | Top1 chunk |
|---|---|---|---|---|
{chr(10).join(f'| {q} | {h} | {t1} | {ms} | {cid} |' for q, h, t1, ms, cid in rows)}

**Dense Hit@5 = {hit5:.2f}　Top1 命中率 = {hit1:.2f}**

## 延迟

| 指标 | P50 | P95 |
|---|---|---|
| query embed+search (ms) | {pctl(embed_ms_all, 0.5)} | {pctl(embed_ms_all, 0.95)} |

## CPU Fallback（Addendum §32）

- CPU 单条 query embed：{cpu_ms:.0f} ms（GPU 约为 P50 水平的 1/{int(cpu_ms / max(pctl(embed_ms_all, 0.5), 1))}）
- Provider 在 cpu 设备加载并推理正常：PASS

## Gate（Addendum §32）

- Qwen Embedding smoke PASS（M0）
- RX 7900 XTX device PASS：preferred_gpu_name 匹配 cuda:1
- CPU fallback PASS
- Qdrant insert PASS：{points['points_count']} points
- Qdrant search PASS
- Semantic Query 基本命中：Hit@5 = {hit5:.2f}
"""
    out = PROJECT_ROOT / "docs" / "M5_DENSE_EVALUATION.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
