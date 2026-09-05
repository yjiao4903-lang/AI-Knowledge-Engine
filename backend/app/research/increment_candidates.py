"""Durable report-increment and relationship candidate layer (DL-04).

These records are KE-owned review artifacts. They are neither formal Cognition
objects nor evidence of truth. Candidate acceptance only changes candidate review
state; it never writes Cognition Markdown or calls Proposal Apply/Revision APIs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.research.dossier import TopicDossierService
from app.storage.repositories.knowledge import ChunkRepository, DocumentRepository

INCREMENT_ANALYSIS_SCHEMA_VERSION = "1.0"
IncrementClass = Literal[
    "new_insight",
    "additional_evidence",
    "potential_conflict",
    "condition_change",
    "duplicate",
    "cannot_determine",
]
RelationType = Literal[
    "topic_related",
    "concept_dependency",
    "mechanism_hypothesis",
    "supports",
    "opposes",
    "condition_limits",
    "analogy",
]
ReviewStatus = Literal["proposed", "accepted", "rejected", "deferred"]
ObjectKind = Literal["report_evidence", "cognition"]


class ResearchObjectRef(BaseModel):
    kind: ObjectKind
    object_id: str = Field(min_length=1)


class IncrementCandidateInput(BaseModel):
    classification: IncrementClass
    title: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=8000)
    difference_reason: str = Field(min_length=1, max_length=8000)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=50)
    target_cognition_object_ids: list[str] = Field(default_factory=list, max_length=50)
    scope: str | None = Field(default=None, max_length=4000)
    proposer: str = Field(default="external_worker", min_length=1, max_length=100)

    @model_validator(mode="after")
    def _grounding_requirements(self):
        if self.classification != "cannot_determine" and not self.evidence_chunk_ids:
            raise ValueError(f"{self.classification} requires at least one evidence_chunk_id")
        if self.classification in {
            "additional_evidence",
            "potential_conflict",
            "condition_change",
            "duplicate",
        } and not self.target_cognition_object_ids:
            raise ValueError(
                f"{self.classification} requires at least one target Cognition object"
            )
        return self


class RelationshipCandidateInput(BaseModel):
    relation_type: RelationType
    source: ResearchObjectRef
    target: ResearchObjectRef
    explanation: str = Field(min_length=1, max_length=8000)
    evidence_chunk_ids: list[str] = Field(min_length=1, max_length=50)
    scope: str | None = Field(default=None, max_length=4000)
    proposer: str = Field(default="external_worker", min_length=1, max_length=100)

    @model_validator(mode="after")
    def _not_self_relation(self):
        if self.source == self.target:
            raise ValueError("relationship source and target must differ")
        return self


class IncrementAnalysisInput(BaseModel):
    source_report_document_id: str = Field(min_length=1)
    analysis_run_key: str | None = Field(default=None, max_length=200)
    task_id: str | None = Field(default=None, max_length=200)
    coverage_note: str | None = Field(default=None, max_length=8000)
    increments: list[IncrementCandidateInput] = Field(default_factory=list, max_length=100)
    relationships: list[RelationshipCandidateInput] = Field(default_factory=list, max_length=100)


class CandidateReviewInput(BaseModel):
    status: ReviewStatus
    reason: str | None = Field(default=None, max_length=4000)
    reviewer: str = Field(default="user", min_length=1, max_length=100)


class IncrementCandidateRecord(IncrementCandidateInput):
    candidate_id: str
    status: ReviewStatus = "proposed"
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class RelationshipCandidateRecord(RelationshipCandidateInput):
    candidate_id: str
    status: ReviewStatus = "proposed"
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class IncrementAnalysisRecord(BaseModel):
    schema_version: str = INCREMENT_ANALYSIS_SCHEMA_VERSION
    analysis_id: str
    dossier_id: str
    source_report_document_id: str
    source_report_content_hash: str | None = None
    analysis_run_key: str | None = None
    task_id: str | None = None
    coverage_note: str | None = None
    created_at: str
    updated_at: str
    increments: list[IncrementCandidateRecord] = Field(default_factory=list)
    relationships: list[RelationshipCandidateRecord] = Field(default_factory=list)
    formal_write_performed: bool = False


class IncrementCandidateService:
    def __init__(self, cfg, report_conn, cognition_conn) -> None:
        self.cfg = cfg
        self.report_docs = DocumentRepository(report_conn)
        self.report_chunks = ChunkRepository(report_conn)
        self.cognition_docs = (
            DocumentRepository(cognition_conn) if cognition_conn is not None else None
        )
        self.cognition_chunks = (
            ChunkRepository(cognition_conn) if cognition_conn is not None else None
        )
        self.dossiers = TopicDossierService(cfg, report_conn, cognition_conn)
        self.root = Path(cfg.paths.data_dir) / "research_dossiers"

    def ingest(self, dossier_id: str, body: IncrementAnalysisInput) -> tuple[IncrementAnalysisRecord, bool]:
        # A valid dossier must already exist. This keeps candidate artifacts scoped
        # to an explicit user research direction rather than creating hidden topics.
        try:
            dossier = self.dossiers.get(dossier_id)
        except KeyError as exc:
            raise KeyError(f"dossier not found: {dossier_id}") from exc

        report = self.report_docs.get(body.source_report_document_id)
        if report is None:
            raise ValueError(f"source report not found: {body.source_report_document_id}")
        report_hash = report.get("sha256")
        analysis_id = self._analysis_id(
            dossier_id,
            body.source_report_document_id,
            report_hash,
            body.analysis_run_key,
        )
        path = self._analysis_path(dossier_id, analysis_id)
        if path.exists():
            return self._read(path), True

        allowed_cognition = self._dossier_cognition_ids(dossier)
        increments = self._validate_increment_candidates(body.increments, allowed_cognition)
        relationships = self._validate_relationships(body.relationships)
        now = _now()
        record = IncrementAnalysisRecord(
            analysis_id=analysis_id,
            dossier_id=dossier_id,
            source_report_document_id=body.source_report_document_id,
            source_report_content_hash=report_hash,
            analysis_run_key=body.analysis_run_key,
            task_id=body.task_id,
            coverage_note=body.coverage_note,
            created_at=now,
            updated_at=now,
            increments=increments,
            relationships=relationships,
            formal_write_performed=False,
        )
        self._atomic_write(path, record)
        return record, False

    def list_analyses(self, dossier_id: str) -> list[IncrementAnalysisRecord]:
        try:
            self.dossiers.get(dossier_id)
        except KeyError as exc:
            raise KeyError(f"dossier not found: {dossier_id}") from exc
        directory = self._dir(dossier_id)
        if not directory.exists():
            return []
        records: list[IncrementAnalysisRecord] = []
        for path in sorted(directory.glob("*.json")):
            try:
                records.append(self._read(path))
            except Exception:
                continue
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def get(self, dossier_id: str, analysis_id: str) -> IncrementAnalysisRecord:
        path = self._analysis_path(dossier_id, analysis_id)
        if not path.exists():
            raise KeyError(f"analysis not found: {analysis_id}")
        return self._read(path)

    def review(
        self,
        dossier_id: str,
        analysis_id: str,
        candidate_id: str,
        review: CandidateReviewInput,
    ) -> IncrementAnalysisRecord:
        path = self._analysis_path(dossier_id, analysis_id)
        record = self.get(dossier_id, analysis_id)
        found = False
        now = _now()
        for collection in (record.increments, record.relationships):
            for candidate in collection:
                if candidate.candidate_id != candidate_id:
                    continue
                candidate.status = review.status
                candidate.review_reason = review.reason
                candidate.reviewed_by = review.reviewer
                candidate.reviewed_at = now
                found = True
        if not found:
            raise KeyError(f"candidate not found: {candidate_id}")
        record.updated_at = now
        # Review only mutates KE candidate state. The formal-write bit is a hard
        # invariant that makes accidental future boundary drift visible in tests.
        record.formal_write_performed = False
        self._atomic_write(path, record)
        return record

    def _validate_increment_candidates(
        self,
        items: list[IncrementCandidateInput],
        allowed_cognition: set[str],
    ) -> list[IncrementCandidateRecord]:
        result: list[IncrementCandidateRecord] = []
        seen: set[str] = set()
        for item in items:
            self._validate_evidence_ids(item.evidence_chunk_ids)
            for object_id in item.target_cognition_object_ids:
                self._validate_cognition_id(object_id)
                if object_id not in allowed_cognition:
                    raise ValueError(
                        f"target Cognition object is outside dossier scope: {object_id}"
                    )
            candidate_id = "inc_" + _fingerprint(item.model_dump(mode="json"))[:16]
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            result.append(
                IncrementCandidateRecord(candidate_id=candidate_id, **item.model_dump())
            )
        return result

    def _validate_relationships(
        self, items: list[RelationshipCandidateInput]
    ) -> list[RelationshipCandidateRecord]:
        result: list[RelationshipCandidateRecord] = []
        seen: set[str] = set()
        for item in items:
            self._validate_object_ref(item.source)
            self._validate_object_ref(item.target)
            self._validate_evidence_ids(item.evidence_chunk_ids)
            candidate_id = "rel_" + _fingerprint(item.model_dump(mode="json"))[:16]
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            result.append(
                RelationshipCandidateRecord(candidate_id=candidate_id, **item.model_dump())
            )
        return result

    def _validate_object_ref(self, ref: ResearchObjectRef) -> None:
        if ref.kind == "cognition":
            self._validate_cognition_id(ref.object_id)
            return
        self._validate_evidence_ids([ref.object_id])

    def _validate_cognition_id(self, object_id: str) -> None:
        if self.cognition_docs is None or self.cognition_docs.get(object_id) is None:
            raise ValueError(f"cognition object not found: {object_id}")

    def _validate_evidence_ids(self, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            if chunk_id.startswith("cog:"):
                if self.cognition_chunks is None or self.cognition_chunks.get(chunk_id) is None:
                    raise ValueError(f"evidence chunk not found: {chunk_id}")
            elif self.report_chunks.get(chunk_id) is None:
                raise ValueError(f"evidence chunk not found: {chunk_id}")

    @staticmethod
    def _dossier_cognition_ids(dossier: dict) -> set[str]:
        definition = dossier["dossier"]
        values = [
            definition.get("topic_object_id"),
            *(definition.get("question_ids") or []),
            *(definition.get("judgment_ids") or []),
            *(definition.get("other_cognition_ids") or []),
        ]
        return {item for item in values if item}

    def _dir(self, dossier_id: str) -> Path:
        # Reuse DossierStore's validated ID path to prevent path traversal.
        directory = self.dossiers.store._dir(dossier_id) / "increment_analyses"
        return directory

    def _analysis_path(self, dossier_id: str, analysis_id: str) -> Path:
        if not analysis_id.startswith("ia_") or len(analysis_id) != 19:
            raise ValueError("invalid analysis_id")
        return self._dir(dossier_id) / f"{analysis_id}.json"

    @staticmethod
    def _analysis_id(
        dossier_id: str,
        report_id: str,
        report_hash: str | None,
        analysis_run_key: str | None,
    ) -> str:
        identity = {
            "dossier_id": dossier_id,
            "source_report_document_id": report_id,
            "source_report_content_hash": report_hash,
            "analysis_run_key": analysis_run_key or "default",
        }
        return "ia_" + _fingerprint(identity)[:16]

    @staticmethod
    def _read(path: Path) -> IncrementAnalysisRecord:
        return IncrementAnalysisRecord.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, record: IncrementAnalysisRecord) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
