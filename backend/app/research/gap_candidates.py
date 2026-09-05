"""Deterministic research-gap and next-topic candidate layer (DL-05).

The service consumes only already-structured, locally verifiable signals:
validated TaskPack results, DL-04 review candidates, and Dossier source-version
changes. It does not call a model and it never writes formal Cognition objects.
Candidate review is KE planning state only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.research.dossier import TopicDossierService
from app.research.increment_candidates import IncrementCandidateService
from app.taskpack.importer import COMPLETED, IMPORTED, TaskPackImporter

TOPIC_CANDIDATE_SCHEMA_VERSION = "1.0"
GapSourceType = Literal[
    "open_question",
    "additional_evidence_needed",
    "potential_conflict",
    "cannot_determine",
    "missing_source",
    "changed_source",
]
ReviewStatus = Literal["proposed", "accepted", "rejected", "deferred"]


class TopicCandidateReviewInput(BaseModel):
    status: ReviewStatus
    reason: str | None = Field(default=None, max_length=4000)
    reviewer: str = Field(default="user", min_length=1, max_length=100)


class TopicCardCandidate(BaseModel):
    schema_version: str = TOPIC_CANDIDATE_SCHEMA_VERSION
    candidate_id: str
    dossier_id: str
    source_type: GapSourceType
    title: str = Field(min_length=1, max_length=400)
    research_question: str = Field(min_length=1, max_length=8000)
    why_now: str = Field(min_length=1, max_length=8000)
    expected_research_value: str = Field(min_length=1, max_length=8000)
    required_evidence: list[str] = Field(default_factory=list, max_length=50)
    source_task_id: str | None = None
    source_analysis_id: str | None = None
    source_candidate_id: str | None = None
    source_ref: str | None = None
    source_fingerprint: str
    status: ReviewStatus = "proposed"
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    created_at: str
    updated_at: str
    formal_write_performed: bool = False


class TopicCandidateRefreshReport(BaseModel):
    dossier_id: str
    discovered: int
    created: int
    reused: int
    invalid_task_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    formal_write_performed: bool = False


class GapCandidateService:
    def __init__(self, cfg, report_conn, cognition_conn, importer: TaskPackImporter) -> None:
        self.cfg = cfg
        self.dossiers = TopicDossierService(cfg, report_conn, cognition_conn)
        self.increments = IncrementCandidateService(cfg, report_conn, cognition_conn)
        self.importer = importer

    def refresh(self, dossier_id: str) -> TopicCandidateRefreshReport:
        dossier = self._require_dossier(dossier_id)
        discovered: list[dict] = []
        invalid_task_ids: list[str] = []

        task_candidates, bad_tasks = self._from_validated_taskpacks(dossier_id)
        discovered.extend(task_candidates)
        invalid_task_ids.extend(bad_tasks)
        discovered.extend(self._from_increment_candidates(dossier_id))
        discovered.extend(self._from_source_changes(dossier))

        unique: dict[str, dict] = {}
        for item in discovered:
            candidate_id = self._candidate_id(dossier_id, item)
            unique.setdefault(candidate_id, item)

        created = 0
        reused = 0
        ids: list[str] = []
        now = _now()
        for candidate_id, item in unique.items():
            ids.append(candidate_id)
            path = self._candidate_path(dossier_id, candidate_id)
            if path.exists():
                existing = self._read(path)
                updated = TopicCardCandidate(
                    **item,
                    candidate_id=candidate_id,
                    dossier_id=dossier_id,
                    status=existing.status,
                    review_reason=existing.review_reason,
                    reviewed_by=existing.reviewed_by,
                    reviewed_at=existing.reviewed_at,
                    created_at=existing.created_at,
                    updated_at=now,
                    formal_write_performed=False,
                )
                self._atomic_write(path, updated)
                reused += 1
            else:
                record = TopicCardCandidate(
                    **item,
                    candidate_id=candidate_id,
                    dossier_id=dossier_id,
                    created_at=now,
                    updated_at=now,
                    formal_write_performed=False,
                )
                self._atomic_write(path, record)
                created += 1

        return TopicCandidateRefreshReport(
            dossier_id=dossier_id,
            discovered=len(unique),
            created=created,
            reused=reused,
            invalid_task_ids=sorted(set(invalid_task_ids)),
            candidate_ids=sorted(ids),
            formal_write_performed=False,
        )

    def list_candidates(self, dossier_id: str) -> list[TopicCardCandidate]:
        self._require_dossier(dossier_id)
        directory = self._dir(dossier_id)
        if not directory.exists():
            return []
        records: list[TopicCardCandidate] = []
        for path in sorted(directory.glob("tc_*.json")):
            try:
                records.append(self._read(path))
            except Exception:
                continue
        status_order = {"accepted": 0, "proposed": 1, "deferred": 2, "rejected": 3}
        return sorted(
            records,
            key=lambda item: (status_order.get(item.status, 9), item.created_at, item.candidate_id),
        )

    def get(self, dossier_id: str, candidate_id: str) -> TopicCardCandidate:
        path = self._candidate_path(dossier_id, candidate_id)
        if not path.exists():
            raise KeyError(f"topic candidate not found: {candidate_id}")
        return self._read(path)

    def review(
        self,
        dossier_id: str,
        candidate_id: str,
        review: TopicCandidateReviewInput,
    ) -> TopicCardCandidate:
        record = self.get(dossier_id, candidate_id)
        record.status = review.status
        record.review_reason = review.reason
        record.reviewed_by = review.reviewer
        record.reviewed_at = _now()
        record.updated_at = record.reviewed_at
        record.formal_write_performed = False
        self._atomic_write(self._candidate_path(dossier_id, candidate_id), record)
        return record

    def _from_validated_taskpacks(self, dossier_id: str) -> tuple[list[dict], list[str]]:
        result: list[dict] = []
        invalid: list[str] = []
        for info in self.importer.list_tasks():
            if info.status not in (COMPLETED, IMPORTED):
                continue
            pack = self.importer.locate(info.task_id)
            if pack is None or self._task_dossier_id(pack) != dossier_id:
                continue
            report = self.importer.import_task(pack)
            if not report.passed:
                invalid.append(info.task_id)
                continue
            parsed = self.importer._read_result(pack)
            if parsed is None:
                invalid.append(info.task_id)
                continue
            envelope = parsed[0]
            for index, question in enumerate(envelope.open_questions):
                q = (question or "").strip()
                if not q:
                    continue
                result.append(
                    self._item(
                        source_type="open_question",
                        title=f"开放问题：{_short(q)}",
                        research_question=q,
                        why_now="通过 TaskPack Gate 的研究结果仍将该问题列为开放问题。",
                        expected_research_value="回答该问题可直接缩小当前主题的已知不确定性，并为下一轮证据搜集提供明确目标。",
                        required_evidence=[],
                        source_task_id=info.task_id,
                        source_ref=f"open_questions[{index}]",
                        source_payload={"task_id": info.task_id, "kind": "open_question", "value": q},
                    )
                )
            for index, need in enumerate(envelope.additional_evidence_needed):
                question = need.question.strip()
                reason = need.reason.strip()
                result.append(
                    self._item(
                        source_type="additional_evidence_needed",
                        title=f"补证需求：{_short(question)}",
                        research_question=question,
                        why_now=reason,
                        expected_research_value="补齐该证据缺口可提升现有结论的可证伪性与引用完整度，而无需扩大到无关研究范围。",
                        required_evidence=[reason],
                        source_task_id=info.task_id,
                        source_ref=f"additional_evidence_needed[{index}]",
                        source_payload={
                            "task_id": info.task_id,
                            "kind": "additional_evidence_needed",
                            "question": question,
                            "reason": reason,
                        },
                    )
                )
        return result, invalid

    def _from_increment_candidates(self, dossier_id: str) -> list[dict]:
        result: list[dict] = []
        for analysis in self.increments.list_analyses(dossier_id):
            for candidate in analysis.increments:
                if candidate.status == "rejected":
                    continue
                if candidate.classification not in {"potential_conflict", "cannot_determine"}:
                    continue
                source_type: GapSourceType = candidate.classification
                if candidate.classification == "potential_conflict":
                    question = f"如何验证并解释该潜在冲突：{candidate.statement}"
                    value = "澄清冲突可防止互不兼容的判断同时进入后续研究，并明确条件边界或需要修订的认知对象。"
                else:
                    question = candidate.statement
                    value = "把当前无法判断的事项转化为明确研究问题，可避免用低置信度推断填补证据空缺。"
                result.append(
                    self._item(
                        source_type=source_type,
                        title=candidate.title,
                        research_question=question,
                        why_now=candidate.difference_reason,
                        expected_research_value=value,
                        required_evidence=list(candidate.evidence_chunk_ids),
                        source_analysis_id=analysis.analysis_id,
                        source_candidate_id=candidate.candidate_id,
                        source_ref=candidate.candidate_id,
                        source_payload={
                            "analysis_id": analysis.analysis_id,
                            "candidate_id": candidate.candidate_id,
                            "classification": candidate.classification,
                        },
                    )
                )
        return result

    def _from_source_changes(self, dossier: dict) -> list[dict]:
        result: list[dict] = []
        for change in dossier.get("source_changes") or []:
            kind = change.get("change")
            if kind not in {"missing", "changed"}:
                continue
            source = str(change.get("source") or "unknown")
            if kind == "missing":
                result.append(
                    self._item(
                        source_type="missing_source",
                        title=f"恢复或替代缺失来源：{source}",
                        research_question=f"缺失来源 {source} 应如何恢复、替代或确认不再需要？",
                        why_now="Dossier 当前投影显示该已保存来源无法解析，继续研究前需要处理覆盖缺口。",
                        expected_research_value="恢复来源或明确替代证据可重新建立主题上下文的可追溯性，并减少盲区。",
                        required_evidence=[source],
                        source_ref=source,
                        source_payload={"source": source, "change": "missing"},
                    )
                )
            else:
                result.append(
                    self._item(
                        source_type="changed_source",
                        title=f"复核来源版本变化：{source}",
                        research_question=f"来源 {source} 的版本变化是否改变当前主题中的既有问题、判断或证据解释？",
                        why_now="Dossier 保存快照与当前权威来源哈希不一致，需要解释变化而不是静默沿用旧上下文。",
                        expected_research_value="复核版本变化可区分文字更新与实质认知变化，并决定是否需要新的研究或修订候选。",
                        required_evidence=[source],
                        source_ref=source,
                        source_payload={
                            "source": source,
                            "change": "changed",
                            "saved": change.get("saved"),
                            "current": change.get("current"),
                        },
                    )
                )
        return result

    @staticmethod
    def _item(*, source_payload: dict, **values) -> dict:
        return {**values, "source_fingerprint": _fingerprint(source_payload)}

    @staticmethod
    def _task_dossier_id(pack: Path) -> str | None:
        path = pack / "research_context.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return (payload.get("direction") or {}).get("dossier_id")
        except Exception:
            return None

    def _require_dossier(self, dossier_id: str) -> dict:
        try:
            return self.dossiers.get(dossier_id)
        except KeyError as exc:
            raise KeyError(f"dossier not found: {dossier_id}") from exc

    def _dir(self, dossier_id: str) -> Path:
        return self.dossiers.store._dir(dossier_id) / "topic_candidates"

    def _candidate_path(self, dossier_id: str, candidate_id: str) -> Path:
        if not candidate_id.startswith("tc_") or len(candidate_id) != 19:
            raise ValueError("invalid topic candidate id")
        return self._dir(dossier_id) / f"{candidate_id}.json"

    @staticmethod
    def _candidate_id(dossier_id: str, item: dict) -> str:
        identity = {
            "dossier_id": dossier_id,
            "source_type": item["source_type"],
            "source_fingerprint": item["source_fingerprint"],
        }
        return "tc_" + _fingerprint(identity)[:16]

    @staticmethod
    def _read(path: Path) -> TopicCardCandidate:
        return TopicCardCandidate.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write(path: Path, record: TopicCardCandidate) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _short(value: str, limit: int = 90) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
