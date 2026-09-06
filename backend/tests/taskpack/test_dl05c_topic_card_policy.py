from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import topic_candidates as topic_api
from app.research.dossier import DossierUpsert, TopicDossierService
from app.research.gap_candidates import GapCandidateService, TopicCandidateReviewInput
from app.research.increment_candidates import (
    IncrementAnalysisInput,
    IncrementCandidateInput,
    IncrementCandidateService,
    RelationshipCandidateInput,
    ResearchObjectRef,
)
from app.taskpack.validation_cache import CachingTaskPackImporter


def _seed_policy_signals(tk_env, dossier_id: str):
    cfg = tk_env["cfg"]
    conn = tk_env["conn"]
    TopicDossierService(cfg, conn, None).upsert(
        dossier_id,
        DossierUpsert(
            title="AI 机制研究",
            direction="围绕机制、条件变化与证据缺口推进下一轮研究。",
            scope_include=["机制识别", "条件边界"],
            scope_exclude=["无关行业扩展"],
            evidence_refs=tk_env["refs"],
        ),
    )
    increments = IncrementCandidateService(cfg, conn, None)

    duplicate_question = "同一个研究问题应保留不同来源并提示重复，而不是自动合并。"
    for run_key, statement in [
        ("dup-a", duplicate_question),
        ("dup-b", duplicate_question),
        ("unique", "另一个无法判断的问题需要先定义最低证据门槛。"),
    ]:
        increments.ingest(
            dossier_id,
            IncrementAnalysisInput(
                source_report_document_id="M04",
                analysis_run_key=run_key,
                increments=[
                    IncrementCandidateInput(
                        classification="cannot_determine",
                        title=f"无法判断 {run_key}",
                        statement=statement,
                        difference_reason="当前证据不足以形成可靠结论。",
                    )
                ],
            ),
        )

    increments.ingest(
        dossier_id,
        IncrementAnalysisInput(
            source_report_document_id="M04",
            analysis_run_key="relations",
            relationships=[
                RelationshipCandidateInput(
                    relation_type="mechanism_hypothesis",
                    source=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0001"),
                    target=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0002"),
                    explanation="HBM 接口变化可能通过先进封装约束影响系统价值量。",
                    evidence_chunk_ids=["M04:ch1:0001"],
                ),
                RelationshipCandidateInput(
                    relation_type="condition_limits",
                    source=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0001"),
                    target=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0002"),
                    explanation="只有在先进封装成为约束时，该关系才可能显著。",
                    evidence_chunk_ids=["M04:ch1:0001"],
                ),
                RelationshipCandidateInput(
                    relation_type="analogy",
                    source=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0001"),
                    target=ResearchObjectRef(kind="report_evidence", object_id="M04:ch1:0002"),
                    explanation="可探索接口升级与封装价值量之间是否存在跨代际类比。",
                    evidence_chunk_ids=["M04:ch1:0001"],
                ),
            ],
        ),
    )


def test_fr04_current_batch_is_max_five_with_rationale_and_duplicate_hint(tk_env):
    dossier_id = "fr04-policy"
    _seed_policy_signals(tk_env, dossier_id)
    importer = CachingTaskPackImporter(tk_env["cfg"], tk_env["conn"], None)
    service = GapCandidateService(tk_env["cfg"], tk_env["conn"], None, importer)

    report = service.refresh(dossier_id)
    assert report.signals_discovered == 6
    assert report.selected == 5
    assert report.max_candidates == 5
    assert report.omitted_by_limit == 1
    rows = service.list_candidates(dossier_id)
    assert len(rows) == 5
    assert "analogy_extension" not in {row.source_type for row in rows}
    assert {"condition_change", "mechanism_gap"}.issubset({row.source_type for row in rows})

    for row in rows:
        assert row.known
        assert row.unknown
        assert row.research_scope
        assert row.research_exclusions
        assert row.suggested_method
        assert row.deliverable
        assert row.evidence_availability_reason
        assert row.workload_reason
        assert row.priority_reason
        assert row.mainline_relevance
        assert row.priority in {"high", "medium", "low"}
        assert row.workload_band in {"low", "medium", "high"}
        assert row.exploratory or len(row.competing_explanations) >= 2
        assert row.formal_write_performed is False

    duplicate_rows = [
        row
        for row in rows
        if row.research_question
        == "同一个研究问题应保留不同来源并提示重复，而不是自动合并。"
    ]
    assert len(duplicate_rows) == 2
    assert all(row.duplicate_check == "possible_duplicate" for row in duplicate_rows)
    assert all(row.possible_duplicate_refs for row in duplicate_rows)

    # A rejected current card is history, not a permanent slot consumer. The next
    # refresh suppresses it and admits the previously omitted exploratory card.
    rejected_id = next(row.candidate_id for row in rows if row.source_type == "cannot_determine")
    service.review(
        dossier_id,
        rejected_id,
        TopicCandidateReviewInput(status="rejected", reason="本轮不研究"),
    )
    next_report = service.refresh(dossier_id)
    next_rows = service.list_candidates(dossier_id)
    assert next_report.rejected_suppressed == 1
    assert len(next_rows) == 5
    assert rejected_id not in {row.candidate_id for row in next_rows}
    assert "analogy_extension" in {row.source_type for row in next_rows}


def test_zero_signal_dossier_can_return_zero_candidates(tk_env):
    dossier_id = "quiet-topic"
    TopicDossierService(tk_env["cfg"], tk_env["conn"], None).upsert(
        dossier_id,
        DossierUpsert(title="暂无缺口", direction="允许系统诚实返回零候选。"),
    )
    importer = CachingTaskPackImporter(tk_env["cfg"], tk_env["conn"], None)
    service = GapCandidateService(tk_env["cfg"], tk_env["conn"], None, importer)
    report = service.refresh(dossier_id)
    assert report.signals_discovered == 0
    assert report.selected == 0
    assert service.list_candidates(dossier_id) == []


def test_accepted_candidate_creates_one_taskpack_then_reuses_it_without_launch(tk_env):
    dossier_id = "candidate-handoff"
    _seed_policy_signals(tk_env, dossier_id)
    importer = CachingTaskPackImporter(tk_env["cfg"], tk_env["conn"], None)
    service = GapCandidateService(tk_env["cfg"], tk_env["conn"], None, importer)
    service.refresh(dossier_id)
    candidate = service.list_candidates(dossier_id)[0]
    service.review(
        dossier_id,
        candidate.candidate_id,
        TopicCandidateReviewInput(status="accepted", reason="进入下一轮"),
    )
    another = next(row for row in service.list_candidates(dossier_id) if row.candidate_id != candidate.candidate_id)

    app = FastAPI()
    app.state.cfg = tk_env["cfg"]
    app.state.conn = tk_env["conn"]
    app.state.cognition = {"enabled": False}
    app.state.taskpack_builder = tk_env["builder"]
    app.state.taskpack_importer = importer
    app.include_router(topic_api.router)

    payload = {
        "task_type": "summary",
        "evidence_context_mode": "none",
        "evidence_refs": [tk_env["refs"][0].model_dump(mode="json")],
        "cognition_object_ids": [],
    }
    with TestClient(app) as client:
        not_accepted = client.post(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/{another.candidate_id}/task",
            json=payload,
        )
        assert not_accepted.status_code == 409

        created = client.post(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/{candidate.candidate_id}/task",
            json=payload,
        )
        assert created.status_code == 200, created.text
        first = created.json()
        assert first["status"] == "READY"
        assert first["reused"] is False
        assert first["worker_launched"] is False
        assert first["formal_write_performed"] is False

        pack = importer.locate(first["task_id"])
        assert pack is not None
        context = json.loads((pack / "research_context.json").read_text(encoding="utf-8"))
        assert context["direction"]["dossier_id"] == dossier_id
        assert context["task"]["topic_candidate_id"] == candidate.candidate_id
        assert context["task"]["query"] == candidate.research_question
        assert context["task"]["topic_candidate_method"] == candidate.suggested_method
        assert "Topic candidate" in (pack / "research_brief.md").read_text(encoding="utf-8")
        assert not (tk_env["root"] / "processing" / first["task_id"]).exists()

        # Even with a different Evidence selection, the same accepted candidate
        # resolves to the already-linked TaskPack instead of creating a duplicate.
        payload["evidence_refs"] = [tk_env["refs"][1].model_dump(mode="json")]
        reused = client.post(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/{candidate.candidate_id}/task",
            json=payload,
        )
        assert reused.status_code == 200
        second = reused.json()
        assert second["reused"] is True
        assert second["task_id"] == first["task_id"]
        assert second["worker_launched"] is False
        linked = [
            info
            for info in importer.list_tasks()
            if info.task_id == first["task_id"]
        ]
        assert len(linked) == 1
