"""Deterministic epistemic lint for TaskPack synthesis results.

This is a lightweight guardrail, not semantic entailment. It catches a small set
of recurrent overclaim patterns observed in external TaskPack evaluation:

- forecasts / estimates marked as `supported`;
- strong causal wording without similarly explicit causal wording in cited
  Evidence snapshots;
- tensions represented with fewer than two distinct Evidence references.

Findings are warnings by default. The linter never rewrites a claim and never
promotes/demotes formal Cognition state automatically.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence


_FORECAST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("future_estimate_year", re.compile(r"\b20\d{2}E\b", re.IGNORECASE)),
    ("forecast_zh", re.compile(r"预计|预测|有望|目标|基准情景|情景假设|未来(?:几年|年度|年)?|市场份额预期|市场空间预期")),
    ("forecast_en", re.compile(r"\b(?:forecast|estimate|estimated|guidance|target|scenario|projected|expected)\b", re.IGNORECASE)),
    ("tam", re.compile(r"\bTAM\b|total addressable market", re.IGNORECASE)),
)

_CAUSAL_PATTERN = re.compile(
    r"导致|直接导致|造成|决定|驱动|必然|因此使|使得|"
    r"\b(?:directly causes|causes|drives|results in|leads to|determines)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LintFinding:
    code: str
    severity: str
    object_type: str
    object_id: str
    message: str
    suggested_state: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data

    def display(self) -> str:
        return f"{self.code} [{self.object_id}]: {self.message}"


def _has_forecast_marker(text: str) -> str | None:
    for name, pattern in _FORECAST_PATTERNS:
        if pattern.search(text or ""):
            return name
    return None


def _evidence_text(refs: list[str], by_chunk: dict[str, TaskPackEvidence]) -> str:
    return "\n".join(
        (by_chunk[ref].excerpt or "")
        for ref in refs
        if ref in by_chunk
    )


def lint_result(
    result: ResultEnvelope,
    evidence: list[TaskPackEvidence],
) -> list[LintFinding]:
    """Return deterministic warning findings for a validated ResultEnvelope."""

    by_chunk = {item.chunk_id: item for item in evidence}
    findings: list[LintFinding] = []

    for claim in result.claims:
        if claim.epistemic_state == "supported":
            marker = _has_forecast_marker(claim.text)
            if marker:
                findings.append(
                    LintFinding(
                        code="FORECAST_MARKED_SUPPORTED",
                        severity="warning",
                        object_type="claim",
                        object_id=claim.id,
                        message=(
                            f"claim 含预测/估算/目标标记（{marker}），但 epistemic_state=supported；"
                            "应保留未来/估算口径并人工复核为 inference/hypothesis/uncertain。"
                        ),
                        suggested_state="inference",
                        evidence_refs=tuple(claim.evidence_refs),
                    )
                )

        if claim.epistemic_state in {"supported", "inference"} and _CAUSAL_PATTERN.search(claim.text):
            cited_text = _evidence_text(claim.evidence_refs, by_chunk)
            if not _CAUSAL_PATTERN.search(cited_text):
                findings.append(
                    LintFinding(
                        code="CAUSAL_STRENGTH_UNDERGROUNDED",
                        severity="warning",
                        object_type="claim",
                        object_id=claim.id,
                        message=(
                            "claim 使用强因果措辞，但当前引用 Evidence 快照中未检测到显式强因果表述；"
                            "请人工核对是否把相关性、并列描述或时间顺序升级成了因果。"
                        ),
                        suggested_state="inference" if claim.epistemic_state == "supported" else None,
                        evidence_refs=tuple(claim.evidence_refs),
                    )
                )

    for tension in result.tensions:
        unique_refs = tuple(dict.fromkeys(tension.evidence_refs))
        if len(unique_refs) < 2:
            findings.append(
                LintFinding(
                    code="TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY",
                    severity="warning",
                    object_type="tension",
                    object_id=tension.id,
                    message=(
                        "tension 少于 2 条不同 Evidence 引用；张力/冲突通常需要至少两个独立证据方向，"
                        "否则应人工确认是否只是单一证据的不确定性。"
                    ),
                    evidence_refs=unique_refs,
                )
            )

    return findings
