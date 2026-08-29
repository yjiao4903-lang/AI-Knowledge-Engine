"""Evaluation API（M10，spec §35）。"""

from __future__ import annotations

import json
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/latest")
def evaluation_latest(request: Request) -> dict:
    root = Path(request.app.state.cfg.paths.data_dir).parent
    results = root / "data" / "m9_results.json"
    md = root / "docs" / "M9_GOLDEN_EVALUATION.md"
    if not results.exists():
        raise HTTPException(status_code=404, detail="尚无评测结果（运行 backend/scripts/m9_eval.py）")
    return {
        "results": json.loads(results.read_text(encoding="utf-8")),
        "report_markdown": md.read_text(encoding="utf-8") if md.exists() else None,
    }


def _resolve_golden(conn, items):
    out = []
    for it in items:
        rows = conn.execute(
            "SELECT id FROM sections WHERE document_id = ? AND (heading LIKE ? OR heading_path LIKE ?)",
            (it["document_id"], f"%{it['heading_contains']}%", f"%{it['heading_contains']}%"),
        ).fetchall()
        for r in rows:
            out.append((r["id"], it["grade"]))
    return out


def _grade_of(section_id: str, golden) -> int:
    matches = [(sid, g) for sid, g in golden
               if section_id == sid or section_id.startswith(sid + ":")]
    return max((g for _, g in matches), default=0)


class EvalRunBody(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    rerank: bool = True


@router.post("/run")
def evaluation_run(body: EvalRunBody, request: Request) -> dict:
    """对 Golden Set 前 N 条执行检索并返回指标（完整评测用 backend/scripts/m9_eval.py）。"""
    app = request.app
    root = Path(app.state.cfg.paths.data_dir).parent
    golden_path = root / "data" / "golden_queries.jsonl"
    if not golden_path.exists():
        raise HTTPException(status_code=404, detail="golden_queries.jsonl 不存在")
    queries = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    queries = queries[: body.limit]

    engine = app.state.engine
    rows = []
    for q in queries:
        golden = _resolve_golden(app.state.conn, q["relevant_sections"])
        if not golden:
            continue
        resp = engine.search(q["query"], mode="hybrid", top_k=10, rerank=body.rerank)
        grades = [_grade_of(r["section_id"], golden) for r in resp["results"]]
        rel = [g >= 2 for g in grades]

        def hit(k):
            return 1 if any(rel[:k]) else 0

        mrr = next((1.0 / i for i, r in enumerate(rel, 1) if r), 0.0)
        dcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(grades, 1))
        ideal = sorted(grades, reverse=True)
        idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1)) or 1.0
        rows.append({"id": q["id"], "type": q["type"], "hit5": hit(5),
                     "mrr": round(mrr, 3), "ndcg": round(dcg / idcg, 3)})

    n = len(rows)
    return {
        "n": n,
        "hit5": round(sum(r["hit5"] for r in rows) / n, 3) if n else 0,
        "mrr10": round(sum(r["mrr"] for r in rows) / n, 3) if n else 0,
        "ndcg10": round(sum(r["ndcg"] for r in rows) / n, 3) if n else 0,
        "detail": rows,
    }
