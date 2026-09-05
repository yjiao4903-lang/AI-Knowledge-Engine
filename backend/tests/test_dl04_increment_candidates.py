from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import increment_analysis as increment_api
from app.core.config import Config
from app.research.dossier import DossierUpsert, TopicDossierService
from app.research.increment_candidates import (
    CandidateReviewInput,
    IncrementAnalysisInput,
    IncrementCandidateInput,
    IncrementCandidateService,
    RelationshipCandidateInput,
    ResearchObjectRef,
)
from app.storage.migrations import init_schema
from app.storage.sqlite import connect


def _seed_document(
    conn,
    *,
    doc_id: str,
    path: Path,
    title: str,
    doc_hash: str,
    chunk_id: str,
    chunk_hash: str,
    text: str,
):
    section_id = f"{doc_id}:s1"
    with conn:
        conn.execute(
            "INSERT INTO documents(id, title, source_path, file_name, sha256, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, title, str(path), path.name, doc_hash, "2026-09-06T01:00:00+08:00"),
        )
        conn.execute(
            "INSERT INTO sections(id, document_id, level, heading, heading_path, ordinal, start_line, end_line, raw_text) VALUES (?, ?, 1, ?, ?, 1, 1, 10, ?)",
            (section_id, doc_id, title, title, text),
        )
        conn.execute(
            """
            INSERT INTO chunks(
                id, document_id, section_id, ordinal, heading_path, content_type,
                raw_markdown, plain_text, embedding_text, lexical_text,
                start_line, end_line, content_hash
            ) VALUES (?, ?, ?, 1, ?, 'paragraph', ?, ?, ?, ?, 1, 10, ?)
            """,
            (chunk_id, doc_id, section_id, title, text, text, text, text, chunk_hash),
        )


def _environment(tmp_path: Path):
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    cognition = tmp_path / "cognition"
    reports.mkdir(parents=True)
    (cognition / "03_问题池").mkdir(parents=True)
    (cognition / "04_判断台账").mkdir(parents=True)

    cfg = Config()
    cfg.paths.data_dir = str(data)
    cfg.cognition.root = str(cognition)

    report_conn = connect(data / "catalog.db", check_same_thread=False)
    cognition_conn = connect(data / "catalog_cognition.db", check_same_thread=False)
    init_schema(report_conn)
    init_schema(cognition_conn)

    _seed_document(
        report_conn,
        doc_id="M100",
        path=reports / "M100.md",
        title="AI 收入分配研究",
        doc_hash="report-v1",
        chunk_id="M100:s1:c1",
        chunk_hash="report-chunk-v1",
        text="AI 采用可能提升企业利润，但工资传导存在时滞。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:q-demand",
        path=cognition / "03_问题池" / "demand.md",
        title="AI 是否形成需求约束",
        doc_hash="question-v1",
        chunk_id="cog:q-demand:s1:c1",
        chunk_hash="question-chunk-v1",
        text="需要检验生产率、劳动收入和总需求之间的反馈。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:j-capex",
        path=cognition / "04_判断台账" / "capex.md",
        title="AI CAPEX 判断",
        doc_hash="judgment-v1",
        chunk_id="cog:j-capex:s1:c1",
        chunk_hash="judgment-chunk-v1",
        text="CAPEX 下降的现金流效应和增长预期效应需要分开。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:j-outside",
        path=cognition / "04_判断台账" / "outside.md",
        title="Dossier 外部判断",
        doc_hash="outside-v1",
        chunk_id="cog:j-outside:s1:c1",
        chunk_hash="outside-chunk-v1",
        text="该对象不属于当前 Dossier。",
    )

    TopicDossierService(cfg, report_conn, cognition_conn).upsert(
        "ai-demand",
        DossierUpsert(
            title="AI 生产率与需求约束",
            direction="研究 AI 生产率、收入分配与总需求反馈。",
            question_ids=["cog:q-demand"],
            judgment_ids=["cog:j-capex"],
        ),
    )
    return cfg, report_conn, cognition_conn


def _increment() -> IncrementCandidateInput:
    return IncrementCandidateInput(
        classification="potential_conflict",
        title="利润改善与需求走弱可能并存",
        statement="新报告提示利润率改善并不保证劳动收入同步增长。",
        difference_reason="这限制了既有增长判断的适用条件。",
        evidence_chunk_ids=["M100:s1:c1"],
        target_cognition_object_ids=["cog:j-capex"],
        scope="企业 AI 采用阶段",
    )


def _relationship() -> RelationshipCandidateInput:
    return RelationshipCandidateInput(
        relation_type="condition_limits",
        source=ResearchObjectRef(kind="report_evidence", object_id="M100:s1:c1"),
        target=ResearchObjectRef(kind="cognition", object_id="cog:j-capex"),
        explanation="工资传导不足可能限制 CAPEX 乐观判断向总需求的外推。",
        evidence_chunk_ids=["M100:s1:c1"],
    )


def _body(*, run_key: str = "worker-run-1") -> IncrementAnalysisInput:
    return IncrementAnalysisInput(
        source_report_document_id="M100",
        analysis_run_key=run_key,
        task_id="task-100",
        coverage_note="仅覆盖报告中收入分配段落。",
        increments=[_increment()],
        relationships=[_relationship()],
    )


def test_persist_idempotency_dedupe_hash_change_and_review_boundary(tmp_path):
    cfg, report_conn, cognition_conn = _environment(tmp_path)
    service = IncrementCandidateService(cfg, report_conn, cognition_conn)
    try:
        body = _body()
        body.increments.append(_increment())
        body.relationships.append(_relationship())

        record, reused = service.ingest("ai-demand", body)
        assert reused is False
        assert len(record.increments) == 1
        assert len(record.relationships) == 1
        assert record.formal_write_performed is False
        path = (
            Path(cfg.paths.data_dir)
            / "research_dossiers"
            / "ai-demand"
            / "increment_analyses"
            / f"{record.analysis_id}.json"
        )
        assert path.exists()

        cognition_before = list(cognition_conn.iterdump())
        candidate_id = record.relationships[0].candidate_id
        reviewed = service.review(
            "ai-demand",
            record.analysis_id,
            candidate_id,
            CandidateReviewInput(status="accepted", reason="保留为候选关系"),
        )
        assert reviewed.relationships[0].status == "accepted"
        assert reviewed.formal_write_performed is False
        assert list(cognition_conn.iterdump()) == cognition_before

        same, reused = service.ingest("ai-demand", body)
        assert reused is True
        assert same.analysis_id == record.analysis_id
        assert same.relationships[0].status == "accepted"

        with report_conn:
            report_conn.execute("UPDATE documents SET sha256 = ? WHERE id = ?", ("report-v2", "M100"))
        changed, reused = service.ingest("ai-demand", body)
        assert reused is False
        assert changed.analysis_id != record.analysis_id
    finally:
        report_conn.close()
        cognition_conn.close()


def test_invalid_references_rejected_before_analysis_file_creation(tmp_path):
    cfg, report_conn, cognition_conn = _environment(tmp_path)
    service = IncrementCandidateService(cfg, report_conn, cognition_conn)
    analysis_dir = (
        Path(cfg.paths.data_dir)
        / "research_dossiers"
        / "ai-demand"
        / "increment_analyses"
    )
    try:
        with pytest.raises(ValueError, match="evidence chunk not found"):
            service.ingest(
                "ai-demand",
                IncrementAnalysisInput(
                    source_report_document_id="M100",
                    analysis_run_key="missing-evidence",
                    increments=[
                        IncrementCandidateInput(
                            classification="new_insight",
                            title="bad",
                            statement="bad",
                            difference_reason="bad",
                            evidence_chunk_ids=["missing:chunk"],
                        )
                    ],
                ),
            )
        assert not analysis_dir.exists() or not list(analysis_dir.glob("*.json"))

        with pytest.raises(ValueError, match="cognition object not found"):
            service.ingest(
                "ai-demand",
                IncrementAnalysisInput(
                    source_report_document_id="M100",
                    analysis_run_key="missing-cognition",
                    increments=[
                        IncrementCandidateInput(
                            classification="potential_conflict",
                            title="bad",
                            statement="bad",
                            difference_reason="bad",
                            evidence_chunk_ids=["M100:s1:c1"],
                            target_cognition_object_ids=["cog:missing"],
                        )
                    ],
                ),
            )

        with pytest.raises(ValueError, match="outside dossier scope"):
            service.ingest(
                "ai-demand",
                IncrementAnalysisInput(
                    source_report_document_id="M100",
                    analysis_run_key="outside-scope",
                    increments=[
                        IncrementCandidateInput(
                            classification="potential_conflict",
                            title="bad",
                            statement="bad",
                            difference_reason="bad",
                            evidence_chunk_ids=["M100:s1:c1"],
                            target_cognition_object_ids=["cog:j-outside"],
                        )
                    ],
                ),
            )
    finally:
        report_conn.close()
        cognition_conn.close()


def test_relationship_schema_rejects_self_relation():
    ref = ResearchObjectRef(kind="cognition", object_id="cog:j-capex")
    with pytest.raises(ValidationError, match="source and target must differ"):
        RelationshipCandidateInput(
            relation_type="supports",
            source=ref,
            target=ref,
            explanation="invalid",
            evidence_chunk_ids=["M100:s1:c1"],
        )


def test_http_create_list_detail_review_and_error_codes(tmp_path):
    cfg, report_conn, cognition_conn = _environment(tmp_path)
    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = report_conn
    app.state.cognition = {"enabled": True, "conn": cognition_conn}
    app.include_router(increment_api.router)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/research-os/dossiers/ai-demand/increment-analyses",
                json=_body().model_dump(mode="json"),
            )
            assert created.status_code == 200, created.text
            payload = created.json()
            assert payload["reused"] is False
            assert payload["auto_apply"] is False
            assert payload["formal_write_performed"] is False
            analysis_id = payload["analysis"]["analysis_id"]
            inc_id = payload["analysis"]["increments"][0]["candidate_id"]

            listed = client.get("/api/research-os/dossiers/ai-demand/increment-analyses")
            assert listed.status_code == 200
            assert [item["analysis_id"] for item in listed.json()["analyses"]] == [analysis_id]

            detail = client.get(
                f"/api/research-os/dossiers/ai-demand/increment-analyses/{analysis_id}"
            )
            assert detail.status_code == 200
            assert detail.json()["analysis"]["analysis_id"] == analysis_id

            cognition_before = list(cognition_conn.iterdump())
            reviewed = client.post(
                f"/api/research-os/dossiers/ai-demand/increment-analyses/{analysis_id}/candidates/{inc_id}/review",
                json={"status": "deferred", "reason": "等待更多证据", "reviewer": "user"},
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["analysis"]["increments"][0]["status"] == "deferred"
            assert reviewed.json()["formal_write_performed"] is False
            assert list(cognition_conn.iterdump()) == cognition_before

            reused = client.post(
                "/api/research-os/dossiers/ai-demand/increment-analyses",
                json=_body().model_dump(mode="json"),
            )
            assert reused.status_code == 200
            assert reused.json()["reused"] is True
            assert reused.json()["analysis"]["increments"][0]["status"] == "deferred"

            missing_dossier = client.get(
                "/api/research-os/dossiers/no-such-dossier/increment-analyses"
            )
            assert missing_dossier.status_code == 404

            invalid_ref = _body(run_key="bad-http").model_dump(mode="json")
            invalid_ref["increments"][0]["evidence_chunk_ids"] = ["missing:chunk"]
            bad = client.post(
                "/api/research-os/dossiers/ai-demand/increment-analyses",
                json=invalid_ref,
            )
            assert bad.status_code == 422
    finally:
        report_conn.close()
        cognition_conn.close()
