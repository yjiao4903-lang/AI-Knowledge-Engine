"""Draft 校验与 L1A 指标计算（主计划 §20-§24）。

自动可算指标（Citation Entailment 需人工，由 harness 记录）：
- schema_valid              ：输出能否被 SynthesisDraft 正确解析（除服务端填充字段）
- citation_valid            ：所有 evidence_refs 都在本次提供的 chunk_id 集合内
- citation_coverage         ：事实性 Claim 中绑定有效 Evidence 的比例（§22, Gate>=95%）
- unsupported_claim_rate    ：事实性 Claim 中无证据支撑的比例（§24, Gate<=5%）
"""

from __future__ import annotations

from typing import Any

from app.synthesis.schemas import FACTUAL_STATES, Claim, SynthesisDraft, Tension


class ValidationReport:
    """L1A 指标报告（用于 Service 日志与 Evaluation Harness）。"""

    __slots__ = (
        "schema_valid",
        "errors",
        "provided_chunk_ids",
        "citation_invalid",
        "factual_claims",
        "cited_factual_claims",
        "unsupported_factual_claims",
        "citation_coverage",
        "unsupported_claim_rate",
        "duplicate_claim_ids",
    )

    def __init__(self) -> None:
        self.schema_valid = True
        self.errors: list[str] = []
        self.provided_chunk_ids: set[str] = set()
        self.citation_invalid: list[str] = []
        self.factual_claims = 0
        self.cited_factual_claims = 0
        self.unsupported_factual_claims = 0
        self.citation_coverage: float | None = None
        self.unsupported_claim_rate: float | None = None
        self.duplicate_claim_ids: list[str] = []

    @property
    def pass_gate(self) -> bool:
        """L1A Gate 中自动部分（§26）：schema 100% + 引用合法性 + 覆盖率/无支撑率阈值
        由评估层按参数判定，此处仅反映是否无阻断性规则失败。"""
        cov_ok = self.citation_coverage is not None and self.citation_coverage >= 0.95
        unsup_ok = self.unsupported_claim_rate is not None and self.unsupported_claim_rate <= 0.05
        leak_ok = not self.citation_invalid and not self.duplicate_claim_ids
        no_peer = self.factual_claims == 0
        return self.schema_valid and cov_ok and unsup_ok and leak_ok and not no_peer


def _collect_refs(claims: list[Claim], tensions: list[Tension]) -> list[str]:
    refs: list[str] = []
    for c in claims:
        refs.extend(getattr(c, "evidence_refs", []) or [])
    for t in tensions:
        refs.extend(getattr(t, "evidence_refs", []) or [])
    return refs


def validate_draft(draft: SynthesisDraft, provided_chunk_ids: set[str]) -> ValidationReport:
    rep = ValidationReport()
    rep.provided_chunk_ids = set(provided_chunk_ids)

    # duplicate claim ids
    seen: dict[str, int] = {}
    for c in draft.claims:
        seen[c.id] = seen.get(c.id, 0) + 1
    rep.duplicate_claim_ids = [k for k, v in seen.items() if v > 1]
    if rep.duplicate_claim_ids:
        rep.errors.append(f"重复 claim id: {rep.duplicate_claim_ids}")
        rep.schema_valid = False

    # citation validity: every ref must be in provided set
    for ref in _collect_refs(draft.claims, draft.tensions):
        if ref not in provided_chunk_ids:
            rep.citation_invalid.append(ref)
    if rep.citation_invalid:
        rep.errors.append(f"引用了未提供的证据: {rep.citation_invalid[:10]}...")

    # factual claims & coverage
    factual = [c for c in draft.claims if c.epistemic_state in FACTUAL_STATES]
    rep.factual_claims = len(factual)
    for c in factual:
        valid_refs = [r for r in (c.evidence_refs or []) if r in provided_chunk_ids]
        if valid_refs:
            rep.cited_factual_claims += 1
        else:
            rep.unsupported_factual_claims += 1
    if rep.factual_claims:
        rep.citation_coverage = rep.cited_factual_claims / rep.factual_claims
        rep.unsupported_claim_rate = rep.unsupported_factual_claims / rep.factual_claims
    return rep


def extract_partial(raw: dict[str, Any]) -> dict[str, Any]:
    """从模型输出的原始 dict 提炼可由模型负责的字段（其余由 service 填充）。"""
    out: dict[str, Any] = {}
    for key in ("claims", "tensions", "uncertainties", "open_questions", "summary"):
        if key in raw:
            out[key] = raw[key]
    return out