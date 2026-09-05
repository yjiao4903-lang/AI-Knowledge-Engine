"""Deterministic research-gap and next-topic candidate layer (DL-05).

The service consumes only structured, locally verifiable signals: Gate-passed
TaskPack results, DL-04 review candidates, and Dossier source-version changes.
It does not call a model and never writes formal Cognition objects.

DL-05C adds the FR-04 product policy:
- a current refresh exposes at most five actionable cards;
- cards contain explicit known/unknown, scope, evidence, method, workload and
  priority rationale instead of fabricated numeric scores;
- deterministic lexical duplicate hints are advisory only;
- rejected cards are retained as history but suppressed from the next batch.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.research.dossier import TopicDossierService
from app.research.increment_candidates import IncrementCandidateService
from app.taskpack.importer import COMPLETED, IMPORTED, TaskPackImporter

TOPIC_CANDIDATE_SCHEMA_VERSION = "1.1"
DEFAULT_MAX_CANDIDATES = 5
GapSourceType = Literal[
    "open_question",
    "additional_evidence_needed",
    "potential_conflict",
    "cannot_determine",
    "condition_change",
    "mechanism_gap",
    "analogy_extension",
    "missing_source",
    "changed_source",
]
ReviewStatus = Literal["proposed", "accepted", "rejected", "deferred"]
EvidenceAvailability = Literal["available", "partial", "unknown", "blocked"]
DuplicateCheck = Literal["no_exact_duplicate", "possible_duplicate"]
WorkloadBand = Literal["low", "medium", "high"]
PriorityBand = Literal["high", "medium", "low"]


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
    related_refs: list[str] = Field(default_factory=list, max_length=100)
    known: list[str] = Field(default_factory=list, max_length=50)
    unknown: list[str] = Field(default_factory=list, max_length=50)
    competing_explanations: list[str] = Field(default_factory=list, max_length=20)
    exploratory: bool = True
    discriminating_evidence: list[str] = Field(default_factory=list, max_length=50)
    evidence_availability: EvidenceAvailability = "unknown"
    evidence_availability_reason: str = "尚未评估可得性。"
    research_scope: list[str] = Field(default_factory=list, max_length=30)
    research_exclusions: list[str] = Field(default_factory=list, max_length=30)
    suggested_method: str = "围绕当前问题做定向证据检索与对照验证。"
    deliverable: str = "结构化研究结论、关键证据、反证/限制与对当前主题状态的影响。"
    duplicate_check: DuplicateCheck = "no_exact_duplicate"
    duplicate_reason: str = "未发现当前候选中的同文研究问题。"
    possible_duplicate_refs: list[str] = Field(default_factory=list, max_length=50)
    workload_band: WorkloadBand = "medium"
    workload_reason: str = "需要定向检索并核对现有主题上下文。"
    priority: PriorityBand = "medium"
    priority_reason: str = "与当前主题直接相关，但不构成必须立即处理的硬阻塞。"
    mainline_relevance: str = "由当前 Dossier 的研究缺口直接触发。"
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
    signals_discovered: int = 0
    selected: int = 0
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    omitted_by_limit: int = 0
    rejected_suppressed: int = 0
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

    def refresh(
        self,
        dossier_id: str,
        *,
        max_candidates: int = DEFAULT_MAX_CANDIDATES,
    ) -> TopicCandidateRefreshReport:
        if max_candidates < 1 or max_candidates > DEFAULT_MAX_CANDIDATES:
            raise ValueError(f"max_candidates must be between 1 and {DEFAULT_MAX_CANDIDATES}")
        dossier = self._require_dossier(dossier_id)
        discovered: list[dict] = []
        invalid_task_ids: list[str] = []

        task_candidates, bad_tasks = self._from_validated_taskpacks(dossier_id)
        discovered.extend(task_candidates)
        invalid_task_ids.extend(bad_tasks)
        discovered.extend(self._from_increment_candidates(dossier_id))
        discovered.extend(self._from_relationship_candidates(dossier_id))
        discovered.extend(self._from_source_changes(dossier))

        unique: dict[str, dict] = {}
        for raw in discovered:
            candidate_id = self._candidate_id(dossier_id, raw)
            unique.setdefault(candidate_id, self._enrich(dossier, raw))

        self._mark_duplicate_hints(dossier_id, unique)

        rejected_suppressed = 0
        selectable: list[tuple[str, dict]] = []
        for candidate_id, item in unique.items():
            existing = self._existing(dossier_id, candidate_id)
            if existing is not None and existing.status == "rejected":
                rejected_suppressed += 1
                continue
            selectable.append((candidate_id, item))
        selectable.sort(key=lambda row: self._rank_key(dossier_id, row[0], row[1]))
        selected = selectable[:max_candidates]

        created = 0
        reused = 0
        ids: list[str] = []
        now = _now()
        for candidate_id, item in selected:
            ids.append(candidate_id)
            path = self._candidate_path(dossier_id, candidate_id)
            existing = self._existing(dossier_id, candidate_id)
            if existing is not None:
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

        snapshot = {
            "schema_version": TOPIC_CANDIDATE_SCHEMA_VERSION,
            "generated_at": now,
            "dossier_id": dossier_id,
            "max_candidates": max_candidates,
            "signals_discovered": len(unique),
            "candidate_ids": ids,
            "omitted_by_limit": max(0, len(selectable) - len(selected)),
            "rejected_suppressed": rejected_suppressed,
            "invalid_task_ids": sorted(set(invalid_task_ids)),
        }
        self._write_json(self._latest_refresh_path(dossier_id), snapshot)
        return TopicCandidateRefreshReport(
            dossier_id=dossier_id,
            discovered=len(unique),
            signals_discovered=len(unique),
            selected=len(ids),
            max_candidates=max_candidates,
            omitted_by_limit=snapshot["omitted_by_limit"],
            rejected_suppressed=rejected_suppressed,
            created=created,
            reused=reused,
            invalid_task_ids=snapshot["invalid_task_ids"],
            candidate_ids=ids,
            formal_write_performed=False,
        )

    def list_candidates(self, dossier_id: str) -> list[TopicCardCandidate]:
        self._require_dossier(dossier_id)
        directory = self._dir(dossier_id)
        if not directory.exists():
            return []
        snapshot = self._read_json(self._latest_refresh_path(dossier_id))
        if snapshot is not None:
            records: list[TopicCardCandidate] = []
            for candidate_id in snapshot.get("candidate_ids") or []:
                existing = self._existing(dossier_id, candidate_id)
                if existing is not None:
                    records.append(existing)
            return records[:DEFAULT_MAX_CANDIDATES]

        # Backward-compatible runtime migration for data produced by DL-05A/B:
        # before the first 1.1 refresh, never expose more than the new default.
        records: list[TopicCardCandidate] = []
        for path in sorted(directory.glob("tc_*.json")):
            try:
                row = self._read(path)
            except Exception:
                continue
            if row.status != "rejected":
                records.append(row)
        records.sort(key=lambda item: self._record_rank(item))
        return records[:DEFAULT_MAX_CANDIDATES]

    def get(self, dossier_id: str, candidate_id: str) -> TopicCardCandidate:
        self._require_dossier(dossier_id)
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
                        expected_research_value="回答该问题可缩小当前主题的已知不确定性，并为下一轮证据搜集提供明确目标。",
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
                if candidate.classification not in {
                    "potential_conflict",
                    "cannot_determine",
                    "condition_change",
                }:
                    continue
                if candidate.classification == "potential_conflict":
                    question = f"如何验证并解释该潜在冲突：{candidate.statement}"
                    value = "澄清冲突可防止互不兼容的判断同时进入后续研究，并明确条件边界或需要修订的认知对象。"
                elif candidate.classification == "condition_change":
                    question = f"条件变化是否实质改变既有判断：{candidate.statement}"
                    value = "复核条件变化可区分边界调整与核心判断失效，避免把旧结论无条件外推到新环境。"
                else:
                    question = candidate.statement
                    value = "把当前无法判断的事项转化为明确研究问题，可避免用低置信度推断填补证据空缺。"
                result.append(
                    self._item(
                        source_type=candidate.classification,
                        title=candidate.title,
                        research_question=question,
                        why_now=candidate.difference_reason,
                        expected_research_value=value,
                        required_evidence=list(candidate.evidence_chunk_ids),
                        related_refs=[*candidate.target_cognition_object_ids, *candidate.evidence_chunk_ids],
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

    def _from_relationship_candidates(self, dossier_id: str) -> list[dict]:
        result: list[dict] = []
        for analysis in self.increments.list_analyses(dossier_id):
            for relation in analysis.relationships:
                if relation.status == "rejected":
                    continue
                if relation.relation_type in {"mechanism_hypothesis", "concept_dependency"}:
                    source_type: GapSourceType = "mechanism_gap"
                    title = f"验证机制联系：{_short(relation.explanation)}"
                    question = f"如何验证该候选机制/依赖关系，而不是把共现误判为机制：{relation.explanation}"
                    value = "验证机制链可把当前关系候选转化为可检验的研究结构，并暴露中介变量或断点。"
                elif relation.relation_type == "condition_limits":
                    source_type = "condition_change"
                    title = f"验证条件限制：{_short(relation.explanation)}"
                    question = f"该条件限制在什么边界下成立，并会如何改变相关判断：{relation.explanation}"
                    value = "明确条件边界可降低跨时期、跨场景外推错误。"
                elif relation.relation_type == "analogy":
                    source_type = "analogy_extension"
                    title = f"探索类比：{_short(relation.explanation)}"
                    question = f"该类比是否存在可验证的结构同构，还是仅为启发：{relation.explanation}"
                    value = "验证类比可发现跨领域研究方向，同时避免把启发性相似误写为事实关系。"
                else:
                    continue
                refs = [
                    f"{relation.source.kind}:{relation.source.object_id}",
                    f"{relation.target.kind}:{relation.target.object_id}",
                    *relation.evidence_chunk_ids,
                ]
                result.append(
                    self._item(
                        source_type=source_type,
                        title=title,
                        research_question=question,
                        why_now=relation.explanation,
                        expected_research_value=value,
                        required_evidence=list(relation.evidence_chunk_ids),
                        related_refs=refs,
                        source_analysis_id=analysis.analysis_id,
                        source_candidate_id=relation.candidate_id,
                        source_ref=relation.candidate_id,
                        source_payload={
                            "analysis_id": analysis.analysis_id,
                            "candidate_id": relation.candidate_id,
                            "relation_type": relation.relation_type,
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
                        related_refs=[source],
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
                        related_refs=[source],
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

    def _enrich(self, dossier: dict, item: dict) -> dict:
        source_type: GapSourceType = item["source_type"]
        profiles: dict[str, dict] = {
            "potential_conflict": {
                "exploratory": False,
                "explanations": ["既有判断仍成立，但适用条件更窄。", "新证据意味着既有判断需要实质修订。"],
                "availability": "partial",
                "availability_reason": "已有冲突证据定位，但仍需要能够区分两种解释的新证据。",
                "method": "对照冲突两侧证据，列出共同前提、条件差异和可证伪预测。",
                "workload": "medium",
                "workload_reason": "需要跨已有判断与新证据做条件化对照。",
                "priority": "high",
                "priority_reason": "未解决冲突会直接污染后续主题判断与研究上下文。",
            },
            "condition_change": {
                "exploratory": False,
                "explanations": ["变化只收窄适用边界，核心判断仍成立。", "变化已经改变核心机制或方向。"],
                "availability": "partial",
                "availability_reason": "已有条件变化线索，但需要新旧条件下的可比证据。",
                "method": "按时间/场景切片比较同一机制在旧条件与新条件下的表现。",
                "workload": "medium",
                "workload_reason": "需要可比口径的跨条件证据。",
                "priority": "high",
                "priority_reason": "条件漂移会导致旧结论被无条件外推。",
            },
            "mechanism_gap": {
                "exploratory": False,
                "explanations": ["候选联系反映真实机制或依赖链。", "候选联系主要由共现、中介变量或选择效应造成。"],
                "availability": "partial",
                "availability_reason": "关系候选已有 Evidence grounding，但尚缺机制识别所需的区分证据。",
                "method": "拆分机制链、寻找中介变量与反事实，优先搜集能区分机制与共现的证据。",
                "workload": "high",
                "workload_reason": "机制识别通常需要多来源与反事实/条件对照。",
                "priority": "medium",
                "priority_reason": "对研究地图有高解释价值，但通常不如当前硬冲突紧迫。",
            },
            "analogy_extension": {
                "exploratory": True,
                "explanations": [],
                "availability": "unknown",
                "availability_reason": "当前只有有依据的类比候选，尚未确认目标领域是否存在可比数据。",
                "method": "先定义可比维度与失配条件，再做小范围证据检索，失败则保留为启发而非事实关系。",
                "workload": "high",
                "workload_reason": "跨领域类比需要先验证口径和结构可比性。",
                "priority": "low",
                "priority_reason": "属于探索性扩展，不应挤占当前主题的冲突和补证任务。",
            },
            "missing_source": {
                "exploratory": True,
                "explanations": [],
                "availability": "blocked",
                "availability_reason": "当前已保存来源无法解析；在恢复或替代前无法完整验证。",
                "method": "先恢复来源或寻找等价替代材料，再判断是否需要后续研究。",
                "workload": "low",
                "workload_reason": "首要工作是来源恢复/替代，而不是展开新机制研究。",
                "priority": "high",
                "priority_reason": "来源缺失直接破坏主题上下文的可追溯性。",
            },
            "changed_source": {
                "exploratory": False,
                "explanations": ["版本变化主要是编辑性更新，不改变既有结论。", "版本变化包含会改变问题、判断或证据解释的实质信息。"],
                "availability": "available",
                "availability_reason": "当前版本可解析，可与保存快照的哈希/内容范围进行复核。",
                "method": "比较保存版本与当前版本，定位实质差异并映射到受影响问题/判断。",
                "workload": "low",
                "workload_reason": "问题边界明确，主要是版本差异复核。",
                "priority": "high",
                "priority_reason": "若不复核，后续上下文可能混用旧版本与新版本。",
            },
            "additional_evidence_needed": {
                "exploratory": True,
                "explanations": [],
                "availability": "partial",
                "availability_reason": "现有结果已明确指出缺失证据；可得性仍需在检索阶段确认。",
                "method": "围绕明确补证问题定向检索，优先获取可直接支撑或反驳现有结论的来源。",
                "workload": "medium",
                "workload_reason": "问题清晰，但仍需新增证据搜集与质量核对。",
                "priority": "high",
                "priority_reason": "这是已通过 Gate 的研究结果显式声明的证据缺口。",
            },
            "open_question": {
                "exploratory": True,
                "explanations": [],
                "availability": "unknown",
                "availability_reason": "问题已被验证为未解决，但尚未评估回答它所需证据的可得性。",
                "method": "先界定问题与可证伪观察，再检索最小充分证据集。",
                "workload": "medium",
                "workload_reason": "需要从问题界定进入定向检索。",
                "priority": "medium",
                "priority_reason": "直接来自已完成研究，但紧迫性低于明确冲突或已知补证缺口。",
            },
            "cannot_determine": {
                "exploratory": True,
                "explanations": [],
                "availability": "unknown",
                "availability_reason": "当前分析明确无法判断，需要先识别缺失变量或证据。",
                "method": "把无法判断拆成可观察子问题，定义最低证据门槛后再研究。",
                "workload": "medium",
                "workload_reason": "需要先重构问题，再搜集证据。",
                "priority": "medium",
                "priority_reason": "避免用低置信度推断填补空缺，但通常不构成当前硬阻塞。",
            },
        }
        profile = profiles[source_type]
        definition = dossier["dossier"]
        scope = list(definition.get("scope_include") or []) or ["仅限当前 Dossier 主题及该候选触发问题。"]
        exclusions = list(definition.get("scope_exclude") or []) or ["不扩展到与触发问题无关的主题。"]
        related = _dedupe_strings([*(item.get("related_refs") or []), *(item.get("required_evidence") or []), item.get("source_ref")])
        discriminating = list(item.get("required_evidence") or [])
        if not discriminating:
            discriminating = ["能够支持、反驳或显著收窄该研究问题的可定位 Evidence。"]
        return {
            **item,
            "related_refs": related,
            "known": [item["why_now"]],
            "unknown": [item["research_question"]],
            "competing_explanations": profile["explanations"],
            "exploratory": profile["exploratory"],
            "discriminating_evidence": discriminating,
            "evidence_availability": profile["availability"],
            "evidence_availability_reason": profile["availability_reason"],
            "research_scope": scope,
            "research_exclusions": exclusions,
            "suggested_method": profile["method"],
            "deliverable": "结构化研究结论；新增 Evidence 定位；反证与限制；相对当前主题状态的增量；仍未解决事项。",
            "duplicate_check": "no_exact_duplicate",
            "duplicate_reason": "未发现当前候选中的同文研究问题；这不是语义重复判定。",
            "possible_duplicate_refs": [],
            "workload_band": profile["workload"],
            "workload_reason": profile["workload_reason"],
            "priority": profile["priority"],
            "priority_reason": profile["priority_reason"],
            "mainline_relevance": f"由 Dossier `{definition['dossier_id']}` 的 {source_type} 信号直接触发。",
        }

    def _mark_duplicate_hints(self, dossier_id: str, items: dict[str, dict]) -> None:
        by_question: dict[str, list[str]] = {}
        for candidate_id, item in items.items():
            key = _normalize_question(item["research_question"])
            if key:
                by_question.setdefault(key, []).append(candidate_id)
        # Include persisted history only for exact normalized-question hints.
        for path in self._dir(dossier_id).glob("tc_*.json") if self._dir(dossier_id).exists() else []:
            try:
                record = self._read(path)
            except Exception:
                continue
            key = _normalize_question(record.research_question)
            if key:
                by_question.setdefault(key, []).append(record.candidate_id)
        for candidate_id, item in items.items():
            refs = sorted(set(by_question.get(_normalize_question(item["research_question"]), [])) - {candidate_id})
            if refs:
                item["duplicate_check"] = "possible_duplicate"
                item["duplicate_reason"] = "发现规范化后完全相同的研究问题；仅提示可能重复，不自动合并不同来源/时期/条件。"
                item["possible_duplicate_refs"] = refs[:50]

    def _rank_key(self, dossier_id: str, candidate_id: str, item: dict) -> tuple:
        status = self._existing(dossier_id, candidate_id)
        status_rank = {"accepted": 0, "proposed": 1, "deferred": 2}.get(
            status.status if status is not None else "proposed", 1
        )
        priority_rank = {"high": 0, "medium": 1, "low": 2}[item["priority"]]
        source_rank = {
            "missing_source": 0,
            "potential_conflict": 1,
            "changed_source": 2,
            "additional_evidence_needed": 3,
            "condition_change": 4,
            "mechanism_gap": 5,
            "open_question": 6,
            "cannot_determine": 7,
            "analogy_extension": 8,
        }[item["source_type"]]
        return (status_rank, priority_rank, source_rank, candidate_id)

    @staticmethod
    def _record_rank(item: TopicCardCandidate) -> tuple:
        return (
            {"accepted": 0, "proposed": 1, "deferred": 2, "rejected": 3}.get(item.status, 9),
            {"high": 0, "medium": 1, "low": 2}.get(item.priority, 9),
            item.candidate_id,
        )

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

    def _latest_refresh_path(self, dossier_id: str) -> Path:
        return self._dir(dossier_id) / "latest_refresh.json"

    def _existing(self, dossier_id: str, candidate_id: str) -> TopicCardCandidate | None:
        path = self._candidate_path(dossier_id, candidate_id)
        if not path.exists():
            return None
        try:
            return self._read(path)
        except Exception:
            return None

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
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _atomic_write(path: Path, record: TopicCardCandidate) -> None:
        GapCandidateService._write_json(path, record.model_dump(mode="json"))

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_question(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def _dedupe_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _short(value: str, limit: int = 90) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
