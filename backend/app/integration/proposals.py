"""Convert a validated TaskPack result into a Cognition Proposal candidate batch.

TaskPack result -> Proposal candidate. Formal Cognition changes still require the
Cognition control plane's Preview + Human Apply.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.synthesis.epistemic_linter import lint_result
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence

GROUNDING_TO_COGNITION = {
    "supported": "inference",
    "inference": "inference",
    "hypothesis": "hypothesis",
    "uncertain": "unknown",
    "contradicted": "counterexample",
}

GROUNDING_TO_CONFIDENCE = {
    "supported": "medium",
    "inference": "medium",
    "hypothesis": "low",
    "uncertain": "low",
    "contradicted": "medium",
}


def _truncate_title(text: str, limit: int = 72) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _evidence_markdown(refs: Iterable[str], by_chunk: dict[str, TaskPackEvidence]) -> str:
    lines: list[str] = []
    for chunk_id in refs:
        ev = by_chunk.get(chunk_id)
        if ev is None:
            lines.append(f"- `{chunk_id}`（TaskPack 中未找到快照；需人工核验）")
            continue
        heading = " > ".join(ev.heading_path) if ev.heading_path else (ev.title or ev.document_id)
        line_range = ""
        if ev.start_line is not None or ev.end_line is not None:
            line_range = f" · L{ev.start_line or '?'}-L{ev.end_line or '?'}"
        lines.append(
            f"- `{ev.chunk_id}` · {ev.document_id} · {heading}{line_range}"
            + (f"\n  - 摘要：{ev.excerpt}" if ev.excerpt else "")
        )
    return "\n".join(lines) if lines else "（无直接 Evidence 引用）"


def _source_markdown(result: ResultEnvelope, grounding_state: str, refs_md: str) -> str:
    worker = result.worker.tool
    if result.worker.model:
        worker += f" / {result.worker.model}"
    return (
        f"- TaskPack：`{result.task_id}`\n"
        f"- Worker：{worker}\n"
        f"- Task grounding_state：`{grounding_state}`\n"
        f"- 生成时间：{result.generated_at}\n"
        f"- Evidence：\n{refs_md}"
    )


def build_cognition_proposal_payload(
    result: ResultEnvelope,
    evidence: list[TaskPackEvidence],
) -> tuple[dict, list[str]]:
    """Return a Cognition `/api/proposals` compatible candidate and warnings.

    Warnings include deterministic epistemic lint findings. They never rewrite
    the result and do not by themselves apply any formal cognition change.
    """

    by_chunk = {item.chunk_id: item for item in evidence}
    warnings: list[str] = []
    items: list[dict] = []

    for claim in result.claims:
        refs_md = _evidence_markdown(claim.evidence_refs, by_chunk)
        if any(ref not in by_chunk for ref in claim.evidence_refs):
            warnings.append(f"claim {claim.id} 包含 TaskPack 快照中不存在的 evidence ref")
        cognition_state = GROUNDING_TO_COGNITION[claim.epistemic_state]
        contradicted = claim.epistemic_state == "contradicted"
        items.append(
            {
                "title": _truncate_title(claim.text),
                "candidate_type": "new_judgment",
                "epistemic_state": cognition_state,
                "suggested_action": "create",
                "confidence": GROUNDING_TO_CONFIDENCE[claim.epistemic_state],
                "sections": {
                    "内容": claim.text,
                    "支持证据": "" if contradicted else refs_md,
                    "反方证据": refs_md if contradicted else "",
                    "什么会证明它错": "需在 Cognition Proposal Preview 中补充/确认。",
                    "来源定位": _source_markdown(result, claim.epistemic_state, refs_md),
                },
            }
        )

    for tension in result.tensions:
        refs_md = _evidence_markdown(tension.evidence_refs, by_chunk)
        if any(ref not in by_chunk for ref in tension.evidence_refs):
            warnings.append(f"tension {tension.id} 包含 TaskPack 快照中不存在的 evidence ref")
        items.append(
            {
                "title": _truncate_title(tension.text),
                "candidate_type": "new_tension",
                "epistemic_state": "unknown",
                "confidence": "low",
                "sections": {
                    "内容": tension.text,
                    "支持证据": refs_md,
                    "反方证据": refs_md,
                    "什么会证明它错": "需通过后续证据或判别指标化解该张力。",
                    "来源定位": _source_markdown(result, "tension", refs_md),
                },
            }
        )

    for question in result.open_questions:
        items.append(
            {
                "title": _truncate_title(question),
                "candidate_type": "new_question",
                "epistemic_state": "open_question",
                "suggested_action": "create",
                "confidence": "low",
                "sections": {
                    "内容": question,
                    "支持证据": "",
                    "反方证据": "",
                    "什么会证明它错": "",
                    "来源定位": _source_markdown(
                        result, "open_question", "（来自 TaskPack open_questions）"
                    ),
                },
            }
        )

    for gap in result.additional_evidence_needed:
        items.append(
            {
                "title": _truncate_title(gap.question),
                "candidate_type": "new_question",
                "epistemic_state": "open_question",
                "suggested_action": "create",
                "confidence": "low",
                "sections": {
                    "内容": gap.question,
                    "支持证据": "",
                    "反方证据": "",
                    "什么会证明它错": "",
                    "来源定位": (
                        _source_markdown(result, "additional_evidence_needed", "（证据缺口）")
                        + f"\n- 缺口原因：{gap.reason}"
                    ),
                },
            }
        )

    if result.uncertainties:
        warnings.extend(f"TaskPack uncertainty: {item}" for item in result.uncertainties)

    # Deterministic guardrail: warning only. Human review remains authoritative.
    warnings.extend(finding.display() for finding in lint_result(result, evidence))

    worker = result.worker.tool
    if result.worker.model:
        worker += f":{result.worker.model}"

    payload = {
        "title": f"TaskPack 研究结算：{_truncate_title(result.query, 48)}",
        "origin_type": "external_llm",
        "origin_ref": result.task_id,
        "origin_title": result.query,
        "generator": worker,
        "description": result.summary,
        "topics": [],
        "items": items,
    }
    return payload, warnings
