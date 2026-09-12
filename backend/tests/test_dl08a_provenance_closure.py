from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.cognition import CognitionContextItem
from app.research.return_candidates import (
    ResearchReturnBatchInput,
    ResearchReturnBatchRecord,
    ResearchReturnCandidateInput,
    ResearchReturnCandidateService,
    close_candidate_provenance,
)
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence

E1 = "M01:s1:c1"
E2 = "M02:s1:c1"
E3 = "M03:s1:c1"
OUTSIDE = "M99:s1:c1"


def _result() -> ResultEnvelope:
    return ResultEnvelope.model_validate(
        {
            "schema_version": "1.0",
            "task_id": "task-provenance",
            "task_type": "causal_synthesis",
            "query": "deterministic provenance closure",
            "summary": "test",
            "claims": [
                {
                    "id": "claim_001",
                    "text": "claim one",
                    "epistemic_state": "supported",
                    "evidence_refs": [E2, E1],
                },
                {
                    "id": "claim_002",
                    "text": "claim two",
                    "epistemic_state": "inference",
                    "evidence_refs": [E3],
                },
            ],
            "tensions": [
                {
                    "id": "tension_001",
                    "text": "tension one",
                    "evidence_refs": [E3, E2],
                }
            ],
            "uncertainties": [],
            "open_questions": ["what changes the conclusion?"],
            "additional_evidence_needed": [
                {"question": "what else?", "reason": "bounded evidence gap"}
            ],
            "worker": {"tool": "codex", "model": "test"},
            "generated_at": "2026-09-12T12:00:00+08:00",
        }
    )


def _evidence() -> list[TaskPackEvidence]:
    return [
        TaskPackEvidence(
            evidence_id=f"EV{index:03d}",
            source_type="report",
            document_id=f"M0{index}",
            chunk_id=chunk_id,
            content_hash=f"hash-{index}",
        )
        for index, chunk_id in enumerate([E1, E2, E3], start=1)
    ]


def _context() -> list[CognitionContextItem]:
    return [
        CognitionContextItem(
            context_id="CTX001",
            object_type="judgment",
            object_id="cog:j-income",
            content_hash="catalog-sha",
            title="Income judgment",
            excerpt="snapshot",
        )
    ]


def _candidate(
    evidence_chunk_ids: list[str] | None = None,
    **updates,
) -> ResearchReturnCandidateInput:
    payload = {
        "intent": "revise_judgment",
        "target_cognition_object_ids": ["cog:j-income"],
        "proposed_text": "Keep the Worker-authored proposed text exactly.",
        "reason": "Keep the Worker-authored reason exactly.",
        "evidence_chunk_ids": evidence_chunk_ids or [E1],
        "source_claim_ids": ["claim_001", "claim_002"],
        "source_tension_ids": ["tension_001"],
        "source_open_question_indexes": [0],
        "source_additional_evidence_indexes": [0],
        "proposer": "external_worker",
    }
    payload.update(updates)
    return ResearchReturnCandidateInput.model_validate(payload)


class _MemoryService(ResearchReturnCandidateService):
    def __init__(
        self,
        result: ResultEnvelope,
        evidence: list[TaskPackEvidence],
        context: list[CognitionContextItem],
    ) -> None:
        self.cfg = None
        self.importer = None
        self.cognition_docs = None
        self.cognition_chunks = None
        self._result = result
        self._evidence = evidence
        self._context = context
        self._record = ResearchReturnBatchRecord(
            task_id=result.task_id,
            updated_at="2026-09-12T12:00:00+08:00",
        )

    def _validated_task(self, task_id: str):
        assert task_id == self._result.task_id
        return Path("."), self._result, self._evidence, self._context

    def _read_batch(self, pack: Path, task_id: str) -> ResearchReturnBatchRecord:
        assert task_id == self._result.task_id
        return self._record.model_copy(deep=True)

    def _write_batch(self, pack: Path, record: ResearchReturnBatchRecord) -> None:
        self._record = record.model_copy(deep=True)


def test_complete_candidate_is_logically_unchanged():
    original = _candidate([E1, E2, E3])
    normalized, added = close_candidate_provenance(
        original,
        result=_result(),
        allowed_evidence={E1, E2, E3},
    )
    assert normalized.model_dump(mode="json") == original.model_dump(mode="json")
    assert added == []


def test_missing_claim_and_tension_evidence_closes_in_stable_order_and_is_idempotent():
    original = _candidate([E1, E1])
    normalized, added = close_candidate_provenance(
        original,
        result=_result(),
        allowed_evidence={E1, E2, E3},
    )
    assert normalized.evidence_chunk_ids == [E1, E2, E3]
    assert added == [E2, E3]
    assert normalized.proposed_text == original.proposed_text
    assert normalized.reason == original.reason
    assert normalized.intent == original.intent
    assert normalized.target_cognition_object_ids == original.target_cognition_object_ids
    assert normalized.source_claim_ids == original.source_claim_ids
    assert normalized.source_tension_ids == original.source_tension_ids
    assert normalized.source_open_question_indexes == original.source_open_question_indexes
    assert (
        normalized.source_additional_evidence_indexes
        == original.source_additional_evidence_indexes
    )

    repeated, repeated_added = close_candidate_provenance(
        normalized,
        result=_result(),
        allowed_evidence={E1, E2, E3},
    )
    assert repeated.model_dump(mode="json") == normalized.model_dump(mode="json")
    assert repeated_added == []


def test_invalid_source_refs_and_indexes_remain_fail_closed():
    with pytest.raises(ValueError, match="source claim not found"):
        close_candidate_provenance(
            _candidate([E1], source_claim_ids=["claim_missing"]),
            result=_result(),
            allowed_evidence={E1, E2, E3},
        )

    with pytest.raises(ValueError, match="open_question index outside"):
        close_candidate_provenance(
            _candidate([E1], source_open_question_indexes=[1]),
            result=_result(),
            allowed_evidence={E1, E2, E3},
        )


def test_candidate_and_derived_evidence_outside_taskpack_remain_rejected():
    with pytest.raises(ValueError, match="outside TaskPack"):
        close_candidate_provenance(
            _candidate([E1, OUTSIDE]),
            result=_result(),
            allowed_evidence={E1, E2, E3},
        )

    result = _result()
    result.claims[0].evidence_refs = [OUTSIDE]
    with pytest.raises(ValueError, match="outside TaskPack"):
        close_candidate_provenance(
            _candidate([E1]),
            result=result,
            allowed_evidence={E1, E2, E3},
        )


def test_unknown_noncontract_source_shape_is_ignored_without_guessing():
    raw = _candidate([E1]).model_dump(mode="json")
    raw["source_magic_refs"] = [OUTSIDE]
    parsed = ResearchReturnCandidateInput.model_validate(raw)
    normalized, _added = close_candidate_provenance(
        parsed,
        result=_result(),
        allowed_evidence={E1, E2, E3},
    )
    assert OUTSIDE not in normalized.evidence_chunk_ids
    assert "source_magic_refs" not in normalized.model_dump(mode="json")


def test_staging_uses_closed_candidate_logs_added_evidence_and_retries_idempotently(caplog):
    service = _MemoryService(_result(), _evidence(), _context())
    original = _candidate([E1])

    with caplog.at_level(logging.INFO, logger="app.research.return_candidates"):
        first, created, reused = service.ingest(
            "task-provenance",
            ResearchReturnBatchInput(candidates=[original]),
        )

    assert created == 1 and reused == 0
    staged = first.candidates[0]
    assert staged.evidence_chunk_ids == [E1, E2, E3]
    assert staged.proposed_text == original.proposed_text
    assert staged.reason == original.reason
    assert staged.intent == original.intent
    assert staged.target_cognition_object_ids == original.target_cognition_object_ids
    assert staged.source_claim_ids == original.source_claim_ids
    assert staged.source_tension_ids == original.source_tension_ids
    assert "added_evidence=['M02:s1:c1', 'M03:s1:c1']" in caplog.text

    second, created2, reused2 = service.ingest(
        "task-provenance",
        ResearchReturnBatchInput(candidates=[original]),
    )
    assert created2 == 0 and reused2 == 1
    assert second.candidates[0].candidate_id == staged.candidate_id
    assert second.candidates[0].evidence_chunk_ids == staged.evidence_chunk_ids


def test_target_whitespace_difference_is_not_repaired():
    service = _MemoryService(_result(), _evidence(), _context())
    candidate = _candidate([E1], target_cognition_object_ids=["cog:j-income "])
    with pytest.raises(ValueError, match="not selected into this TaskPack"):
        service.ingest(
            "task-provenance",
            ResearchReturnBatchInput(candidates=[candidate]),
        )


def test_malformed_worker_result_remains_schema_rejected():
    raw = _result().model_dump(mode="json")
    raw["claims"] = "not-an-array"
    with pytest.raises(ValidationError):
        ResultEnvelope.model_validate(raw)
