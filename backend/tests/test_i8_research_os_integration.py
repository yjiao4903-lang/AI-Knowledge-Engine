from app.contracts.cognition import CognitionContextItem
from app.integration.proposals import build_cognition_proposal_payload
from app.synthesis.schemas import Claim, SynthesisRequest
from app.taskpack.schemas import (
    AdditionalEvidenceNeeded,
    ResultEnvelope,
    TaskPackEvidence,
    Tension,
    WorkerInfo,
)


def _evidence(chunk_id: str = "M04:ch1:o1:0001") -> TaskPackEvidence:
    return TaskPackEvidence(
        evidence_id="EV001",
        source_type="report",
        document_id="M04",
        section_id="ch1",
        chunk_id=chunk_id,
        content_hash="a" * 64,
        title="HBM4",
        heading_path=["第一章", "HBM4"],
        start_line=10,
        end_line=20,
        excerpt="HBM4 evidence snapshot",
    )


def test_synthesis_request_accepts_structured_cognition_context():
    req = SynthesisRequest(
        task_type="summary",
        query="test",
        evidence_refs=[
            {
                "source_type": "report",
                "document_id": "M04",
                "chunk_id": "M04:ch1:o1:0001",
            }
        ],
        cognition_context=[
            {
                "context_id": "CTX001",
                "object_type": "judgment",
                "object_id": "judgment-1",
                "content_hash": "b" * 64,
                "title": "当前判断",
                "excerpt": "existing cognition",
            }
        ],
    )
    assert isinstance(req.cognition_context[0], CognitionContextItem)
    assert req.cognition_context[0].object_id == "judgment-1"


def test_taskpack_result_converts_to_conservative_cognition_proposal():
    chunk_id = "M04:ch1:o1:0001"
    result = ResultEnvelope(
        task_id="task_001",
        task_type="causal_synthesis",
        query="AI CAPEX 如何影响现金流？",
        summary="summary",
        claims=[
            Claim(
                id="claim_001",
                text="CAPEX 上升会压低短期自由现金流。",
                epistemic_state="supported",
                evidence_refs=[chunk_id],
            )
        ],
        tensions=[
            Tension(
                id="tension_001",
                text="投资扩张与短期现金流之间存在张力。",
                evidence_refs=[chunk_id],
            )
        ],
        open_questions=["收入增速能否覆盖折旧增长？"],
        additional_evidence_needed=[
            AdditionalEvidenceNeeded(
                question="需要哪些未来收入数据？",
                reason="现有固定证据没有覆盖未来收入兑现。",
            )
        ],
        worker=WorkerInfo(tool="codex", model="gpt"),
        generated_at="2026-09-01T12:00:00+08:00",
    )

    payload, warnings = build_cognition_proposal_payload(result, [_evidence(chunk_id)])

    assert warnings == []
    assert payload["origin_type"] == "external_llm"
    assert payload["origin_ref"] == "task_001"
    assert len(payload["items"]) == 4

    claim = payload["items"][0]
    assert claim["candidate_type"] == "new_judgment"
    # `supported` is deliberately NOT promoted to verified_fact.
    assert claim["epistemic_state"] == "inference"
    assert chunk_id in claim["sections"]["支持证据"]

    tension = payload["items"][1]
    assert tension["candidate_type"] == "new_tension"
    assert tension["epistemic_state"] == "unknown"

    question = payload["items"][2]
    assert question["candidate_type"] == "new_question"
    assert question["epistemic_state"] == "open_question"


def test_missing_evidence_snapshot_returns_warning_not_fake_source():
    result = ResultEnvelope(
        task_id="task_002",
        task_type="summary",
        query="test",
        claims=[
            Claim(
                id="claim_001",
                text="claim",
                epistemic_state="inference",
                evidence_refs=["missing-chunk"],
            )
        ],
        worker=WorkerInfo(tool="worker"),
        generated_at="2026-09-01T12:00:00+08:00",
    )
    payload, warnings = build_cognition_proposal_payload(result, [])
    assert warnings
    assert "未找到快照" in payload["items"][0]["sections"]["支持证据"]
