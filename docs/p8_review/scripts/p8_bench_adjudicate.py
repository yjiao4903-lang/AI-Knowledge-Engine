# -*- coding: utf-8 -*-
"""P8-BENCH-02：盲化人工相关性判定（blinded human adjudication）工具链。

背景 / 为什么需要它
-------------------
`p8_bench_pool.py` 的 `grade_chunk()` 用 token 包含 + 正则谓词**机械**判定相关度，其产物是
**机器预标注 `auto_prelabel`**。2026-09-11 WEB-CONTROL 更正指出：预标注结果不能用来推断检索
质量，也不能用来判定 benchmark 无效。相关性判定必须由**人工领域审阅**给出，且人工判定要与
自动预标注**分开持久化**、可审计、可冻结。

本脚本提供三段式工作流（全部确定性、无检索参数改动）：

  export  —— 生成**盲化人审包**：冻结 query + 打散后的候选池 + 足够源文本；
             检索视图名 / 名次 / 分数 / 自动 grade **一律不出现在包内**。
             盲化映射单独写入 key 文件（Holdout 的 key 必须留在仓库外）。
  import  —— 导入人工判定：校验 schema（grade 0/1/2/3、accept/rewrite/reject/ambiguous、
             审阅人 / 审阅版本 / 时间戳），**只由人工 grade 重算 gold**，并做人审后的
             false-negative 审计；输出 gold + freeze 哈希。
  report  —— 报告 auto_prelabel 与人工判定的**分歧**、人审池内的 pooled recall，
             并给出用人工 gold 重算正式指标的命令。

盲化与池化假设（必须随结论一起披露）
------------------------------------
1. `export` 只把候选**集合**交给审阅人，顺序按 seed 确定性打散；候选的视图归属/名次/分数
   只在 key 中留存，用于事后统计，不在包内可见。
2. 包内候选是 4 个冻结视图 top-N 的**有界轮转抽样**，不是全语料穷举。因此未被包内出现的
   相关块不会成为 gold —— 这是标准 pooling 假设（"未判定 = 不相关"），属已披露的限制。
3. `--n` 校准子集（Issue #39：Dev 20 + sealed Holdout 10）按 tier 轮转 + family 覆盖确定性抽样。

用法
----
  # 1) 生成人审包（Dev 包与 key 可入库；Holdout 的包与 key 必须留在仓库外）
  python docs/p8_review/scripts/p8_bench_adjudicate.py export \\
      --questions docs/p8_review/benchmark/development_v1/pilot_v1_auto_prelabel.jsonl \\
      --split development --n 20 \\
      --outdir docs/p8_review/benchmark/adjudication/development_calibration_v1 \\
      --keydir docs/p8_review/benchmark/adjudication/development_calibration_v1 \\
      --pool-audit docs/p8_review/benchmark/development_v1/pool_audit_v1.json

  # 2) 人工填好 judgments 后导入（只由人工 grade 重算 gold）
  python docs/p8_review/scripts/p8_bench_adjudicate.py import \\
      --judgments <filled.jsonl> --key <key.json> --questions <frozen.jsonl> \\
      --split development --adjudication-out <adj.jsonl> \\
      --gold-out <gold.jsonl> --freeze-out <freeze.json>

  # 3) auto_prelabel vs 人工 分歧 + 人审池 recall
  python docs/p8_review/scripts/p8_bench_adjudicate.py report \\
      --judgments <adj.jsonl> --key <key.json> --split development \\
      --out <report.json> --md <report.md>

  # 4) 无 GPU 确定性自检（schema/往返/哈希/密封护栏）
  python docs/p8_review/scripts/p8_bench_adjudicate.py self-test
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent

PACKET_VERSION = "1.0"
ADJUDICATION_VERSION = "1.0"
KEY_VERSION = "1.0"
DEFAULT_SEED = "p8-bench-02-adjudication-20260911"

VIEW_NAMES = ("dense", "lexical", "hybrid", "hybrid_rerank")
GRADES = (0, 1, 2, 3)
STATUSES = ("accept", "rewrite", "reject", "ambiguous")
REVIEWER_KINDS = ("human", "agent_assisted", "selftest")

REQUIRED_JUDGMENT_FIELDS = ("adjudication_version", "qid", "reviewer", "reviewer_kind",
                            "reviewer_version", "reviewed_at", "status", "grades")


# ------------------------------------------------------------------ 基础工具
def load_jsonl(p: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def dump_jsonl(p: str | Path, rows: list[dict]) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sha256_file(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha256_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def write_json(p: str | Path, obj) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def in_repo(p: str | Path) -> bool:
    try:
        Path(p).resolve().relative_to(REPO.resolve())
        return True
    except ValueError:
        return False


def guard_sealed(split: str, paths, allow_repo_holdout: bool) -> None:
    """Holdout 内容（题目/金标/逐题判定/key）不得进入公开仓库。"""
    if split != "holdout" or allow_repo_holdout:
        return
    bad = [str(p) for p in paths if p and in_repo(p)]
    if bad:
        raise SystemExit(
            "REFUSING: sealed Holdout 产物不得写入仓库（Issue #39 密封条款）：\n  "
            + "\n  ".join(bad)
            + "\n请把 --outdir/--keydir/--*-out 指向仓库外路径，或显式 --allow-repo-holdout（仅限本地调试）。")


def norm_text(s: str | None, limit: int) -> str:
    t = " ".join((s or "").split())
    return t if len(t) <= limit else t[:limit] + " …"


# ------------------------------------------------------------------ 校准抽样
def sample_calibration(items: list[dict], n: int, seed: str) -> list[dict]:
    """确定性分层抽样：先保证 family 覆盖，再按 tier 轮转补足。

    同一 (items, n, seed) 必得同一子集。
    """
    if n >= len(items):
        return sorted(items, key=lambda x: x["id"])

    def hkey(it: dict) -> str:
        return hashlib.sha256(f"{seed}|{it['id']}".encode("utf-8")).hexdigest()

    picked: list[dict] = []
    used: set[str] = set()

    # 1) family 覆盖：每个 family 先取 1 题
    for fam in sorted({it["query_type"] for it in items}):
        if len(picked) >= n:
            break
        cands = sorted([it for it in items if it["query_type"] == fam], key=hkey)
        if cands:
            picked.append(cands[0])
            used.add(cands[0]["id"])

    # 2) tier 轮转补足
    tiers = sorted({it["corpus_tier"] for it in items})
    buckets = {t: sorted([it for it in items
                          if it["corpus_tier"] == t and it["id"] not in used], key=hkey)
               for t in tiers}
    idx = {t: 0 for t in tiers}
    progress = True
    while len(picked) < n and progress:
        progress = False
        for t in tiers:
            if len(picked) >= n:
                break
            while idx[t] < len(buckets[t]):
                it = buckets[t][idx[t]]
                idx[t] += 1
                if it["id"] not in used:
                    picked.append(it)
                    used.add(it["id"])
                    progress = True
                    break
    return picked


# ------------------------------------------------------------------ export
def cmd_export(a) -> int:
    from p8_bench_views import FrozenViews, open_catalog, rows_for
    from p8_bench_pool import grade_chunk
    from p8_bench_build import load_corpus, make_splits

    outdir, keydir = Path(a.outdir), Path(a.keydir or a.outdir)
    guard_sealed(a.split, [outdir, keydir], a.allow_repo_holdout)

    conn = open_catalog()
    questions = load_jsonl(a.questions)
    for q in questions:
        assert q.get("split") == a.split, f"{q.get('id')}: split mismatch"
    dev_map, hold_map = make_splits(load_corpus(conn))
    active = dev_map if a.split == "development" else hold_map
    allowed = {d["id"] for ds in active.values() for d in ds}

    fn_by_qid: dict[str, list[str]] = {}
    if a.pool_audit and Path(a.pool_audit).exists():
        for rec in json.loads(Path(a.pool_audit).read_text(encoding="utf-8")).get("per_query", []):
            fn_by_qid[rec["id"]] = [x["chunk_id"] for x in rec.get("fn", [])]

    sample = sample_calibration(questions, a.n, a.seed)
    fv = FrozenViews(conn=conn)

    packet, key_queries, cand_counts = [], {}, []
    cross_excluded = 0
    for i, q in enumerate(sample, 1):
        views, _ = fv.views(q["query"], topn=a.topn)
        rows = rows_for(conn, list(dict.fromkeys(sum(views.values(), []))))
        rank_of = {v: {cid: r for r, cid in enumerate(views[v], 1)} for v in VIEW_NAMES}

        excluded = {cid for cid, r in rows.items() if r["document_id"] not in allowed}
        cross_excluded += len(excluded)

        auto_gold = {c["chunk_id"]: c["grade"] for c in q["gold"]["chunks"]}
        special = [c for c in auto_gold] + [c for c in fn_by_qid.get(q["id"], [])]
        special = list(dict.fromkeys([c for c in special if c in rows and c not in excluded]))
        chosen = list(special)

        # 4 视图有界轮转抽样（视图身份不在包内可见）
        per_view = {v: [c for c in views[v] if c in rows and c not in excluded] for v in VIEW_NAMES}
        cursor = {v: 0 for v in VIEW_NAMES}
        rounds = 0
        while len(chosen) < a.max_candidates and rounds < a.per_view_k:
            for v in VIEW_NAMES:
                if len(chosen) >= a.max_candidates:
                    break
                while cursor[v] < len(per_view[v]) and per_view[v][cursor[v]] in chosen:
                    cursor[v] += 1
                if cursor[v] < len(per_view[v]):
                    chosen.append(per_view[v][cursor[v]])
                    cursor[v] += 1
            rounds += 1
        chosen = list(dict.fromkeys(chosen))

        # 确定性打散（同一 qid + seed 必得同一顺序）→ cand_id 不携带任何名次信息
        rnd = random.Random(f"{a.seed}|{q['id']}|shuffle")
        rnd.shuffle(chosen)

        rubric = (q.get("judging") or {}).get("rubric") or {"req": [], "requires_any": []}
        cands, key_cands = [], {}
        for k, cid in enumerate(chosen, 1):
            cand_id = f"{q['id']}#c{k:03d}"
            row = rows[cid]
            blob = ((row["plain_text"] or "") + "\n" + (row["heading_path"] or "")).lower()
            cands.append({
                "cand_id": cand_id,
                "document_id": row["document_id"],
                "heading_path": row["heading_path"],
                "text": norm_text(row["plain_text"], a.text_chars),
            })
            key_cands[cand_id] = {
                "chunk_id": cid,
                "document_id": row["document_id"],
                "views": {v: rank_of[v].get(cid) for v in VIEW_NAMES},
                "auto_prelabel_grade": grade_chunk(rubric, blob),
                "auto_prelabel_gold_grade": auto_gold.get(cid),
            }

        packet.append({
            "packet_version": PACKET_VERSION, "qid": q["id"], "split": a.split,
            "query": q["query"], "query_type": q["query_type"], "corpus_tier": q["corpus_tier"],
            "candidates": cands,
        })
        key_queries[q["id"]] = {
            "query": q["query"], "query_type": q["query_type"], "corpus_tier": q["corpus_tier"],
            "auto_prelabel_gold": [{"chunk_id": c, "grade": g} for c, g in sorted(auto_gold.items())],
            "views_ranked": {v: list(views[v]) for v in VIEW_NAMES},
            "candidates": key_cands,
        }
        cand_counts.append(len(cands))
        if i % 10 == 0 or i == len(sample):
            print(f"  [{i}/{len(sample)}] {q['id']} cands={len(cands)}", flush=True)

    stem = f"{a.split}_calibration_v1"
    packet_path = outdir / f"packet_{stem}.jsonl"
    key_path = keydir / f"key_{stem}.json"
    dump_jsonl(packet_path, packet)
    write_json(key_path, {"key_version": KEY_VERSION, "split": a.split, "seed": a.seed,
                          "topn": a.topn, "queries": key_queries})

    cov_tier = Counter(p["corpus_tier"] for p in packet)
    cov_fam = Counter(p["query_type"] for p in packet)
    manifest = {
        "packet_version": PACKET_VERSION, "seed": a.seed, "split": a.split,
        "source_questions": str(a.questions), "source_questions_sha256": sha256_file(a.questions),
        "n_questions_available": len(questions), "n_sampled": len(sample),
        "sampling": "family 覆盖优先 + tier 轮转（seed 确定性）",
        "blinding": {
            "hidden_from_reviewer": ["view 归属", "视图内名次", "融合/RRF 分数", "auto_prelabel grade"],
            "shuffle": f"random.Random('{a.seed}|<qid>|shuffle')",
            "cand_id": "<qid>#c<index>，index 为打散后位置，不携带名次信息",
            "key_file": str(key_path), "key_file_in_repo": in_repo(key_path),
        },
        "selection": {"view_topn": a.topn, "per_view_k": a.per_view_k,
                      "max_candidates": a.max_candidates,
                      "always_included": "auto_prelabel gold + 池内 FN 候选",
                      "cross_split_candidates_excluded": cross_excluded},
        "candidate_count": {"min": min(cand_counts), "max": max(cand_counts),
                            "median": sorted(cand_counts)[len(cand_counts) // 2]},
        "coverage": {"by_tier": dict(sorted(cov_tier.items())),
                     "by_family": dict(sorted(cov_fam.items()))},
        "pooling_assumption": "包内候选未判定的块按不相关计（标准 pooling 假设）；候选集为有界抽样，非全语料穷举。",
        "packet_sha256": sha256_file(packet_path), "key_sha256": sha256_file(key_path),
        "queries": sorted(key_queries),
    }
    man_path = outdir / f"packet_{stem}.manifest.json"
    write_json(man_path, manifest)

    template = [{
        "adjudication_version": ADJUDICATION_VERSION, "qid": p["qid"],
        "reviewer": "", "reviewer_kind": "human", "reviewer_version": "",
        "reviewed_at": "", "status": "", "final_query": "",
        "grades": [{"cand_id": c["cand_id"], "grade": None, "rationale": ""} for c in p["candidates"]],
        "notes": "",
    } for p in packet]
    tpl_path = outdir / f"judgments_{stem}.template.jsonl"
    dump_jsonl(tpl_path, template)

    md_path = outdir / f"review_form_{stem}.md"
    write_review_form(md_path, packet, manifest)

    print(json.dumps({"packet": str(packet_path), "key": str(key_path),
                      "manifest": str(man_path), "template": str(tpl_path),
                      "review_form": str(md_path), "n": len(packet),
                      "packet_sha256": manifest["packet_sha256"][:16],
                      "key_in_repo": manifest["blinding"]["key_file_in_repo"]},
                     ensure_ascii=False, indent=2))
    fv.close()
    return 0


def write_review_form(path: str | Path, packet: list[dict], manifest: dict) -> None:
    path = Path(path)
    L = [
        "# P8-BENCH-02 盲化人审表（blinded human adjudication form）", "",
        f"- split：**{manifest['split']}** ｜ 题数：**{manifest['n_sampled']}** ｜ seed：`{manifest['seed']}`",
        f"- 包 SHA256：`{manifest['packet_sha256']}`",
        f"- 抽样：{manifest['sampling']}",
        "- **本表刻意不显示**：检索视图归属、视图内名次、融合分数、auto_prelabel grade。",
        "- 候选为 4 个冻结视图 top-N 的**有界抽样**；未在本表出现的 chunk 不参与 gold（standard pooling 假设）。", "",
        "## 判定口径（graded relevance）", "",
        "| grade | 含义 |", "|---|---|",
        "| 3 | 直接回答该信息需求 |",
        "| 2 | 实质性支撑答案 / 有效的替代证据 |",
        "| 1 | 主题相关但不足以回答 |",
        "| 0 | 不相关 |", "",
        "`status`：`accept`（query 与 gold 可接受）/ `rewrite`（需改写 query，填 `final_query`）"
        "/ `reject`（query 不可辩护）/ `ambiguous`（无法判定，需复查）。", "",
        "> accept / rewrite 的题必须至少 1 个 grade-3。", "",
        "---", "",
    ]
    for p in packet:
        L += [f"## {p['qid']} · {p['query_type']} / {p['corpus_tier']}", "",
              f"**query**：{p['query']}", "",
              f"**候选 {len(p['candidates'])} 个**（顺序已打散；未显示检索视图 / 名次 / 分数 / 预标注 grade）", ""]
        for i, c in enumerate(p["candidates"], 1):
            L += [f"#### {i}. `{c['cand_id']}`", "",
                  f"- document：`{c['document_id']}`",
                  f"- heading：{c['heading_path'] or '（无）'}",
                  "- 文本：", ""]
            for ln in c["text"].splitlines() or [""]:
                L.append(f"> {ln}")
            L += ["", "`grade（0/1/2/3）`：______", ""]
        L += ["**status**：______（accept / rewrite / reject / ambiguous）",
              "**final_query**（status=rewrite 时必填）：______",
              "**notes**：______", "", "---", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ import
def validate_judgment(rec: dict, key_q: dict, errs: list[str]) -> None:
    qid = rec.get("qid", "?")
    for f in REQUIRED_JUDGMENT_FIELDS:
        if f not in rec or rec[f] in (None, ""):
            errs.append(f"{qid}: 缺少字段 {f}")
    if rec.get("adjudication_version") != ADJUDICATION_VERSION:
        errs.append(f"{qid}: adjudication_version 必须为 {ADJUDICATION_VERSION}")
    if rec.get("reviewer_kind") not in REVIEWER_KINDS:
        errs.append(f"{qid}: reviewer_kind 非法 {rec.get('reviewer_kind')!r}")
    if rec.get("status") not in STATUSES:
        errs.append(f"{qid}: status 非法 {rec.get('status')!r}")
    ts = rec.get("reviewed_at")
    if ts:
        try:
            datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            errs.append(f"{qid}: reviewed_at 非 ISO8601：{ts!r}")
    if rec.get("status") == "rewrite" and not rec.get("final_query"):
        errs.append(f"{qid}: status=rewrite 必须提供 final_query")

    seen, g3 = set(), 0
    for g in rec.get("grades") or []:
        cid = g.get("cand_id")
        if cid not in key_q["candidates"]:
            errs.append(f"{qid}: 未知 cand_id {cid!r}（不在该题 key 中）")
            continue
        if cid in seen:
            errs.append(f"{qid}: cand_id 重复 {cid}")
        seen.add(cid)
        grade = g.get("grade")
        if grade is None:
            errs.append(f"{qid}: grade 未填写（{cid}，模板占位未替换）")
        elif grade not in GRADES:
            errs.append(f"{qid}: grade 非法 {grade!r}（{cid}）")
        elif grade == 3:
            g3 += 1
    judged = len(seen)
    packet_ids = set(key_q["candidates"])
    missing = sorted(packet_ids - seen)
    if rec.get("status") in ("accept", "rewrite"):
        # candidate-level completeness：accept/rewrite 必须把该题人审包内每个候选都判定且仅判定一次
        if judged == 0:
            errs.append(f"{qid}: accept/rewrite 必须给出候选 grade")
        if missing:
            errs.append(f"{qid}: 候选判定不完整 —— 该题人审包共 {len(packet_ids)} 个候选，缺 {len(missing)} 个"
                        f"（例如 {missing[:5]}）；accept/rewrite 必须逐个候选判定")
        if g3 == 0:
            errs.append(f"{qid}: accept/rewrite 必须至少 1 个 grade-3")


def build_gold_record(frozen: dict, rec: dict, key_q: dict) -> dict:
    out = copy.deepcopy(frozen)
    out["query"] = rec.get("final_query") or frozen["query"]
    gold = []
    human = {}
    fn_added = []
    auto_gold = {c["chunk_id"]: c["grade"] for c in key_q["auto_prelabel_gold"]}
    for g in rec.get("grades") or []:
        kg = key_q["candidates"][g["cand_id"]]
        human[kg["chunk_id"]] = g["grade"]
        if g["grade"] >= 2:
            gold.append({"chunk_id": kg["chunk_id"], "grade": g["grade"]})
            if kg["chunk_id"] not in auto_gold:
                fn_added.append(kg["chunk_id"])
    out["gold"] = {"mode": "chunk_ids", "chunks": sorted(gold, key=lambda x: (x["grade"], x["chunk_id"]))}
    out["evidence_class"] = "human_adjudicated"
    out["gold_revision"] = "human_v1"
    out["version"] = f"{frozen.get('version', '1.0')}-human"
    j = dict(out.get("judging") or {})
    j.update({
        "human_adjudicated": True,
        "reviewer": rec.get("reviewer"), "reviewer_kind": rec.get("reviewer_kind"),
        "reviewer_version": rec.get("reviewer_version"), "reviewed_at": rec.get("reviewed_at"),
        "status": rec.get("status"),
        "candidates_in_packet": len(key_q["candidates"]),
        "candidates_judged": len(human),
        "human_grade_dist": {str(k): sum(1 for v in human.values() if v == k) for k in GRADES},
        "human_grade3": sum(1 for v in human.values() if v == 3),
        "fn_added_after_human_audit": sorted(fn_added),
    })
    out["judging"] = j
    return out


def candidate_completeness(recs: list[dict], key_queries: dict) -> dict:
    """accept/rewrite 题的候选级判定完整度（拒答题不要求逐候选判定）。

    只有 `accept` / `rewrite` 的题才进入 gold 与指标计算，因此也只有它们需要
    100% 的候选覆盖（pooled false-negative 审计要求逐个候选判定）。
    """
    per_query, incomplete = {}, []
    accepted = 0
    for rec in recs:
        if rec.get("status") not in ("accept", "rewrite"):
            continue
        qid = rec.get("qid")
        kq = key_queries.get(qid)
        if not kq:
            continue
        accepted += 1
        packet = set(kq["candidates"])
        graded = {g.get("cand_id") for g in (rec.get("grades") or [])} & packet
        complete = graded == packet
        per_query[qid] = {"graded": len(graded), "packet": len(packet), "complete": complete}
        if not complete:
            incomplete.append(qid)
    return {
        "accepted_or_rewritten": accepted,
        "fully_graded": accepted - len(incomplete),
        "coverage": round((accepted - len(incomplete)) / accepted, 4) if accepted else None,
        "incomplete_queries": sorted(incomplete),
        "per_query": dict(sorted(per_query.items())),
    }


def assess_review(recs: list[dict], key_queries: dict) -> dict:
    """freeze 与 report 共用的审阅完备性评估（两处口径必须一致）。"""
    seen = {r.get("qid") for r in recs}
    missing = sorted(set(key_queries) - seen)
    kinds = sorted({r.get("reviewer_kind") for r in recs})
    status_dist = dict(sorted(Counter(r.get("status") for r in recs).items()))
    cc = candidate_completeness(recs, key_queries)
    warnings = []
    if cc["accepted_or_rewritten"] == 0 and recs:
        warnings.append("全部题被 reject/ambiguous，没有可用于评测的 gold。")
    complete = (bool(recs) and kinds == ["human"] and not missing
                and cc["coverage"] == 1.0)
    return {
        "n_records": len(recs), "n_queries_in_packet": len(key_queries), "missing_queries": missing,
        "reviewer_kinds": kinds, "status_dist": status_dist,
        "candidate_completeness": cc,
        "human_review_complete": complete,
        "warnings": warnings,
        "human_review_blocker": None if complete else
            "需全部校准题均由 human 判定且无缺题，且所有 accept/rewrite 题的候选覆盖率为 100%（或存在非 human 的 reviewer_kind）。",
    }


def cmd_import(a) -> int:
    key = json.loads(Path(a.key).read_text(encoding="utf-8"))
    key_queries = key["queries"]
    questions = {q["id"]: q for q in load_jsonl(a.questions)}
    recs = load_jsonl(a.judgments)

    guard_sealed(a.split, [a.adjudication_out, a.gold_out, a.freeze_out],
                 getattr(a, "allow_repo_holdout", False))

    errs: list[str] = []
    seen: set[str] = set()
    for rec in recs:
        qid = rec.get("qid")
        if qid not in key_queries:
            errs.append(f"{qid}: 不在 key 中")
            continue
        if qid in seen:
            errs.append(f"{qid}: 重复判定记录")
        seen.add(qid)
        validate_judgment(rec, key_queries[qid], errs)
    missing = sorted(set(key_queries) - seen)
    if getattr(a, "require_complete", False) and missing:
        errs.append(f"未覆盖 {len(missing)} 题（--require-complete）：{missing[:10]}")
    if errs:
        print(json.dumps({"pass": False, "n_errors": len(errs), "errors": errs[:60]},
                         ensure_ascii=False, indent=2))
        return 1

    gold_rows, rejected = [], []
    status_dist = Counter()
    for rec in recs:
        qid = rec["qid"]
        status_dist[rec["status"]] += 1
        if rec["status"] in ("reject", "ambiguous"):
            rejected.append({"qid": qid, "status": rec["status"], "notes": rec.get("notes", ""),
                             "query": key_queries[qid]["query"]})
            continue
        gold_rows.append(build_gold_record(questions[qid], rec, key_queries[qid]))

    assess = assess_review(recs, key_queries)
    freeze = {
        "adjudication_version": ADJUDICATION_VERSION, "split": a.split,
        "n_records": len(recs), "n_accepted": len(gold_rows), "n_rejected": len(rejected),
        "status_dist": assess["status_dist"],
        "reviewer_kinds": assess["reviewer_kinds"],
        "reviewers": sorted({r.get("reviewer") for r in recs if r.get("reviewer")}),
        # 候选级完整度：freeze 显式暴露每题的 graded/packet 计数
        "candidate_completeness": assess["candidate_completeness"],
        "human_review_complete": assess["human_review_complete"],
        "human_review_blocker": assess["human_review_blocker"],
        "warnings": assess["warnings"],
        "hashes": {
            "judgments_sha256": sha256_file(a.judgments),
            "key_sha256": sha256_file(a.key),
            "questions_sha256": sha256_file(a.questions),
        },
        "coverage": {"sampled": len(key_queries), "adjudicated": len(recs), "missing": missing},
    }

    stem = f"{a.split}_calibration_v1"
    dump_jsonl(a.adjudication_out or f"{stem}_adjudication.jsonl", recs)
    if gold_rows:
        dump_jsonl(a.gold_out or f"{stem}_gold.jsonl", gold_rows)
        freeze["hashes"]["gold_sha256"] = sha256_file(a.gold_out or f"{stem}_gold.jsonl")
    write_json(a.freeze_out or f"{stem}_freeze.json", freeze)

    cc = freeze["candidate_completeness"]
    print(json.dumps({"pass": True, "n_records": len(recs), "n_gold": len(gold_rows),
                      "n_rejected": len(rejected), "status_dist": freeze["status_dist"],
                      "candidate_completeness": {"accepted_or_rewritten": cc["accepted_or_rewritten"],
                                                 "fully_graded": cc["fully_graded"],
                                                 "coverage": cc["coverage"],
                                                 "incomplete_queries": cc["incomplete_queries"]},
                      "human_review_complete": freeze["human_review_complete"],
                      "warnings": freeze["warnings"],
                      "outputs": {"adjudication": str(a.adjudication_out),
                                  "gold": str(a.gold_out), "freeze": str(a.freeze_out)}},
                     ensure_ascii=False, indent=2))
    return 0


# ------------------------------------------------------------------ report
def pooled_recall(ranked: list[str], rel: set[str], k: int) -> float | None:
    if not rel:
        return None
    return round(len(set(ranked[:k]) & rel) / len(rel), 4)


def cmd_report(a) -> int:
    key = json.loads(Path(a.key).read_text(encoding="utf-8"))
    key_queries = key["queries"]
    rec_list = load_jsonl(a.judgments)
    recs = {r["qid"]: r for r in rec_list}
    assess = assess_review(rec_list, key_queries)

    per_query: list[dict] = []
    excluded: list[dict] = []
    agree_c = 0
    pm1 = 0
    binary = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    hand3, auto3 = 0, 0
    jaccards, recall20 = [], defaultdict(list)
    fn_total, judged_total, packet_total = 0, 0, 0

    for qid, kq in key_queries.items():
        rec = recs.get(qid)
        if not rec:
            continue
        # reject / ambiguous 是题目级处置：显式排除出 gold 与全部指标计算
        if rec.get("status") not in ("accept", "rewrite"):
            excluded.append({"qid": qid, "status": rec.get("status"),
                             "notes": rec.get("notes", ""), "query": kq["query"]})
            continue
        human = {}
        for g in rec.get("grades") or []:
            kg = kq["candidates"].get(g["cand_id"])
            if kg and g.get("grade") is not None:
                human[kg["chunk_id"]] = g["grade"]
        auto = {cid: c["auto_prelabel_grade"] for cid, c in kq["candidates"].items()}
        auto_by_chunk = {kq["candidates"][cid]["chunk_id"]: g for cid, g in auto.items()}
        auto_gold = {c["chunk_id"]: c["grade"] for c in kq["auto_prelabel_gold"]}

        pq_judged = len(human)
        judged_total += pq_judged
        packet_total += len(kq["candidates"])
        for cid, hg in human.items():
            ag = auto_by_chunk.get(cid, 0)
            agree_c += 1 if ag == hg else 0
            pm1 += 1 if abs(ag - hg) <= 1 else 0
            ar, hr = ag >= 2, hg >= 2
            if ar and hr:
                binary["tp"] += 1
            elif ar and not hr:
                binary["fp"] += 1
            elif hr and not ar:
                binary["fn"] += 1
            else:
                binary["tn"] += 1
            if hg >= 2 and cid not in auto_gold:
                fn_total += 1
        h3 = {c for c, g in human.items() if g == 3}
        a3 = {c for c, g in auto_gold.items() if g == 3}
        hand3 += len(h3)
        auto3 += len(a3)
        union = h3 | a3
        jaccards.append(round(len(h3 & a3) / len(union), 4) if union else 1.0)

        rel = {c for c, g in human.items() if g >= 2}
        for v in VIEW_NAMES:
            r = pooled_recall(kq["views_ranked"][v], rel, a.recall_k)
            if r is not None:
                recall20[v].append(r)
        union20 = list(dict.fromkeys(sum((kq["views_ranked"][v][:a.recall_k] for v in VIEW_NAMES), [])))
        r = pooled_recall(union20, rel, a.recall_k)
        if r is not None:
            recall20["union"].append(r)

        per_query.append({"qid": qid, "status": rec.get("status"), "query": kq["query"],
                          "judged": pq_judged, "packet": len(kq["candidates"]),
                          "human_g3": len(h3), "auto_g3": len(a3),
                          "human_rel": len(rel), "auto_rel": len(auto_gold),
                          "fn_missed_by_prelabel": sum(1 for c, g in human.items()
                                                       if g >= 2 and c not in auto_gold)})

    tp, fp, fn = binary["tp"], binary["fp"], binary["fn"]
    prec = round(tp / (tp + fp), 4) if tp + fp else None
    rec_ = round(tp / (tp + fn), 4) if tp + fn else None
    f1 = round(2 * prec * rec_ / (prec + rec_), 4) if prec and rec_ else None
    report = {
        "split": a.split,
        "n_queries_in_packet": len(key_queries),
        "n_queries_judged": len(recs),
        "n_queries_measured": len(per_query),
        "reviewer_kinds": assess["reviewer_kinds"], "dispositions": assess["status_dist"],
        "candidate_completeness": assess["candidate_completeness"],
        "human_review_complete": assess["human_review_complete"],
        "human_review_blocker": assess["human_review_blocker"],
        "warnings": assess["warnings"],
        "excluded_from_metrics": {
            "statuses": ["reject", "ambiguous"], "n": len(excluded), "queries": excluded,
            "note": "reject/ambiguous 是题目级处置，已排除出 gold 与全部指标计算。",
        },
        "coverage": {"candidates_total": packet_total, "candidates_judged": judged_total,
                     "judged_share": round(judged_total / packet_total, 4) if packet_total else 0},
        "auto_prelabel_vs_human": {
            "candidate_pairs": judged_total,
            "exact_grade_agreement": round(agree_c / judged_total, 4) if judged_total else None,
            "within_one_grade": round(pm1 / judged_total, 4) if judged_total else None,
            "binary_relevance_ge2": {"tp": tp, "fp": fp, "fn": fn, "tn": binary["tn"],
                                     "precision": prec, "recall": rec_, "f1": f1},
            "grade3_jaccard_mean": round(sum(jaccards) / len(jaccards), 4) if jaccards else None,
            "human_grade3_total": hand3, "auto_prelabel_grade3_total": auto3,
            "human_relevant_missing_from_prelabel_gold": fn_total,
        },
        "pooled_recall_benchmark_side": {
            "k": a.recall_k,
            "per_view_mean": {v: round(sum(xs) / len(xs), 4) for v, xs in sorted(recall20.items()) if xs},
            "note": "benchmark-side 计算，不改变检索行为；只覆盖人审判定过的候选（有界池）。",
        },
        "per_query": per_query,
    }
    write_json(a.out, report)
    if a.md:
        write_report_md(a.md, report, a)
    print(json.dumps({k: v for k, v in report.items() if k != "per_query"},
                     ensure_ascii=False, indent=2))
    return 0


def write_report_md(path: str | Path, rep: dict, a) -> None:
    path = Path(path)
    av = rep["auto_prelabel_vs_human"]
    cc = rep["candidate_completeness"]
    L = [f"# P8-BENCH-02 人工判定 vs 自动预标注 · {rep['split']}", "",
         f"- 已判定题数：**{rep['n_queries_judged']} / {rep['n_queries_in_packet']}**"
         f" ｜ reviewer_kind：{rep['reviewer_kinds']}",
         f"- **human_review_complete**：`{rep['human_review_complete']}`",
         f"- 处置分布：{rep['dispositions']}",
         f"- 进入指标计算的题数：**{rep['n_queries_measured']}**"
         f" ｜ 排除（reject/ambiguous）：**{rep['excluded_from_metrics']['n']}**",
         f"- **候选级完整度**（accept/rewrite）：fully_graded "
         f"**{cc['fully_graded']} / {cc['accepted_or_rewritten']}**（coverage `{cc['coverage']}`）；"
         f"未完整题：{cc['incomplete_queries'] or '无'}",
         f"- 候选判定覆盖：{rep['coverage']['candidates_judged']} / {rep['coverage']['candidates_total']}"
         f"（{rep['coverage']['judged_share']:.1%}）", ""]
    if rep.get("warnings"):
        L += [f"> ⚠ {'；'.join(rep['warnings'])}", ""]
    if rep["excluded_from_metrics"]["n"]:
        L += ["**排除的题（题目级处置，不进入 gold 与任何指标）**：",
              "", "| qid | status | notes |", "|---|---|---|"]
        for e in rep["excluded_from_metrics"]["queries"]:
            L.append(f"| `{e['qid']}` | {e['status']} | {(e.get('notes') or '').replace('|', '/')[:80]} |")
        L.append("")
    L += ["## auto_prelabel 与人工判定的分歧", "",
         "| 指标 | 值 |", "|---|---|",
         f"| candidate 级 grade 完全一致率 | {av['exact_grade_agreement']} |",
         f"| ±1 grade 一致率 | {av['within_one_grade']} |",
         f"| 二值相关（≥2）precision / recall / F1 | {av['binary_relevance_ge2']['precision']} / "
         f"{av['binary_relevance_ge2']['recall']} / {av['binary_relevance_ge2']['f1']} |",
         f"| grade-3 集合 Jaccard（均值） | {av['grade3_jaccard_mean']} |",
         f"| 人工判为相关但**预标注金标未收录**的块数 | {av['human_relevant_missing_from_prelabel_gold']} |", "",
         f"> {av.get('note', '')}" if av.get('note') else "",
         "## 人审池 recall（benchmark-side，k=" + str(rep["pooled_recall_benchmark_side"]["k"]) + "）", "",
         "| 视图 | 平均 recall |", "|---|---|"]
    for v, x in rep["pooled_recall_benchmark_side"]["per_view_mean"].items():
        L.append(f"| {v} | {x} |")
    L += ["", rep["pooled_recall_benchmark_side"]["note"], "",
          "## 正式指标", "",
          "人工 gold 落盘后由既有评测器重算（**不改检索行为**）：", "",
          "```bat", f"D:\\AI-Knowledge-Engine\\.venv\\Scripts\\python.exe docs\\p8_review\\scripts\\p8_trace.py "
          f"--exp p8_bench02_{rep['split']}_human --questions <{a.split}_gold.jsonl> "
          f"--split {rep['split']}", "```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ self-test
def cmd_self_test(a) -> int:
    """无 GPU 的确定性自检：schema 拒绝、gold 往返、哈希稳定、Holdout 密封护栏。"""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="p8_adj_selftest_"))
    ok = []

    def chk(name, cond):
        ok.append((name, bool(cond)))
        print(("  PASS  " if cond else "  FAIL  ") + name)

    def cand(qid, n, chunk, doc, rank, ag, agg):
        return {f"{qid}#c{n:03d}": {"chunk_id": chunk, "document_id": doc,
                                    "views": {v: rank for v in VIEW_NAMES},
                                    "auto_prelabel_grade": ag, "auto_prelabel_gold_grade": agg}}

    key = {"key_version": KEY_VERSION, "split": "development", "seed": "st", "topn": 50,
           "queries": {
               "Q1": {"query": "q1", "query_type": "numeric", "corpus_tier": "flagship",
                      "auto_prelabel_gold": [{"chunk_id": "ch1", "grade": 3}],
                      "views_ranked": {v: ["ch1", "ch2"] for v in VIEW_NAMES},
                      "candidates": {**cand("Q1", 1, "ch1", "D1", 1, 3, 3),
                                     **cand("Q1", 2, "ch2", "D1", 2, 0, None)}},
               "Q2": {"query": "q2", "query_type": "temporal", "corpus_tier": "flagship",
                      "auto_prelabel_gold": [{"chunk_id": "ch3", "grade": 3}],
                      "views_ranked": {v: ["ch3"] for v in VIEW_NAMES},
                      "candidates": {**cand("Q2", 1, "ch3", "D2", 1, 3, 3)}},
           }}
    questions = [{"id": "Q1", "query": "q1", "query_type": "numeric", "source_type": "flagship",
                  "corpus_tier": "flagship", "split": "development", "difficulty": "hard",
                  "temporal": False, "version": "1.0", "ocr_derived": False,
                  "gold": {"mode": "chunk_ids", "chunks": [{"chunk_id": "ch1", "grade": 3}]},
                  "source_hashes": [{"document_id": "D1", "sha256": "x" * 64}],
                  "judging": {"rubric": {"req": ["a"], "requires_any": []}}},
                 {"id": "Q2", "query": "q2", "query_type": "temporal", "source_type": "flagship",
                  "corpus_tier": "flagship", "split": "development", "difficulty": "medium",
                  "temporal": True, "version": "1.0", "ocr_derived": False,
                  "gold": {"mode": "chunk_ids", "chunks": [{"chunk_id": "ch3", "grade": 3}]},
                  "source_hashes": [{"document_id": "D2", "sha256": "y" * 64}],
                  "judging": {"rubric": {"req": ["b"], "requires_any": []}}}]
    kp, qp = tmp / "key.json", tmp / "questions.jsonl"
    write_json(kp, key)
    dump_jsonl(qp, questions)

    base = {"adjudication_version": ADJUDICATION_VERSION, "qid": "Q1", "reviewer": "r",
            "reviewer_kind": "human", "reviewer_version": "v1",
            "reviewed_at": "2026-09-11T12:00:00Z", "status": "accept"}

    # 1) 未知 cand_id
    r = dict(base, grades=[{"cand_id": "Q1#c999", "grade": 3}])
    jp = tmp / "bad1.jsonl"; dump_jsonl(jp, [r])
    rec = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                        split="development", adjudication_out=str(tmp / "x1.jsonl"),
                                        gold_out=str(tmp / "x1g.jsonl"), freeze_out=str(tmp / "x1f.json")))
    chk("拒绝未知 cand_id", rec == 1)
    # 2) 非法 grade
    jp = tmp / "bad2.jsonl"; dump_jsonl(jp, [dict(base, grades=[{"cand_id": "Q1#c001", "grade": 5}])])
    rec = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                        split="development", adjudication_out=str(tmp / "x2.jsonl"),
                                        gold_out=str(tmp / "x2g.jsonl"), freeze_out=str(tmp / "x2f.json")))
    chk("拒绝非法 grade", rec == 1)
    # 3) accept 但无 grade-3
    jp = tmp / "bad3.jsonl"; dump_jsonl(jp, [dict(base, grades=[{"cand_id": "Q1#c001", "grade": 2}])])
    rec = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                        split="development", adjudication_out=str(tmp / "x3.jsonl"),
                                        gold_out=str(tmp / "x3g.jsonl"), freeze_out=str(tmp / "x3f.json")))
    chk("拒绝 accept 无 grade-3", rec == 1)
    # 4) rewrite 缺 final_query
    jp = tmp / "bad4.jsonl"
    dump_jsonl(jp, [dict(base, status="rewrite", grades=[{"cand_id": "Q1#c001", "grade": 3}])])
    rec = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                        split="development", adjudication_out=str(tmp / "x4.jsonl"),
                                        gold_out=str(tmp / "x4g.jsonl"), freeze_out=str(tmp / "x4f.json")))
    chk("拒绝 rewrite 缺 final_query", rec == 1)
    # 5) 缺 reviewer 字段
    bad = dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3}]); bad["reviewer"] = ""
    jp = tmp / "bad5.jsonl"; dump_jsonl(jp, [bad])
    rec = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                        split="development", adjudication_out=str(tmp / "x5.jsonl"),
                                        gold_out=str(tmp / "x5g.jsonl"), freeze_out=str(tmp / "x5f.json")))
    chk("拒绝缺 reviewer", rec == 1)

    # 6) 正常往返 + FN 补入（人工把 ch2 判为 2，预标注 gold 未含 → FN 应被补入）
    good = dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3},
                              {"cand_id": "Q1#c002", "grade": 2}])
    jp = tmp / "good.jsonl"; dump_jsonl(jp, [good])
    rc = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                      split="development", adjudication_out=str(tmp / "a.jsonl"),
                                      gold_out=str(tmp / "g.jsonl"), freeze_out=str(tmp / "f.json")))
    gold = load_jsonl(tmp / "g.jsonl")[0]
    chk("gold 往返成功", rc == 0)
    chk("gold 只由人工 grade 生成", {c["chunk_id"] for c in gold["gold"]["chunks"]} == {"ch1", "ch2"})
    chk("FN 审计补入未预标注块", gold["judging"]["fn_added_after_human_audit"] == ["ch2"])
    chk("evidence_class=human_adjudicated", gold["evidence_class"] == "human_adjudicated")
    # 7) 哈希稳定性
    chk("freeze 哈希稳定", sha256_file(tmp / "g.jsonl") == sha256_file(tmp / "g.jsonl"))
    # 8) reject 不入 gold
    jp = tmp / "rej.jsonl"
    dump_jsonl(jp, [dict(base, status="reject", notes="bad query", grades=[])])
    cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                  split="development", adjudication_out=str(tmp / "ar.jsonl"),
                                  gold_out=str(tmp / "gr.jsonl"), freeze_out=str(tmp / "fr.json")))
    fr = json.loads((tmp / "fr.json").read_text(encoding="utf-8"))
    chk("reject 不计入 gold", fr["n_accepted"] == 0 and fr["n_rejected"] == 1)
    # 9) 密封护栏：Holdout 产物不得入库
    try:
        guard_sealed("holdout", [REPO / "docs" / "x.json"], allow_repo_holdout=False)
        chk("Holdout 密封护栏生效", False)
    except SystemExit:
        chk("Holdout 密封护栏生效", True)
    # 10) 校准抽样确定性
    items = [{"id": f"Q{i:02d}", "query_type": f"f{i % 4}", "corpus_tier": f"t{i % 3}"} for i in range(30)]
    chk("抽样确定性", [x["id"] for x in sample_calibration(items, 8, "s")] ==
        [x["id"] for x in sample_calibration(items, 8, "s")])
    chk("抽样覆盖全部 family",
        len({x["query_type"] for x in sample_calibration(items, 8, "s")}) ==
        len({x["query_type"] for x in items}))

    # 11) candidate-level completeness：accept 只判部分候选 → 拒绝
    partial = dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3}])
    jp = tmp / "bad6.jsonl"; dump_jsonl(jp, [partial])
    rc = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                      split="development", adjudication_out=str(tmp / "x6.jsonl"),
                                      gold_out=str(tmp / "x6g.jsonl"), freeze_out=str(tmp / "x6f.json")))
    chk("拒绝 accept 的部分候选判定（缺候选）", rc == 1)
    # 12) 重复 cand_id → 拒绝
    jp = tmp / "dup.jsonl"
    dump_jsonl(jp, [dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3},
                                       {"cand_id": "Q1#c002", "grade": 3},
                                       {"cand_id": "Q1#c002", "grade": 2}])])
    rc = cmd_import(argparse.Namespace(judgments=str(jp), key=str(kp), questions=str(qp),
                                      split="development", adjudication_out=str(tmp / "x7.jsonl"),
                                      gold_out=str(tmp / "x7g.jsonl"), freeze_out=str(tmp / "x7f.json")))
    chk("拒绝重复 cand_id", rc == 1)
    # 13) assess_review：缺题 / 非 human / 候选不完整 → human_review_complete=False
    kq = key["queries"]
    full_q1_q2 = [dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3},
                                     {"cand_id": "Q1#c002", "grade": 2}]),
                  dict(base, qid="Q2", status="reject", grades=[])]
    a_full = assess_review(full_q1_q2, kq)
    chk("complete：全覆盖 + 全 human → True", a_full["human_review_complete"] is True)
    chk("complete：reject 不要求候选覆盖", a_full["candidate_completeness"]["coverage"] == 1.0
        and a_full["candidate_completeness"]["accepted_or_rewritten"] == 1)
    a_missing = assess_review(full_q1_q2[:1], kq)
    chk("complete：缺题 → False", a_missing["human_review_complete"] is False)
    a_kind = assess_review([dict(r, reviewer_kind="agent_assisted") for r in full_q1_q2], kq)
    chk("complete：非 human → False", a_kind["human_review_complete"] is False)
    a_partial = assess_review([dict(base, grades=[{"cand_id": "Q1#c001", "grade": 3}]),
                               full_q1_q2[1]], kq)
    chk("complete：候选不完整 → False",
        a_partial["human_review_complete"] is False
        and a_partial["candidate_completeness"]["incomplete_queries"] == ["Q1"])
    # 14) report：reject/ambiguous 显式排除出指标
    jp = tmp / "mix.jsonl"; dump_jsonl(jp, full_q1_q2)
    rc = cmd_report(argparse.Namespace(judgments=str(jp), key=str(kp), split="development",
                                       out=str(tmp / "r2.json"), md=str(tmp / "r2.md"), recall_k=20))
    r2 = json.loads((tmp / "r2.json").read_text(encoding="utf-8"))
    chk("report：reject 排除出指标",
        rc == 0 and r2["n_queries_measured"] == 1 and r2["excluded_from_metrics"]["n"] == 1
        and r2["excluded_from_metrics"]["queries"][0]["qid"] == "Q2")
    chk("report：reject 不阻塞 human_review_complete（候选全覆盖）",
        r2["human_review_complete"] is True
        and r2["candidate_completeness"]["accepted_or_rewritten"] == 1)
    jp = tmp / "q1only.jsonl"; dump_jsonl(jp, full_q1_q2[:1])
    cmd_report(argparse.Namespace(judgments=str(jp), key=str(kp), split="development",
                                  out=str(tmp / "r3.json"), md=str(tmp / "r3.md"), recall_k=20))
    r3 = json.loads((tmp / "r3.json").read_text(encoding="utf-8"))
    chk("report：缺题时 human_review_complete=False",
        r3["human_review_complete"] is False and r3["candidate_completeness"]["coverage"] == 1.0)

    passed = all(v for _, v in ok)
    print(json.dumps({"self_test_pass": passed, "n_checks": len(ok),
                      "failed": [n for n, v in ok if not v], "tmp": str(tmp)},
                     ensure_ascii=False, indent=2))
    return 0 if passed else 1


# ------------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="P8-BENCH-02 盲化人工相关性判定工具链")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="生成盲化人审包 + key")
    e.add_argument("--questions", required=True)
    e.add_argument("--split", required=True, choices=["development", "holdout"])
    e.add_argument("--outdir", required=True)
    e.add_argument("--keydir")
    e.add_argument("--n", type=int, default=20, help="校准题数（Dev 20 / Holdout 10）")
    e.add_argument("--seed", default=DEFAULT_SEED)
    e.add_argument("--topn", type=int, default=50)
    e.add_argument("--per-view-k", type=int, default=6)
    e.add_argument("--max-candidates", type=int, default=20)
    e.add_argument("--text-chars", type=int, default=600)
    e.add_argument("--pool-audit", help="可选的 pool_audit json（用于把池内 FN 候选纳入待判集合）")
    e.add_argument("--allow-repo-holdout", action="store_true")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import", help="导入人工判定 → 人工 gold + freeze")
    i.add_argument("--judgments", required=True)
    i.add_argument("--key", required=True)
    i.add_argument("--questions", required=True)
    i.add_argument("--split", required=True, choices=["development", "holdout"])
    i.add_argument("--adjudication-out")
    i.add_argument("--gold-out")
    i.add_argument("--freeze-out")
    i.add_argument("--require-complete", action="store_true")
    i.add_argument("--allow-repo-holdout", action="store_true")
    i.set_defaults(func=cmd_import)

    r = sub.add_parser("report", help="auto_prelabel vs 人工分歧 + 人审池 recall")
    r.add_argument("--judgments", required=True)
    r.add_argument("--key", required=True)
    r.add_argument("--split", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--md")
    r.add_argument("--recall-k", type=int, default=20)
    r.set_defaults(func=cmd_report)

    s = sub.add_parser("self-test", help="无 GPU 确定性自检")
    s.set_defaults(func=cmd_self_test)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
