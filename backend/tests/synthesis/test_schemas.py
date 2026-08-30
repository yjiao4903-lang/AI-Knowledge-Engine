"""SynthesisDraft Schema V1 + epistemic_state（主计划 §6/§8）。"""

from __future__ import annotations

import pytest

from app.synthesis.schemas import (
    EPISTEMIC_STATES,
    FACTUAL_STATES,
    TASK_TYPES,
    Claim,
    EvidenceRef,
    SynthesisDraft,
)
from pydantic import ValidationError


def test_epistemic_state_enum():
    assert set(EPISTEMIC_STATES) == {
        "supported", "inference", "hypothesis", "uncertain", "contradicted",
    }
    assert FACTUAL_STATES == ("supported", "inference", "hypothesis", "contradicted")


def test_task_types():
    assert set(TASK_TYPES) == {
        "summary", "comparison", "causal_synthesis", "tension_extraction",
    }


def test_evidence_ref_chunk_id_required():
    with pytest.raises(ValidationError):
        EvidenceRef(source_type="report", document_id="M04", chunk_id="  ")


def test_evidence_ref_valid():
    ref = EvidenceRef(
        source_type="report", document_id="M04", section_id="ch1",
        chunk_id="M04:ch1:0001", content_hash="abc", evidence_level=2,
    )
    assert ref.schema_version == "1.0"
    assert ref.chunk_id == "M04:ch1:0001"
    assert ref.evidence_level == 2


def test_claim_epistemic_literal():
    with pytest.raises(ValidationError):
        Claim(id="c1", text="x", epistemic_state="no_such_state")
    c = Claim(id="c1", text="HBM4 位宽提高", epistemic_state="supported", evidence_refs=["E1"])
    assert c.epistemic_state == "supported"


def test_full_draft_roundtrip():
    draft = SynthesisDraft.model_validate({
        "id": "synthesis_x",
        "task_type": "summary",
        "query": "q",
        "created_at": "2026-08-30T10:00:00Z",
        "generator": {"provider": "mock", "model": "m", "prompt_version": "v1"},
        "evidence": [{"source_type": "report", "document_id": "M04",
                      "chunk_id": "M04:ch1:0001"}],
        "claims": [{"id": "claim_001", "text": "t", "epistemic_state": "supported",
                    "evidence_refs": ["M04:ch1:0001"]}],
        "tensions": [],
        "uncertainties": [],
        "open_questions": [],
        "summary": "s",
    })
    assert draft.schema_version == "1.0"
    assert draft.status == "draft"
    assert draft.claims[0].evidence_refs == ["M04:ch1:0001"]


def test_bad_task_type_rejected():
    with pytest.raises(ValidationError):
        SynthesisDraft.model_validate({
            "id": "s1", "task_type": "agent_research", "query": "q",
            "created_at": "x", "generator": {"provider": "m", "model": "m", "prompt_version": "v"},
        })