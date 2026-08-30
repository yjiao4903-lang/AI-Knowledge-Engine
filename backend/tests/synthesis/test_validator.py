"""Validator：L1A 指标计算（主计划 §20-§24）。"""

from __future__ import annotations

from app.synthesis.schemas import SynthesisDraft
from app.synthesis.validator import validate_draft


def _draft(claims, *, tensions=None):
    return SynthesisDraft.model_validate({
        "id": "s1", "task_type": "summary", "query": "q",
        "created_at": "x", "generator": {"provider": "m", "model": "m", "prompt_version": "v"},
        "evidence": [], "claims": claims, "tensions": tensions or [],
        "uncertainties": [], "open_questions": [], "summary": "s",
    })


def test_coverage_all_cited():
    d = _draft([{"id": "c1", "text": "a", "epistemic_state": "supported",
                 "evidence_refs": ["E1"]},
                {"id": "c2", "text": "b", "epistemic_state": "inference",
                 "evidence_refs": ["E1", "E2"]}])
    rep = validate_draft(d, {"E1", "E2"})
    assert rep.schema_valid
    assert rep.factual_claims == 2
    assert rep.citation_coverage == 1.0
    assert rep.unsupported_claim_rate == 0.0
    assert rep.pass_gate


def test_unsupported_and_invalid_citations_countdown():
    d = _draft([{"id": "c1", "text": "a", "epistemic_state": "supported",
                 "evidence_refs": []},
                {"id": "c2", "text": "b", "epistemic_state": "supported",
                 "evidence_refs": ["FABRICATED_ID"]}])
    rep = validate_draft(d, {"E1", "E2"})
    assert rep.factual_claims == 2
    assert rep.cited_factual_claims == 0
    assert rep.citation_coverage == 0.0
    assert rep.unsupported_claim_rate == 1.0
    assert "FABRICATED_ID" in rep.citation_invalid
    assert not rep.pass_gate


def test_inference_needs_citation_too():
    # inference 也属于事实性断言，必须绑定证据
    d = _draft([{"id": "c1", "text": "推测", "epistemic_state": "inference",
                 "evidence_refs": []}])
    rep = validate_draft(d, {"E1"})
    assert rep.unsupported_claim_rate == 1.0


def test_uncertain_not_counted_as_factual():
    d = _draft([{"id": "c1", "text": "不确定", "epistemic_state": "uncertain",
                 "evidence_refs": []}])
    rep = validate_draft(d, {"E1"})
    assert rep.factual_claims == 0
    assert rep.citation_coverage is None
    assert rep.unsupported_claim_rate is None


def test_duplicate_claim_ids_invalidate():
    d = _draft([{"id": "c1", "text": "a", "epistemic_state": "supported", "evidence_refs": ["E1"]},
                {"id": "c1", "text": "b", "epistemic_state": "supported", "evidence_refs": ["E1"]}])
    rep = validate_draft(d, {"E1"})
    assert not rep.schema_valid
    assert rep.duplicate_claim_ids == ["c1"]


def test_tension_citations_validated():
    d = _draft([], tensions=[{"id": "t1", "text": "矛盾", "evidence_refs": ["GHOST"]}])
    rep = validate_draft(d, {"E1"})
    assert "GHOST" in rep.citation_invalid