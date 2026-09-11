# -*- coding: utf-8 -*-
"""P8-2 检索逐层追踪 / 仪器化（只读；不改引擎；产物写 E 盘 `_golden/p8_experiments/`）。

规范依据：`_meta/P8_开发建议与执行规范_v1.0.md` §6（P8-2）、§8、§9。
交接依据：`P8_新窗口交接说明_20260911.md` §7.3。

能力
----
1. 逐题输出每一层 gold 名次：
   dense/terms/trigram 名次 -> fused 名次 -> rerank 输入位次/输出名次 -> final 名次
2. 新增 candidate recall 指标：
   Dense Recall@50 / Lexical Recall@50 / Union Recall@50 / Fusion Recall@30,50 / Rerank Recall@10
3. 金标匹配双模式：
   - legacy：`relevant_sections[{document_id, heading_contains, grade}]`（heading LIKE，兼容旧 50 题）
   - 新题集：`gold.chunks[{chunk_id, grade}]` 或 `gold.content_anchors[{document_id, anchor_contains, grade}]`
4. 7 臂指标自校验：与已发布回归逐臂比对（默认阈值 ±0.02）
5. 语料隔离探针：`--filters all|flagship|<json>`，无需重建索引

用法
----
  python pipeline/p8_trace.py --exp p7_baseline_20260911
  python pipeline/p8_trace.py --exp flagship_isolation --filters flagship
  python pipeline/p8_trace.py --exp smoke --limit 3 --no-rerank

红线：不写 D 盘；不修改引擎；不覆盖 `_golden/baseline_p7_20260911/`。
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

E = Path(r"E:\研报提取资料库")
ENGINE = Path(r"D:\AI-Knowledge-Engine")
OUT_ROOT = E / "_golden" / "p8_experiments"
LEGACY = E / "_golden" / "benchmark" / "legacy_v1" / "golden_queries.jsonl"
PUBLISHED = E / "_golden" / "full_corpus_regression.json"
FLAGSHIP = E / "_golden" / "baseline_p7_20260911" / "flagship_doc_ids.json"
CATALOG = ENGINE / "data" / "catalog_full.db"

sys.path.insert(0, str(ENGINE / "backend"))
sys.path.insert(0, str(ENGINE / "backend" / "scripts"))

from app.retrieval.fusion import weighted_rrf  # noqa: E402

ARMS = ("terms", "trigram", "lexical", "dense", "hybrid", "hybrid_boost", "hybrid_rerank")


# ---------------------------------------------------------------- 基础设施
def ro_conn() -> sqlite3.Connection:
    """只读打开 catalog，避免 WAL 写入（不干扰 backend）。"""
    c = sqlite3.connect(f"file:{CATALOG.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def pctl(vals, p):
    vals = sorted(vals)
    return round(vals[min(int(len(vals) * p), len(vals) - 1)], 1) if vals else 0.0


def first_rank(ids, grade_fn):
    for i, cid in enumerate(ids, 1):
        if grade_fn(cid) >= 2:
            return i
    return None


def section_hits(section_id, rel_sections):
    return any(section_id == s or section_id.startswith(s + ":") for s in rel_sections)


def section_recall(ids, k, rel_sections, section_of):
    total = len(rel_sections)
    if total == 0:
        return 0.0
    found = set()
    for cid in ids[:k]:
        sid = section_of.get(cid)
        if sid and section_hits(sid, rel_sections):
            for s in rel_sections:
                if sid == s or sid.startswith(s + ":"):
                    found.add(s)
    return len(found) / total


def chunk_recall(ids, k, rel_chunks):
    """chunk 级 recall（新题集用；rel_chunks=grade>=2 的 chunk_id 集合）。"""
    total = len(rel_chunks)
    if total == 0:
        return 0.0
    return len({c for c in ids[:k] if c in rel_chunks}) / total


# ---------------------------------------------------------------- 金标解析
class Gold:
    """统一金标：section 级（legacy）与 chunk 级（新题集）兼容。"""

    def __init__(self, sections, chunk_grades, mode):
        self.sections = sections                  # [(section_id, grade)]
        self.chunk_grades = chunk_grades          # {chunk_id: grade}
        self.mode = mode
        self.rel_sections = {s for s, g in sections if g >= 2}
        self.rel_chunks = {c for c, g in chunk_grades.items() if g >= 2}

    def grade(self, chunk_id, section_of):
        g = self.chunk_grades.get(chunk_id, 0)
        sid = section_of.get(chunk_id)
        if sid:
            sg = max((gr for s, gr in self.sections
                      if sid == s or sid.startswith(s + ":")), default=0)
            g = max(g, sg)
        return g

    @property
    def has_sections(self):
        return bool(self.rel_sections)

    @property
    def has_chunks(self):
        return bool(self.rel_chunks)


def resolve_legacy(conn, relevant):
    out = []
    for it in relevant:
        rows = conn.execute(
            "SELECT id FROM sections WHERE document_id = ? AND (heading LIKE ? OR heading_path LIKE ?)",
            (it["document_id"], f"%{it['heading_contains']}%", f"%{it['heading_contains']}%"),
        ).fetchall()
        for r in rows:
            out.append((r["id"], it["grade"]))
    return out, {}, "heading_contains"


def resolve_new(conn, gold):
    """gold.chunks（首选）或 gold.content_anchors（次选）。"""
    chunk_grades = {}
    sections = []
    mode = "chunk_ids"
    for it in gold.get("chunks", []) or []:
        cid = it["chunk_id"]
        chunk_grades[cid] = max(chunk_grades.get(cid, 0), it["grade"])
        sid = conn.execute("SELECT section_id FROM chunks WHERE id=?", (cid,)).fetchone()
        if sid:
            sections.append((sid["section_id"], it["grade"]))
    if not gold.get("chunks"):
        mode = "content_anchors"
        for it in gold.get("content_anchors", []) or []:
            rows = conn.execute(
                "SELECT id, section_id FROM chunks WHERE document_id=? AND plain_text LIKE ?",
                (it["document_id"], f"%{it['anchor_contains']}%"),
            ).fetchall()
            for r in rows:
                chunk_grades[r["id"]] = max(chunk_grades.get(r["id"], 0), it["grade"])
                sections.append((r["section_id"], it["grade"]))
    return sections, chunk_grades, mode


def load_questions(path: Path, split: str) -> list[dict]:
    qs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in qs:
        q.setdefault("split", split)
    return qs


# ---------------------------------------------------------------- 检索复现
def fetch_rows(conn, chunk_ids):
    if not chunk_ids:
        return {}
    marks = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT c.id, c.document_id, c.section_id, c.heading_path, c.content_type, "
        f"c.evidence_level, c.plain_text, c.start_line, c.end_line, d.title "
        f"FROM chunks c LEFT JOIN documents d ON d.id = c.document_id "
        f"WHERE c.id IN ({marks})",
        chunk_ids,
    ).fetchall()
    return {r["id"]: r for r in rows}


def allowed_ids(conn, filters):
    if not filters:
        return None
    clauses, params = [], []
    if filters.get("document_ids"):
        clauses.append(f"document_id IN ({','.join('?' * len(filters['document_ids']))})")
        params += list(filters["document_ids"])
    if filters.get("domains"):
        clauses.append(f"document_id IN (SELECT id FROM documents WHERE domain IN ({','.join('?' * len(filters['domains']))}))")
        params += list(filters["domains"])
    if filters.get("content_types"):
        clauses.append(f"content_type IN ({','.join('?' * len(filters['content_types']))})")
        params += list(filters["content_types"])
    if filters.get("evidence_levels"):
        clauses.append(f"evidence_level IN ({','.join('?' * len(filters['evidence_levels']))})")
        params += list(filters["evidence_levels"])
    if filters.get("date_from"):
        clauses.append("document_id IN (SELECT id FROM documents WHERE completed_at >= ?)")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("document_id IN (SELECT id FROM documents WHERE completed_at <= ?)")
        params.append(filters["date_to"])
    if not clauses:
        return None
    return {r["id"] for r in conn.execute(f"SELECT id FROM chunks WHERE {' AND '.join(clauses)}", params)}


def fuse(lists, cfg, boost_prefixes=None):
    """复现块：weighted_rrf -> section boost -> 候选稳定排序 -> 未截断名次列表。

    与 `SearchEngine.search` 的 candidate 插入顺序/稳定排序保持一致。
    """
    fused = weighted_rrf(lists, rrf_k=cfg.fusion.rrf_k, weights={
        "dense": cfg.fusion.dense_weight,
        "terms": cfg.fusion.terms_weight,
        "trigram": cfg.fusion.trigram_weight,
    })
    score_map = {cid: sc for cid, sc, _ in fused}
    cand_order, seen = [], set()
    for cid in lists.get("dense", []) + lists.get("terms", []) + lists.get("trigram", []) + [c for c, _, _ in fused]:
        if cid not in seen:
            seen.add(cid)
            cand_order.append(cid)
    final = {}
    for cid in cand_order:
        boost = 1.0
        if boost_prefixes and any(cid.startswith(p) for p in boost_prefixes):
            boost = cfg.fusion.parent_boost
        final[cid] = score_map.get(cid, 0.0) * boost
    return sorted(cand_order, key=lambda c: final[c], reverse=True), score_map


def p8_bucket(trace, fused_k):
    """P8 失败归因（规范 §26）：NO_RECALL / FUSION / RERANK_DEPTH / RERANK / OTHER。"""
    if trace["final_rank"] and trace["final_rank"] <= 5:
        return "OK"
    if not trace["in_union50"]:
        return "NO_RECALL"
    if trace["fused_rank"] is None or trace["fused_rank"] > fused_k:
        return "FUSION"
    if trace["rerank_input_pos"] is None:
        return "RERANK_DEPTH"    # 进了 fused_k 但被 candidate_k 截断，没有重排机会
    return "RERANK"


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="实验 id（目录名）")
    ap.add_argument("--questions", default=str(LEGACY))
    ap.add_argument("--split", default="legacy")
    ap.add_argument("--filters", default="all", help="all | flagship | JSON 文件/内联")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-rerank", action="store_true", help="跳过重排（快速冒烟）")
    ap.add_argument("--published", default=str(PUBLISHED), help="自校验对照的已发布回归 JSON")
    ap.add_argument("--tolerance", type=float, default=0.02)
    # 配置覆盖（P8-3 实验用；运行时生效，不写 D 盘配置）
    ap.add_argument("--dense_k", type=int), ap.add_argument("--terms_k", type=int)
    ap.add_argument("--trigram_k", type=int), ap.add_argument("--fused_k", type=int)
    ap.add_argument("--candidate_k", type=int, help="覆盖 reranker.candidate_k（真正的重排截断）")
    ap.add_argument("--final_k", type=int)
    ap.add_argument("--w_dense", type=float), ap.add_argument("--w_terms", type=float)
    ap.add_argument("--w_trigram", type=float)
    ap.add_argument("--boost", choices=["on", "off"], default="default")
    args = ap.parse_args()

    from app.core.config import load_config
    from app.inference.manager import InferenceManager
    from app.lexical.fts_search import LexicalSearcher
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.rerank import RerankerService

    cfg = load_config()
    overrides = {}
    if args.dense_k: cfg.retrieval.dense_k = args.dense_k; overrides["dense_k"] = args.dense_k
    if args.terms_k: cfg.retrieval.fts_terms_k = args.terms_k; overrides["fts_terms_k"] = args.terms_k
    if args.trigram_k: cfg.retrieval.fts_trigram_k = args.trigram_k; overrides["fts_trigram_k"] = args.trigram_k
    if args.fused_k: cfg.retrieval.fused_k = args.fused_k; overrides["fused_k"] = args.fused_k
    if args.candidate_k: cfg.reranker.candidate_k = args.candidate_k; overrides["reranker_candidate_k"] = args.candidate_k
    if args.final_k: cfg.retrieval.final_k = args.final_k; overrides["final_k"] = args.final_k
    if args.w_dense is not None: cfg.fusion.dense_weight = args.w_dense; overrides["dense_weight"] = args.w_dense
    if args.w_terms is not None: cfg.fusion.terms_weight = args.w_terms; overrides["terms_weight"] = args.w_terms
    if args.w_trigram is not None: cfg.fusion.trigram_weight = args.w_trigram; overrides["trigram_weight"] = args.w_trigram
    if args.boost != "default":
        cfg.fusion.parent_boost_enabled = (args.boost == "on"); overrides["parent_boost_enabled"] = args.boost == "on"
    if overrides:
        (E / "p8_configs").mkdir(parents=True, exist_ok=True)
        (E / "p8_configs" / f"{args.exp}.yaml").write_text(json.dumps(
            {"exp_id": args.exp, "overrides": overrides,
             "retrieval": {"dense_k": cfg.retrieval.dense_k, "fts_terms_k": cfg.retrieval.fts_terms_k,
                           "fts_trigram_k": cfg.retrieval.fts_trigram_k, "fused_k": cfg.retrieval.fused_k,
                           "final_k": cfg.retrieval.final_k},
             "reranker": {"candidate_k": cfg.reranker.candidate_k},
             "fusion": {"rrf_k": cfg.fusion.rrf_k, "dense_weight": cfg.fusion.dense_weight,
                        "terms_weight": cfg.fusion.terms_weight, "trigram_weight": cfg.fusion.trigram_weight,
                        "parent_boost_enabled": cfg.fusion.parent_boost_enabled}},
            ensure_ascii=False, indent=2), encoding="utf-8")
    conn = ro_conn()
    section_of = {r["id"]: r["section_id"] for r in conn.execute("SELECT id, section_id FROM chunks")}

    # filters 解析
    if args.filters == "all":
        filters = None
    elif args.filters == "flagship":
        ids = json.loads(FLAGSHIP.read_text(encoding="utf-8"))["doc_ids"]
        filters = {"document_ids": ids}
    else:
        raw = Path(args.filters).read_text(encoding="utf-8") if Path(args.filters).exists() else args.filters
        obj = json.loads(raw)
        filters = obj if isinstance(obj, dict) else {"document_ids": obj}
    allowed = allowed_ids(conn, filters)

    questions = load_questions(Path(args.questions), args.split)
    if args.limit:
        questions = questions[: args.limit]

    # 金标解析
    golds, unresolved = {}, []
    for q in questions:
        if "relevant_sections" in q:
            secs, cg, mode = resolve_legacy(conn, q["relevant_sections"])
        else:
            secs, cg, mode = resolve_new(conn, q.get("gold", {}))
        g = Gold(secs, cg, mode)
        if not g.rel_sections and not g.rel_chunks:
            unresolved.append(q["id"])
        golds[q["id"]] = g

    print(f"questions={len(questions)} unresolved={len(unresolved)} filters={args.filters} "
          f"allowed_chunks={len(allowed) if allowed is not None else 'ALL'}")
    if unresolved:
        print(f"WARNING unresolved gold（按发布口径跳过，不计分）: {unresolved}")
    questions = [q for q in questions if golds[q["id"]].rel_sections or golds[q["id"]].rel_chunks]
    if not questions:
        print("ERROR: 无有效题（全部 unresolved）")
        return 2

    dense = DenseRetriever(cfg)
    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    lexical = LexicalSearcher(conn)

    traces, arm_metrics = [], {a: [] for a in ARMS}
    lat = {a: [] for a in ARMS}
    t_start = time.perf_counter()

    for n, q in enumerate(questions, 1):
        g = golds[q["id"]]
        gfn = lambda cid: g.grade(cid, section_of)  # noqa: E731
        t0 = time.perf_counter()

        dense_hits, embed_ms = dense.search(q["query"], k=cfg.retrieval.dense_k, filters=filters,
                                            collection=cfg.qdrant.chunks_collection)
        t1 = time.perf_counter()
        terms_hits = lexical.search_terms(q["query"], k=cfg.retrieval.fts_terms_k, filters=filters)
        t2 = time.perf_counter()
        trigram_hits = lexical.search_trigram(q["query"], k=cfg.retrieval.fts_trigram_k, filters=filters)
        t3 = time.perf_counter()
        lists = {
            "dense": [h["payload"]["chunk_id"] for h in dense_hits],
            "terms": [h.chunk_id for h in terms_hits],
            "trigram": [h.chunk_id for h in trigram_hits],
        }

        # section parent boost（复现引擎：不携带 filters）
        boost_prefixes = None
        if cfg.fusion.parent_boost_enabled:
            sec_hits, _ = dense.search(q["query"], k=cfg.fusion.parent_boost_sections_k,
                                       collection=cfg.qdrant.sections_collection)
            boost_prefixes = {f"{h['payload']['document_id']}:{h['payload']['section_id']}:" for h in sec_hits}

        fused_all, _ = fuse(lists, cfg, boost_prefixes)
        fused_nb, _ = fuse(lists, cfg, None)          # hybrid（无 boost）对照臂
        if allowed is not None:
            fused_all = [c for c in fused_all if c in allowed]
            fused_nb = [c for c in fused_nb if c in allowed]

        fused_k = cfg.retrieval.fused_k
        fused_top = fused_all[:fused_k]
        fused50 = fused_all[:50]
        union50 = list(dict.fromkeys(lists["dense"] + lists["terms"] + lists["trigram"]))

        # 重排（复现引擎：整段 fused_top 交给 RerankerService，内部按 candidate_k 截断）
        final_order = list(fused_top)
        reranked = []
        if not args.no_rerank and fused_top:
            t4 = time.perf_counter()
            rows = fetch_rows(conn, fused_top)
            cands = [{"chunk_id": c, "title": rows[c]["title"], "heading_path": rows[c]["heading_path"],
                      "content_type": rows[c]["content_type"], "evidence_level": rows[c]["evidence_level"],
                      "plain_text": rows[c]["plain_text"]} for c in fused_top if c in rows]
            reranked = reranker.rerank(q["query"], cands)
            sb = {x["chunk_id"]: x["reranker_score"] for x in reranked}
            final_order = sorted(fused_top, key=lambda c: sb.get(c, float("-inf")), reverse=True)
            lat["hybrid_rerank"].append(round((time.perf_counter() - t4) * 1000, 2))
        final10 = final_order[: cfg.retrieval.final_k]

        # 逐层名次
        tr = {
            "id": q["id"], "type": q.get("type") or q.get("query_type"), "query": q["query"],
            "gold_mode": g.mode,
            "n_rel_sections": len(g.rel_sections), "n_rel_chunks": len(g.rel_chunks),
            "dense_rank": first_rank(lists["dense"], gfn),
            "terms_rank": first_rank(lists["terms"], gfn),
            "trigram_rank": first_rank(lists["trigram"], gfn),
            "in_dense50": first_rank(lists["dense"], gfn) is not None,
            "in_terms50": first_rank(lists["terms"], gfn) is not None,
            "in_trigram30": first_rank(lists["trigram"], gfn) is not None,
            "in_union50": first_rank(union50, gfn) is not None,
            "union50_rank": first_rank(union50, gfn),
            "fused_rank": first_rank(fused_all, gfn),
            "in_fused30": first_rank(fused_top, gfn) is not None,
            "in_fused50": first_rank(fused50, gfn) is not None,
            "rerank_input_pos": (first_rank(fused_top[: cfg.reranker.candidate_k], gfn)
                                 if not args.no_rerank else None),
            "reranked_rank": (first_rank([x["chunk_id"] for x in reranked], gfn) if reranked else None),
            "final_rank": first_rank(final10, gfn),
            "recall": {
                "dense@50": round(section_recall(lists["dense"], 50, g.rel_sections, section_of), 3),
                "lexical@50": round(section_recall(list(dict.fromkeys(lists["terms"] + lists["trigram"])), 50,
                                                   g.rel_sections, section_of), 3),
                "union@50": round(section_recall(union50, 50, g.rel_sections, section_of), 3),
                "fusion@30": round(section_recall(fused_all, 30, g.rel_sections, section_of), 3),
                "fusion@50": round(section_recall(fused_all, 50, g.rel_sections, section_of), 3),
                "rerank@10": round(section_recall(final10, 10, g.rel_sections, section_of), 3),
            },
            "arm_hit5": {},
            "bucket": None,
        }
        if g.rel_chunks:
            tr["recall"]["chunk_union@50"] = round(chunk_recall(union50, 50, g.rel_chunks), 3)
        tr["bucket"] = p8_bucket(tr, fused_k)

        # 7 臂指标（用与发布回归一致的口径：m9.metrics_for）
        arm_ids = {
            "terms": lists["terms"][:10],
            "trigram": lists["trigram"][:10],
            "lexical": fuse({"terms": lists["terms"], "trigram": lists["trigram"]}, cfg)[0][:10],
            "dense": lists["dense"][:10],
            "hybrid": fused_nb[:fused_k][:10],
            "hybrid_boost": fused_top[:10],
            "hybrid_rerank": final10,
        }
        for arm in ARMS:
            m = metrics_for(arm_ids[arm], g, section_of)
            arm_metrics[arm].append(m)
            tr["arm_hit5"][arm] = m["hit5"]
            if arm != "hybrid_rerank":
                lat[arm].append(round((t1 - t0) * 1000, 2) if arm == "dense" else
                                (round((t3 - t1) * 1000, 2) if arm in ("terms", "trigram", "lexical") else
                                 round((t3 - t0) * 1000, 2)))

        tr["_latency_total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        traces.append(tr)
        if n % 10 == 0 or n == len(questions):
            print(f"  [{n}/{len(questions)}] {q['id']} final={tr['final_rank']} bucket={tr['bucket']}")

    # 汇总
    n = len(traces)
    def agg(arm):
        ms = arm_metrics[arm]
        if not ms:
            return {}
        return {
            "n": len(ms),
            "hit1": round(sum(m["hit1"] for m in ms) / len(ms), 3),
            "hit3": round(sum(m["hit3"] for m in ms) / len(ms), 3),
            "hit5": round(sum(m["hit5"] for m in ms) / len(ms), 3),
            "recall5": round(sum(m["recall5"] for m in ms) / len(ms), 3),
            "recall10": round(sum(m["recall10"] for m in ms) / len(ms), 3),
            "mrr": round(sum(m["mrr"] for m in ms) / len(ms), 3),
            "ndcg": round(sum(m["ndcg"] for m in ms) / len(ms), 3),
            "p50_ms": pctl(lat[arm], 0.5), "p95_ms": pctl(lat[arm], 0.95),
        }
    summary = {a: agg(a) for a in ARMS}

    def avg(key):
        vals = [t["recall"][key] for t in traces if key in t["recall"]]
        return round(sum(vals) / len(vals), 3) if vals else None
    cand_recall = {k: avg(k) for k in ("dense@50", "lexical@50", "union@50",
                                       "fusion@30", "fusion@50", "rerank@10", "chunk_union@50")}

    def presence(key):
        vals = [bool(t[key]) for t in traces]
        return round(sum(vals) / len(vals), 3) if vals else None
    presence_summary = {
        "dense50": presence("in_dense50"), "terms50": presence("in_terms50"),
        "trigram30": presence("in_trigram30"), "union50": presence("in_union50"),
        "fusion30": presence("in_fused30"), "fusion50": presence("in_fused50"),
        "rerank24": round(sum(1 for t in traces if t["rerank_input_pos"] is not None) / n, 3) if n else None,
        "final_hit5": round(sum(1 for t in traces if t["final_rank"] and t["final_rank"] <= 5) / n, 3) if n else None,
    }
    buckets = {}
    for t in traces:
        buckets[t["bucket"]] = buckets.get(t["bucket"], 0) + 1

    # 自校验 vs 已发布
    self_check = {"tolerance": args.tolerance, "source": str(args.published), "arms": {}}
    if Path(args.published).exists():
        pub = json.loads(Path(args.published).read_text(encoding="utf-8"))["summary_by_arm"]
        for arm in ARMS:
            if arm not in pub or not summary.get(arm):
                continue
            d = {k: round(summary[arm][k] - pub[arm][k], 3) for k in ("hit1", "hit3", "hit5", "mrr", "ndcg")}
            ok = all(abs(v) <= args.tolerance for v in d.values())
            self_check["arms"][arm] = {"delta_vs_published": d, "within_tolerance": ok}
        self_check["pass"] = all(v["within_tolerance"] for v in self_check["arms"].values())

    out = OUT_ROOT / args.exp
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "exp_id": args.exp, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "questions": str(args.questions), "split": args.split, "n_questions": n,
        "unresolved": unresolved, "filters": filters, "overrides": overrides,
        "params": {
            "dense_k": cfg.retrieval.dense_k, "fts_terms_k": cfg.retrieval.fts_terms_k,
            "fts_trigram_k": cfg.retrieval.fts_trigram_k, "fused_k": cfg.retrieval.fused_k,
            "rerank_k_config_dead": cfg.retrieval.rerank_k, "reranker_candidate_k": cfg.reranker.candidate_k,
            "final_k": cfg.retrieval.final_k, "rrf_k": cfg.fusion.rrf_k,
            "weights": [cfg.fusion.dense_weight, cfg.fusion.terms_weight, cfg.fusion.trigram_weight],
            "parent_boost": cfg.fusion.parent_boost, "parent_boost_enabled": cfg.fusion.parent_boost_enabled,
            "embedding": cfg.embedding.model, "reranker": cfg.reranker.model,
        },
        "corpus": {
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "allowed_chunks": len(allowed) if allowed is not None else None,
        },
    }
    (out / "trace.json").write_text(
        json.dumps({**meta, "summary_by_arm": summary, "candidate_recall": cand_recall,
                    "candidate_presence": presence_summary,
                    "bucket_distribution": buckets, "self_check": self_check, "traces": traces},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "per_query.jsonl").open("w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # summary.md
    L = [f"# p8_trace · {args.exp}", "",
         f"- 时间：{meta['generated_at']}",
         f"- 题集：{args.questions}（split={args.split}, n={n}, unresolved={len(unresolved)}）",
         f"- filters：`{args.filters}`" + (f"（allowed_chunks={len(allowed)}）" if allowed is not None else ""),
         f"- 语料：documents={meta['corpus']['documents']} chunks={meta['corpus']['chunks']}", "",
         "## 1. 逐层 gold 名次（失败题）", "",
         "| id | type | dense | terms | trigram | union50 | fused | rerank_in | reranked | final | bucket |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in traces:
        if t["bucket"] == "OK":
            continue
        L.append(f"| {t['id']} | {t['type']} | {t['dense_rank']} | {t['terms_rank']} | {t['trigram_rank']} | "
                 f"{t['union50_rank']} | {t['fused_rank']} | {t['rerank_input_pos']} | {t['reranked_rank']} | "
                 f"{t['final_rank']} | {t['bucket']} |")
    L += ["", "## 2. Candidate Recall / Presence", "",
          "> **Presence = 题级候选存在率**（该题任一 gold>=2 出现在该层）。这是「召回 vs 排序」的决定性分叉。", "",
          "| 指标 | 值 |", "|---|---|"]
    for k, v in presence_summary.items():
        L.append(f"| presence · {k} | {v} |")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    for k, v in cand_recall.items():
        if v is not None:
            L.append(f"| section-recall · {k} | {v} |")
    L += ["", "## 3. 7 臂指标（本次复跑）", "",
          "| Arm | Hit@1 | Hit@3 | Hit@5 | MRR | NDCG | p50(ms) | p95(ms) |",
          "|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        v = summary[a]
        L.append(f"| {a} | {v.get('hit1')} | {v.get('hit3')} | {v.get('hit5')} | {v.get('mrr')} | "
                 f"{v.get('ndcg')} | {v.get('p50_ms')} | {v.get('p95_ms')} |")
    L += ["", "## 4. 自校验 vs 已发布回归（±%s）" % args.tolerance, "",
          f"**pass = {self_check.get('pass')}**", "",
          "| Arm | Δhit5 | Δmrr | Δndcg | within |", "|---|---|---|---|---|"]
    for a, v in self_check.get("arms", {}).items():
        d = v["delta_vs_published"]
        L.append(f"| {a} | {d['hit5']:+} | {d['mrr']:+} | {d['ndcg']:+} | {v['within_tolerance']} |")
    L += ["", "## 5. 失败归因分布（P8 bucket）", "", "```",
          json.dumps(buckets, ensure_ascii=False), "```"]
    (out / "summary.md").write_text("\n".join(L), encoding="utf-8")

    print(json.dumps({"exp": args.exp, "summary_by_arm": summary["hybrid_rerank"],
                      "candidate_recall": cand_recall, "candidate_presence": presence_summary,
                      "buckets": buckets, "self_check_pass": self_check.get("pass")},
                     ensure_ascii=False, indent=2))
    print(f"elapsed={round(time.perf_counter()-t_start,1)}s -> {out}")
    mgr.shutdown()
    conn.close()
    return 0


# m9 口径指标（与发布回归严格一致）
def metrics_for(ranked_ids, gold: Gold, section_of):
    grades = [gold.grade(cid, section_of) for cid in ranked_ids[:10]]
    rel = [g >= 2 for g in grades]
    hit = lambda k: 1 if any(rel[:k]) else 0  # noqa: E731
    if gold.rel_sections:
        total = len(gold.rel_sections)
        found = set()
        for cid in ranked_ids:
            sid = section_of.get(cid)
            if sid:
                for s in gold.rel_sections:
                    if sid == s or sid.startswith(s + ":"):
                        found.add(s)
        # 与 m9 一致：recall5/10 只看前 5/10
        r5 = len({s for cid in ranked_ids[:5] for s in gold.rel_sections
                  if section_of.get(cid) and (section_of[cid] == s or section_of[cid].startswith(s + ":"))}) / total if total else 0.0
        r10 = len({s for cid in ranked_ids[:10] for s in gold.rel_sections
                   if section_of.get(cid) and (section_of[cid] == s or section_of[cid].startswith(s + ":"))}) / total if total else 0.0
    else:
        r5 = chunk_recall(ranked_ids, 5, gold.rel_chunks)
        r10 = chunk_recall(ranked_ids, 10, gold.rel_chunks)
    mrr = 0.0
    for i, r in enumerate(rel, 1):
        if r:
            mrr = 1.0 / i
            break
    dcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(grades, 1))
    ideal = sorted(grades, reverse=True)
    idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1)) or 1.0
    return {"hit1": hit(1), "hit3": hit(3), "hit5": hit(5),
            "recall5": round(r5, 3), "recall10": round(r10, 3),
            "mrr": round(mrr, 3), "ndcg": round(dcg / idcg, 3)}


if __name__ == "__main__":
    raise SystemExit(main())
