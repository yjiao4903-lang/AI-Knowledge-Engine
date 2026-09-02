from app.integration.proposals import build_cognition_proposal_payload
from app.synthesis.epistemic_linter import lint_result
from app.synthesis.schemas import Claim, Tension
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence, WorkerInfo


def _evidence(chunk_id: str, excerpt: str) -> TaskPackEvidence:
    return TaskPackEvidence(
        evidence_id=f"EV-{chunk_id}",
        source_type="report",
        document_id="M04",
        section_id="ch1",
        chunk_id=chunk_id,
        content_hash="a" * 64,
        title="test evidence",
        heading_path=["test"],
        start_line=1,
        end_line=2,
        excerpt=excerpt,
    )


def _result(
    *,
    claim_text: str | None = None,
    state: str = "supported",
    claim_refs: list[str] | None = None,
    tension_refs: list[str] | None = None,
) -> ResultEnvelope:
    claims = []
    if claim_text is not None:
        claims.append(
            Claim(
                id="claim_001",
                text=claim_text,
                epistemic_state=state,
                evidence_refs=claim_refs or ["chunk_1"],
            )
        )

    tensions = []
    if tension_refs is not None:
        tensions.append(
            Tension(
                id="tension_001",
                text="两组证据存在张力。",
                evidence_refs=tension_refs,
            )
        )

    return ResultEnvelope(
        task_id="task_linter",
        task_type="causal_synthesis",
        query="test query",
        summary="summary",
        claims=claims,
        tensions=tensions,
        worker=WorkerInfo(tool="test-worker", model="test-model"),
        generated_at="2026-09-02T12:00:00+08:00",
    )


def _codes(findings) -> set[str]:
    return {finding.code for finding in findings}


def test_forecast_marked_supported_warns():
    result = _result(claim_text="预计 2027E 出货量达到 100 万", state="supported")
    findings = lint_result(result, [_evidence("chunk_1", "当前出货量为 50 万。")])

    assert "FORECAST_MARKED_SUPPORTED" in _codes(findings)
    finding = next(item for item in findings if item.code == "FORECAST_MARKED_SUPPORTED")
    assert finding.severity == "warning"
    assert finding.suggested_state == "inference"


def test_forecast_marked_inference_does_not_warn_as_supported():
    result = _result(claim_text="预计 2027E 出货量达到 100 万", state="inference")
    findings = lint_result(result, [_evidence("chunk_1", "当前出货量为 50 万。")])

    assert "FORECAST_MARKED_SUPPORTED" not in _codes(findings)


def test_causal_strength_without_explicit_causal_evidence_warns():
    result = _result(claim_text="AI 投资导致利润率下降", state="supported")
    evidence = [_evidence("chunk_1", "AI 投资与利润率下降同时出现。")]

    assert "CAUSAL_STRENGTH_UNDERGROUNDED" in _codes(lint_result(result, evidence))


def test_causal_strength_with_explicit_causal_evidence_does_not_warn():
    result = _result(claim_text="AI 投资导致利润率下降", state="supported")
    evidence = [_evidence("chunk_1", "研究结果显示 AI 投资直接导致利润率下降。")]

    assert "CAUSAL_STRENGTH_UNDERGROUNDED" not in _codes(lint_result(result, evidence))


def test_tension_with_one_distinct_evidence_ref_warns():
    result = _result(tension_refs=["chunk_1"])

    assert "TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY" in _codes(
        lint_result(result, [_evidence("chunk_1", "evidence one")])
    )


def test_tension_with_two_distinct_evidence_refs_does_not_warn():
    result = _result(tension_refs=["chunk_1", "chunk_2"])
    evidence = [
        _evidence("chunk_1", "evidence one"),
        _evidence("chunk_2", "evidence two"),
    ]

    assert "TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY" not in _codes(
        lint_result(result, evidence)
    )


def test_lint_result_does_not_mutate_result_envelope():
    result = _result(
        claim_text="预计 2027E AI 投资导致利润率下降",
        state="supported",
        tension_refs=["chunk_1"],
    )
    evidence = [_evidence("chunk_1", "AI 投资与利润率下降同时出现。")]
    before = result.model_dump(mode="json")

    lint_result(result, evidence)

    assert result.model_dump(mode="json") == before
    assert result.claims[0].epistemic_state == "supported"


def test_proposal_includes_lint_warning_without_rewriting_candidate_state():
    result = _result(claim_text="预计 2027E 出货量达到 100 万", state="supported")
    evidence = [_evidence("chunk_1", "当前出货量为 50 万。")]

    payload, warnings = build_cognition_proposal_payload(result, evidence)

    assert any("FORECAST_MARKED_SUPPORTED" in warning for warning in warnings)
    assert "[Research OS Review Warnings]" in payload["description"]
    assert "FORECAST_MARKED_SUPPORTED" in payload["description"]
    # Existing conservative mapping must remain intact: supported never becomes verified_fact.
    assert payload["items"][0]["epistemic_state"] == "inference"
    # Linter is warning-only and must not rewrite the source ResultEnvelope.
    assert result.claims[0].epistemic_state == "supported"
    # Proposal construction is staging-only; no formal apply surface is introduced here.
    assert "apply" not in payload
    assert "auto_apply" not in payload
