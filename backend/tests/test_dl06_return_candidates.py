from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import return_candidates as return_api
from app.contracts.cognition import CognitionContextItem
from app.core.config import Config
from app.research.return_candidates import (
    ResearchReturnBatchInput,
    ResearchReturnCandidateInput,
    ResearchReturnCandidateService,
    ReturnCandidateReviewInput,
)
from app.storage.migrations import init_schema
from app.storage.sqlite import connect
from app.synthesis.schemas import EvidenceRef
from app.taskpack.builder import TaskPackBuilder
from app.taskpack.importer import TaskPackImporter
from app.taskpack.manifest import sha256_file


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
    cfg.taskpack.root_dir = str(data / "taskpacks")
    cfg.cognition.root = str(cognition)

    report_conn = connect(data / "catalog.db", check_same_thread=False)
    cognition_conn = connect(data / "catalog_cognition.db", check_same_thread=False)
    init_schema(report_conn)
    init_schema(cognition_conn)

    _seed_document(
        report_conn,
        doc_id="M06",
        path=reports / "M06.md",
        title="AI 收入传导研究",
        doc_hash="report-v1",
        chunk_id="M06:s1:c1",
        chunk_hash="evidence-v1",
        text="企业 AI 生产率改善并不自动等价于劳动收入同步增长。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:j-income",
        path=cognition / "04_判断台账" / "income.md",
        title="AI 收入传导当前判断",
        doc_hash="judgment-v1",
        chunk_id="cog:j-income:s1:c1",
        chunk_hash="judgment-chunk-v1",
        text="旧判断：AI 生产率改善最终会较快传导到劳动收入。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:q-demand",
        path=cognition / "03_问题池" / "demand.md",
        title="收入传导是否形成需求约束",
        doc_hash="question-v1",
        chunk_id="cog:q-demand:s1:c1",
        chunk_hash="question-chunk-v1",
        text="问题：劳动收入传导滞后是否足以约束总需求？",
    )

    evidence = EvidenceRef(
        source_type="report",
        document_id="M06",
        chunk_id="M06:s1:c1",
        content_hash="evidence-v1",
    )
    cognition_context = [
        CognitionContextItem(
            context_id="CTX001",
            object_type="judgment",
            object_id="cog:j-income",
            content_hash="judgment-v1",
            title="AI 收入传导当前判断",
            excerpt="旧判断：AI 生产率改善最终会较快传导到劳动收入。",
        ),
        CognitionContextItem(
            context_id="CTX002",
            object_type="question",
            object_id="cog:q-demand",
            content_hash="question-v1",
            title="收入传导是否形成需求约束",
            excerpt="问题：劳动收入传导滞后是否足以约束总需求？",
        ),
    ]
    builder = TaskPackBuilder(cfg, report_conn, cognition_conn)
    created = builder.create_task(
        task_type="causal_synthesis",
        query="AI 生产率收益是否会因收入传导滞后形成需求约束？",
        evidence_refs=[evidence],
        cognition_context=cognition_context,
        now=datetime(2026, 9, 6, 1, 0, 0),
    )

    completed = Path(cfg.taskpack.root_dir) / "completed"
    completed.mkdir(parents=True, exist_ok=True)
    pack = completed / created.task_id
    shutil.move(str(created.task_path), str(pack))
    result = {
        "schema_version": "1.0",
        "task_id": pack.name,
        "task_type": "causal_synthesis",
        "query": "AI 生产率收益是否会因收入传导滞后形成需求约束？",
        "summary": "现有 Evidence 支持重新审视收入传导速度。",
        "claims": [
            {
                "id": "claim_001",
                "text": "生产率改善并不保证劳动收入同步增长。",
                "epistemic_state": "supported",
                "evidence_refs": ["M06:s1:c1"],
            }
        ],
        "tensions": [
            {
                "id": "tension_001",
                "text": "企业利润改善与劳动收入传导速度之间存在待验证张力。",
                "evidence_refs": ["M06:s1:c1"],
            }
        ],
        "uncertainties": [],
        "open_questions": ["收入传导滞后持续多久才会形成需求约束？"],
        "additional_evidence_needed": [
            {"question": "需要工资和就业数据吗？", "reason": "当前 Evidence 只覆盖企业侧。"}
        ],
        "worker": {"tool": "codex", "model": "test-model"},
        "generated_at": "2026-09-06T01:10:00+08:00",
    }
    (pack / "result" / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    run_meta = {
        "worker_tool": "codex",
        "model": "test-model",
        "prompt_version": "taskpack-synthesis-v1",
        "prompt_sha256": sha256_file(pack / "AGENT_INSTRUCTION.md"),
        "task_manifest_sha256": sha256_file(pack / "manifest.json"),
        "started_at": "2026-09-06T01:05:00+08:00",
        "completed_at": "2026-09-06T01:10:00+08:00",
    }
    (pack / "result" / "run_meta.json").write_text(json.dumps(run_meta), encoding="utf-8")
    (pack / "result" / "DONE").write_text("", encoding="utf-8")

    importer = TaskPackImporter(cfg, report_conn, cognition_conn)
    assert importer.import_task(pack).passed is True
    return cfg, report_conn, cognition_conn, importer, pack


def _revision() -> ResearchReturnCandidateInput:
    return ResearchReturnCandidateInput(
        intent="revise_judgment",
        target_cognition_object_ids=["cog:j-income"],
        proposed_text="修订判断：AI 生产率改善到劳动收入的传导可能存在显著时滞。",
        reason="Gate-passed 研究结果与旧判断的快速传导假设存在张力。",
        evidence_chunk_ids=["M06:s1:c1"],
        source_claim_ids=["claim_001"],
        source_tension_ids=["tension_001"],
    )


def test_return_candidate_is_idempotent_reviewable_and_never_writes_cognition(tmp_path):
    cfg, report_conn, cognition_conn, importer, pack = _environment(tmp_path)
    service = ResearchReturnCandidateService(cfg, report_conn, cognition_conn, importer)
    try:
        cognition_before = list(cognition_conn.iterdump())
        first, created, reused = service.ingest(
            pack.name,
            ResearchReturnBatchInput(candidates=[_revision()]),
        )
        assert created == 1 and reused == 0
        candidate = first.candidates[0]
        assert candidate.target_snapshots[0].baseline_content_hash == "judgment-v1"
        assert candidate.target_snapshots[0].current_content_hash == "judgment-v1"
        assert candidate.target_snapshots[0].version_state == "unchanged"
        assert candidate.has_version_conflict is False
        assert candidate.formal_preview_supported is False
        assert candidate.formal_apply_supported is False
        assert candidate.formal_write_performed is False
        assert list(cognition_conn.iterdump()) == cognition_before

        reviewed = service.review(
            pack.name,
            candidate.candidate_id,
            ReturnCandidateReviewInput(status="accepted", reason="进入未来 Cognition Preview"),
        )
        assert reviewed.candidates[0].status == "accepted"
        assert reviewed.candidates[0].formal_write_performed is False
        assert list(cognition_conn.iterdump()) == cognition_before

        second, created2, reused2 = service.ingest(
            pack.name,
            ResearchReturnBatchInput(candidates=[_revision()]),
        )
        assert created2 == 0 and reused2 == 1
        assert second.candidates[0].candidate_id == candidate.candidate_id
        assert second.candidates[0].status == "accepted"
        assert list(cognition_conn.iterdump()) == cognition_before
    finally:
        report_conn.close()
        cognition_conn.close()


def test_target_version_change_and_missing_are_explicit_conflicts(tmp_path):
    cfg, report_conn, cognition_conn, importer, pack = _environment(tmp_path)
    service = ResearchReturnCandidateService(cfg, report_conn, cognition_conn, importer)
    try:
        record, _, _ = service.ingest(pack.name, ResearchReturnBatchInput(candidates=[_revision()]))
        candidate_id = record.candidates[0].candidate_id

        with cognition_conn:
            cognition_conn.execute(
                "UPDATE documents SET sha256 = ?, title = ? WHERE id = ?",
                ("judgment-v2", "AI 收入传导更新判断", "cog:j-income"),
            )
            cognition_conn.execute(
                "UPDATE chunks SET plain_text = ?, content_hash = ? WHERE document_id = ?",
                ("新版本：收入传导可能显著滞后。", "judgment-chunk-v2", "cog:j-income"),
            )
        changed = service.refresh_target_versions(pack.name).candidates[0]
        assert changed.candidate_id == candidate_id
        assert changed.target_snapshots[0].version_state == "changed"
        assert changed.target_snapshots[0].current_content_hash == "judgment-v2"
        assert "显著滞后" in (changed.target_snapshots[0].current_excerpt or "")
        assert changed.has_version_conflict is True

        with cognition_conn:
            cognition_conn.execute("DELETE FROM chunks WHERE document_id = ?", ("cog:j-income",))
            cognition_conn.execute("DELETE FROM sections WHERE document_id = ?", ("cog:j-income",))
            cognition_conn.execute("DELETE FROM documents WHERE id = ?", ("cog:j-income",))
        missing = service.refresh_target_versions(pack.name).candidates[0]
        assert missing.target_snapshots[0].version_state == "missing"
        assert missing.has_version_conflict is True
        assert missing.formal_write_performed is False
    finally:
        report_conn.close()
        cognition_conn.close()


def test_return_candidate_rejects_out_of_scope_targets_and_evidence(tmp_path):
    cfg, report_conn, cognition_conn, importer, pack = _environment(tmp_path)
    service = ResearchReturnCandidateService(cfg, report_conn, cognition_conn, importer)
    try:
        outside = _revision().model_copy(
            update={"target_cognition_object_ids": ["cog:not-selected"]}
        )
        try:
            service.ingest(pack.name, ResearchReturnBatchInput(candidates=[outside]))
            assert False, "expected out-of-scope target rejection"
        except ValueError as exc:
            assert "not selected into this TaskPack" in str(exc)

        bad_evidence = _revision().model_copy(update={"evidence_chunk_ids": ["M06:outside"]})
        try:
            service.ingest(pack.name, ResearchReturnBatchInput(candidates=[bad_evidence]))
            assert False, "expected evidence membership rejection"
        except ValueError as exc:
            assert "outside TaskPack" in str(exc)
    finally:
        report_conn.close()
        cognition_conn.close()


def test_return_candidate_api_is_staging_only_and_maps_state_errors(tmp_path):
    cfg, report_conn, cognition_conn, importer, pack = _environment(tmp_path)
    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = report_conn
    app.state.cognition = {"enabled": True, "conn": cognition_conn}
    app.state.taskpack_importer = importer
    app.include_router(return_api.router)
    try:
        payload = {"candidates": [_revision().model_dump(mode="json")]}
        with TestClient(app) as client:
            created = client.post(
                f"/api/research-os/tasks/{pack.name}/return-candidates",
                json=payload,
            )
            assert created.status_code == 200, created.text
            body = created.json()
            assert body["created"] == 1
            assert body["formal_preview_supported"] is False
            assert body["formal_apply_supported"] is False
            assert body["auto_apply"] is False
            assert body["formal_write_performed"] is False
            candidate = body["return_candidates"]["candidates"][0]

            reviewed = client.post(
                f"/api/research-os/tasks/{pack.name}/return-candidates/{candidate['candidate_id']}/review",
                json={"status": "deferred", "reason": "等待真实 Preview contract", "reviewer": "user"},
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["candidate"]["status"] == "deferred"
            assert reviewed.json()["accepted_for_future_preview"] is False
            assert reviewed.json()["formal_write_performed"] is False

            missing = client.get("/api/research-os/tasks/not-a-real-task/return-candidates")
            assert missing.status_code == 404
    finally:
        report_conn.close()
        cognition_conn.close()
