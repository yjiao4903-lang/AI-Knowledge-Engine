"""KE-owned research-return / cognition-change candidate staging (DL-06A).

This layer expresses how a Gate-passed external research result *might* affect
existing Cognition objects without performing any formal Cognition write. It
captures the TaskPack-time Cognition snapshot, re-reads the current derived
Cognition catalog, and surfaces target-version conflicts before any future
Cognition Preview/Human Apply integration.

Hard boundary: review/acceptance in this module only mutates KE candidate state.
It never calls Cognition Proposal Apply, revision, merge, retract, Topic update,
or writes Cognition Markdown.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.contracts.cognition import CognitionContextItem
from app.storage.repositories.knowledge import ChunkRepository, DocumentRepository
from app.taskpack.importer import COMPLETED, IMPORTED, TaskPackImporter
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence

RETURN_CANDIDATE_SCHEMA_VERSION = "1.0"
ReturnIntent = Literal[
    "new_judgment",
    "add_evidence",
    "revise_judgment",
    "suggest_retract",
    "advance_question",
    "relation_change",
]
ReviewStatus = Literal["proposed", "accepted", "rejected", "deferred"]
TargetVersionState = Literal[
    "unchanged",
    "changed",
    "missing",
    "unavailable",
    "unknown_baseline",
]


class ReturnCandidateStateError(RuntimeError):
    """Raised when TaskPack state cannot legally produce a return candidate."""


class ResearchReturnCandidateInput(BaseModel):
    intent: ReturnIntent
    target_cognition_object_ids: list[str] = Field(default_factory=list, max_length=10)
    proposed_text: str = Field(min_length=1, max_length=16000)
    reason: str = Field(min_length=1, max_length=8000)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=100)
    source_claim_ids: list[str] = Field(default_factory=list, max_length=100)
    source_tension_ids: list[str] = Field(default_factory=list, max_length=100)
    source_open_question_indexes: list[int] = Field(default_factory=list, max_length=100)
    source_additional_evidence_indexes: list[int] = Field(default_factory=list, max_length=100)
    proposer: str = Field(default="external_worker", min_length=1, max_length=100)

    @model_validator(mode="after")
    def _intent_requirements(self):
        if self.intent != "new_judgment" and not self.target_cognition_object_ids:
            raise ValueError(f"{self.intent} requires at least one target Cognition object")
        if self.intent in {
            "new_judgment",
            "add_evidence",
            "revise_judgment",
            "suggest_retract",
            "relation_change",
        } and not self.evidence_chunk_ids:
            raise ValueError(f"{self.intent} requires at least one evidence_chunk_id")
        if self.intent == "advance_question" and not (
            self.evidence_chunk_ids
            or self.source_claim_ids
            or self.source_tension_ids
            or self.source_open_question_indexes
            or self.source_additional_evidence_indexes
        ):
            raise ValueError("advance_question requires a traceable TaskPack result source")
        return self


class ResearchReturnBatchInput(BaseModel):
    candidates: list[ResearchReturnCandidateInput] = Field(min_length=1, max_length=100)


class ReturnCandidateReviewInput(BaseModel):
    status: ReviewStatus
    reason: str | None = Field(default=None, max_length=4000)
    reviewer: str = Field(default="user", min_length=1, max_length=100)


class TargetSnapshot(BaseModel):
    object_id: str
    object_type: str
    baseline_content_hash: str | None = None
    baseline_title: str | None = None
    baseline_excerpt: str | None = None
    current_content_hash: str | None = None
    current_title: str | None = None
    current_excerpt: str | None = None
    version_state: TargetVersionState
    checked_at: str


class ResearchReturnCandidateRecord(ResearchReturnCandidateInput):
    schema_version: str = RETURN_CANDIDATE_SCHEMA_VERSION
    candidate_id: str
    task_id: str
    task_query: str
    result_generated_at: str
    target_snapshots: list[TargetSnapshot] = Field(default_factory=list)
    has_version_conflict: bool = False
    version_check_incomplete: bool = False
    status: ReviewStatus = "proposed"
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str
    formal_preview_supported: bool = False
    formal_apply_supported: bool = False
    formal_write_performed: bool = False


class ResearchReturnBatchRecord(BaseModel):
    schema_version: str = RETURN_CANDIDATE_SCHEMA_VERSION
    task_id: str
    updated_at: str
    candidates: list[ResearchReturnCandidateRecord] = Field(default_factory=list)
    formal_write_performed: bool = False


class ResearchReturnCandidateService:
    FILE_NAME = "return_candidates.json"

    def __init__(self, cfg, report_conn, cognition_conn, importer: TaskPackImporter) -> None:
        self.cfg = cfg
        self.importer = importer
        self.cognition_docs = (
            DocumentRepository(cognition_conn) if cognition_conn is not None else None
        )
        self.cognition_chunks = (
            ChunkRepository(cognition_conn) if cognition_conn is not None else None
        )

    def ingest(
        self,
        task_id: str,
        body: ResearchReturnBatchInput,
    ) -> tuple[ResearchReturnBatchRecord, int, int]:
        pack, result, evidence, cognition_context = self._validated_task(task_id)
        allowed_evidence = {item.chunk_id for item in evidence}
        context_by_id = {item.object_id: item for item in cognition_context}
        claim_by_id = {item.id: item for item in result.claims}
        tension_by_id = {item.id: item for item in result.tensions}

        record = self._read_batch(pack, task_id)
        existing = {item.candidate_id: item for item in record.candidates}
        now = _now()
        created = 0
        reused = 0

        for item in body.candidates:
            self._validate_input(
                item,
                result=result,
                allowed_evidence=allowed_evidence,
                context_by_id=context_by_id,
                claim_by_id=claim_by_id,
                tension_by_id=tension_by_id,
            )
            candidate_id = self._candidate_id(task_id, item)
            snapshots = [self._target_snapshot(context_by_id[object_id]) for object_id in item.target_cognition_object_ids]
            conflict, incomplete = _version_flags(snapshots)
            old = existing.get(candidate_id)
            if old is None:
                candidate = ResearchReturnCandidateRecord(
                    **item.model_dump(),
                    candidate_id=candidate_id,
                    task_id=task_id,
                    task_query=result.query,
                    result_generated_at=result.generated_at,
                    target_snapshots=snapshots,
                    has_version_conflict=conflict,
                    version_check_incomplete=incomplete,
                    created_at=now,
                    updated_at=now,
                    formal_preview_supported=False,
                    formal_apply_supported=False,
                    formal_write_performed=False,
                )
                existing[candidate_id] = candidate
                created += 1
            else:
                # Idempotent retries refresh target-version observations while
                # preserving explicit human review state.
                old.target_snapshots = snapshots
                old.has_version_conflict = conflict
                old.version_check_incomplete = incomplete
                old.updated_at = now
                old.formal_preview_supported = False
                old.formal_apply_supported = False
                old.formal_write_performed = False
                reused += 1

        record.candidates = sorted(existing.values(), key=lambda row: (row.created_at, row.candidate_id))
        record.updated_at = now
        record.formal_write_performed = False
        self._write_batch(pack, record)
        return record, created, reused

    def list_candidates(self, task_id: str) -> ResearchReturnBatchRecord:
        pack = self._require_task_exists(task_id)
        return self._read_batch(pack, task_id)

    def review(
        self,
        task_id: str,
        candidate_id: str,
        body: ReturnCandidateReviewInput,
    ) -> ResearchReturnBatchRecord:
        pack = self._require_task_exists(task_id)
        record = self._read_batch(pack, task_id)
        found = False
        now = _now()
        for candidate in record.candidates:
            if candidate.candidate_id != candidate_id:
                continue
            candidate.status = body.status
            candidate.review_reason = body.reason
            candidate.reviewed_by = body.reviewer
            candidate.reviewed_at = now
            candidate.updated_at = now
            candidate.formal_preview_supported = False
            candidate.formal_apply_supported = False
            candidate.formal_write_performed = False
            found = True
            break
        if not found:
            raise KeyError(f"return candidate not found: {candidate_id}")
        record.updated_at = now
        record.formal_write_performed = False
        self._write_batch(pack, record)
        return record

    def refresh_target_versions(self, task_id: str) -> ResearchReturnBatchRecord:
        pack = self._require_task_exists(task_id)
        _, _, _, cognition_context = self._validated_task(task_id)
        context_by_id = {item.object_id: item for item in cognition_context}
        record = self._read_batch(pack, task_id)
        now = _now()
        for candidate in record.candidates:
            snapshots: list[TargetSnapshot] = []
            for old in candidate.target_snapshots:
                baseline = context_by_id.get(old.object_id)
                if baseline is None:
                    # Candidate file is preserved for auditability, but a target
                    # disappearing from the original TaskPack context is a hard
                    # handoff conflict rather than permission to expand scope.
                    snapshots.append(
                        TargetSnapshot(
                            object_id=old.object_id,
                            object_type=old.object_type,
                            baseline_content_hash=old.baseline_content_hash,
                            baseline_title=old.baseline_title,
                            baseline_excerpt=old.baseline_excerpt,
                            version_state="missing",
                            checked_at=now,
                        )
                    )
                else:
                    snapshots.append(self._target_snapshot(baseline, checked_at=now))
            candidate.target_snapshots = snapshots
            candidate.has_version_conflict, candidate.version_check_incomplete = _version_flags(snapshots)
            candidate.updated_at = now
            candidate.formal_preview_supported = False
            candidate.formal_apply_supported = False
            candidate.formal_write_performed = False
        record.updated_at = now
        record.formal_write_performed = False
        self._write_batch(pack, record)
        return record

    def _validated_task(
        self,
        task_id: str,
    ) -> tuple[Path, ResultEnvelope, list[TaskPackEvidence], list[CognitionContextItem]]:
        pack = self._require_task_exists(task_id)
        status = self.importer.status_of(pack)
        if status not in (COMPLETED, IMPORTED):
            raise ReturnCandidateStateError(
                f"only Gate-ready completed/imported TaskPacks can create return candidates; status={status}"
            )
        report = self.importer.import_task(pack)
        if not report.passed:
            failure = report.first_failure
            detail = f"{failure.name}: {failure.failure}" if failure is not None else "unknown Gate failure"
            raise ReturnCandidateStateError(f"TaskPack Gate failed: {detail}")
        parsed = self.importer._read_result(pack)
        if parsed is None:
            raise ReturnCandidateStateError("validated TaskPack result is unavailable")
        cognition_context = self._read_cognition_context(pack)
        return pack, parsed[0], self.importer._read_evidence(pack), cognition_context

    def _require_task_exists(self, task_id: str) -> Path:
        pack = self.importer.locate(task_id)
        if pack is None:
            raise KeyError(f"task not found: {task_id}")
        return pack

    def _validate_input(
        self,
        item: ResearchReturnCandidateInput,
        *,
        result: ResultEnvelope,
        allowed_evidence: set[str],
        context_by_id: dict[str, CognitionContextItem],
        claim_by_id: dict,
        tension_by_id: dict,
    ) -> None:
        missing_evidence = [chunk_id for chunk_id in item.evidence_chunk_ids if chunk_id not in allowed_evidence]
        if missing_evidence:
            raise ValueError(f"return candidate references evidence outside TaskPack: {missing_evidence[:10]}")

        for object_id in item.target_cognition_object_ids:
            if object_id not in context_by_id:
                raise ValueError(
                    f"target Cognition object was not selected into this TaskPack: {object_id}"
                )

        missing_claims = [claim_id for claim_id in item.source_claim_ids if claim_id not in claim_by_id]
        if missing_claims:
            raise ValueError(f"source claim not found in TaskPack result: {missing_claims[:10]}")
        missing_tensions = [tension_id for tension_id in item.source_tension_ids if tension_id not in tension_by_id]
        if missing_tensions:
            raise ValueError(f"source tension not found in TaskPack result: {missing_tensions[:10]}")

        self._validate_indexes(
            item.source_open_question_indexes,
            len(result.open_questions),
            "open_question",
        )
        self._validate_indexes(
            item.source_additional_evidence_indexes,
            len(result.additional_evidence_needed),
            "additional_evidence_needed",
        )

        candidate_evidence = set(item.evidence_chunk_ids)
        inherited: set[str] = set()
        for claim_id in item.source_claim_ids:
            inherited.update(claim_by_id[claim_id].evidence_refs or [])
        for tension_id in item.source_tension_ids:
            inherited.update(tension_by_id[tension_id].evidence_refs or [])
        missing_inherited = sorted(inherited - candidate_evidence)
        if missing_inherited:
            raise ValueError(
                "candidate must preserve all Evidence refs of its selected source claims/tensions: "
                f"{missing_inherited[:10]}"
            )

    @staticmethod
    def _validate_indexes(indexes: list[int], size: int, label: str) -> None:
        bad = [index for index in indexes if index < 0 or index >= size]
        if bad:
            raise ValueError(f"{label} index outside TaskPack result: {bad[:10]}")

    def _target_snapshot(
        self,
        baseline: CognitionContextItem,
        *,
        checked_at: str | None = None,
    ) -> TargetSnapshot:
        checked = checked_at or _now()
        if self.cognition_docs is None or self.cognition_chunks is None:
            return TargetSnapshot(
                object_id=baseline.object_id,
                object_type=baseline.object_type,
                baseline_content_hash=baseline.content_hash,
                baseline_title=baseline.title,
                baseline_excerpt=baseline.excerpt,
                version_state="unavailable",
                checked_at=checked,
            )

        current = self.cognition_docs.get(baseline.object_id)
        if current is None:
            return TargetSnapshot(
                object_id=baseline.object_id,
                object_type=baseline.object_type,
                baseline_content_hash=baseline.content_hash,
                baseline_title=baseline.title,
                baseline_excerpt=baseline.excerpt,
                version_state="missing",
                checked_at=checked,
            )

        current_hash = current.get("sha256")
        if baseline.content_hash is None:
            state: TargetVersionState = "unknown_baseline"
        elif current_hash == baseline.content_hash:
            state = "unchanged"
        else:
            state = "changed"
        return TargetSnapshot(
            object_id=baseline.object_id,
            object_type=baseline.object_type,
            baseline_content_hash=baseline.content_hash,
            baseline_title=baseline.title,
            baseline_excerpt=baseline.excerpt,
            current_content_hash=current_hash,
            current_title=current.get("title") or current.get("file_name") or baseline.object_id,
            current_excerpt=_join_excerpt(self.cognition_chunks.list_for_document(baseline.object_id), 6000),
            version_state=state,
            checked_at=checked,
        )

    @staticmethod
    def _read_cognition_context(pack: Path) -> list[CognitionContextItem]:
        path = pack / "cognition_context.jsonl"
        if not path.exists():
            return []
        rows: list[CognitionContextItem] = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(CognitionContextItem.model_validate_json(line))
            except Exception as exc:
                raise ReturnCandidateStateError(
                    f"cognition_context.jsonl line {lineno} is invalid: {exc}"
                ) from exc
        return rows

    def _read_batch(self, pack: Path, task_id: str) -> ResearchReturnBatchRecord:
        path = pack / "result" / self.FILE_NAME
        if not path.exists():
            return ResearchReturnBatchRecord(task_id=task_id, updated_at=_now())
        try:
            record = ResearchReturnBatchRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ReturnCandidateStateError(f"cannot parse {self.FILE_NAME}: {exc}") from exc
        if record.task_id != task_id:
            raise ReturnCandidateStateError(
                f"return candidate file task_id mismatch: {record.task_id} != {task_id}"
            )
        return record

    def _write_batch(self, pack: Path, record: ResearchReturnBatchRecord) -> None:
        path = pack / "result" / self.FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _candidate_id(task_id: str, item: ResearchReturnCandidateInput) -> str:
        payload = {"task_id": task_id, "candidate": item.model_dump(mode="json")}
        return "rc_" + _fingerprint(payload)[:16]


def _version_flags(snapshots: list[TargetSnapshot]) -> tuple[bool, bool]:
    conflict = any(item.version_state in {"changed", "missing"} for item in snapshots)
    incomplete = any(item.version_state in {"unavailable", "unknown_baseline"} for item in snapshots)
    return conflict, incomplete


def _join_excerpt(chunks: list[dict], limit: int) -> str:
    text = "\n\n".join((item.get("plain_text") or "").strip() for item in chunks).strip()
    return text[:limit]


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
