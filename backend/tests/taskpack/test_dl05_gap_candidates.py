from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import topic_candidates as topic_api
from app.research.dossier import DossierUpsert, TopicDossierService
from app.research.gap_candidates import GapCandidateService, TopicCandidateReviewInput
from app.research.increment_candidates import (
    IncrementAnalysisInput,
    IncrementCandidateInput,
    IncrementCandidateService,
)
from app.taskpack.manifest import sha256_file
from app.taskpack.validation_cache import CachingTaskPackImporter


def _research_context(dossier_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-06T01:00:00+08:00",
        "direction": {
            "dossier_id": dossier_id,
            "title": "AI 生产率与需求约束",
            "direction": "研究生产率、劳动收入与总需求之间的反馈。",
            "scope_include": [],
            "scope_exclude": [],
        },
        "topic_state": {
            "formal_topic_bound": False,
            "planning_only": True,
            "dossier_updated_at": "2026-09-06T01:00:00+08:00",
            "needs_refresh": False,
            "source_changes": [],
            "source_versions": {},
            "sources": [],
            "omitted_sources": [],
        },
        "task": {
            "task_id": None,
            "task_type": "summary",
            "query": "AI 生产率是否会形成需求约束？",
            "evidence_context_mode": "none",
            "selected_cognition_object_ids": [],
            "allow_network": False,
            "allow_external_sources": False,
        },
        "warnings": [],
    }


def _result(pack: Path, *, invalid: bool = False) -> dict:
    claims = [
        {
            "id": "claim_001",
            "text": "现有材料显示生产率收益与劳动收入传导需要分开检验。",
            "epistemic_state": "supported",
            "evidence_refs": ["M04:ch1:0001"],
        }
    ]
    if invalid:
        claims.append(
            {
                "id": "claim_002",
                "text": "这条 claim 故意没有证据，必须使 Gate 失败。",
                "epistemic_state": "supported",
                "evidence_refs": [],
            }
        )
    return {
        "schema_version": "1.0",
        "task_id": pack.name,
        "task_type": "summary",
        "query": "AI 生产率是否会形成需求约束？",
        "summary": "test",
        "claims": claims,
        "tensions": [],
        "uncertainties": [],
        "open_questions": [
            "企业利润率改善是否会通过工资或投资重新传导到总需求？"
            if not invalid
            else "INVALID TASK MUST NOT BECOME A NEW CANDIDATE"
        ],
        "additional_evidence_needed": [
            {
                "question": "需要哪些劳动收入数据验证需求约束？",
                "reason": "当前 Evidence 只有企业侧材料，缺少劳动收入分配证据。",
            }
        ],
        "worker": {"tool": "codex", "model": "test-model"},
        "generated_at": "2026-09-06T01:10:00+08:00",
    }


def _complete_dossier_task(tk_env, dossier_id: str) -> Path:
    created = tk_env["builder"].create_task(
        task_type="summary",
        query="AI 生产率是否会形成需求约束？",
        evidence_refs=[tk_env["refs"][0]],
        research_context=_research_context(dossier_id),
        now=datetime(2026, 9, 6, 1, 0, 0),
    )
    completed_root = tk_env["root"] / "completed"
    completed_root.mkdir(parents=True, exist_ok=True)
    pack = completed_root / created.task_id
    shutil.move(str(created.task_path), str(pack))
    (pack / "result").mkdir(parents=True, exist_ok=True)
    (pack / "result" / "result.json").write_text(
        json.dumps(_result(pack), ensure_ascii=False), encoding="utf-8"
    )
    run_meta = {
        "worker_tool": "codex",
        "model": "test-model",
        "prompt_version": "taskpack-synthesis-v1",
        "prompt_sha256": sha256_file(pack / "AGENT_INSTRUCTION.md"),
        "task_manifest_sha256": sha256_file(pack / "manifest.json"),
        "started_at": "2026-09-06T01:05:00+08:00",
        "completed_at": "2026-09-06T01:10:00+08:00",
    }
    (pack / "result" / "run_meta.json").write_text(
        json.dumps(run_meta, ensure_ascii=False), encoding="utf-8"
    )
    (pack / "result" / "DONE").write_text("", encoding="utf-8")
    return pack


def _setup(tk_env):
    cfg = tk_env["cfg"]
    conn = tk_env["conn"]
    dossier_id = "ai-demand"
    TopicDossierService(cfg, conn, None).upsert(
        dossier_id,
        DossierUpsert(
            title="AI 生产率与需求约束",
            direction="研究生产率、劳动收入与总需求之间的反馈。",
            evidence_refs=[tk_env["refs"][0]],
        ),
    )
    IncrementCandidateService(cfg, conn, None).ingest(
        dossier_id,
        IncrementAnalysisInput(
            source_report_document_id="M04",
            analysis_run_key="gap-seed",
            increments=[
                IncrementCandidateInput(
                    classification="cannot_determine",
                    title="工资传导尚无法判断",
                    statement="AI 生产率收益是否会形成持续工资增长仍无法判断。",
                    difference_reason="当前报告没有足够的劳动收入时间序列。",
                )
            ],
        ),
    )
    pack = _complete_dossier_task(tk_env, dossier_id)
    importer = CachingTaskPackImporter(cfg, conn, None)
    return dossier_id, pack, importer


def test_refresh_uses_only_gate_passed_results_and_preserves_review(tk_env):
    dossier_id, pack, importer = _setup(tk_env)
    service = GapCandidateService(tk_env["cfg"], tk_env["conn"], None, importer)

    first = service.refresh(dossier_id)
    assert first.invalid_task_ids == []
    assert first.created == 3
    rows = service.list_candidates(dossier_id)
    assert {row.source_type for row in rows} == {
        "open_question",
        "additional_evidence_needed",
        "cannot_determine",
    }
    assert all(row.formal_write_performed is False for row in rows)

    open_row = next(row for row in rows if row.source_type == "open_question")
    sqlite_before = list(tk_env["conn"].iterdump())
    accepted = service.review(
        dossier_id,
        open_row.candidate_id,
        TopicCandidateReviewInput(status="accepted", reason="进入下一轮研究"),
    )
    assert accepted.status == "accepted"
    assert accepted.formal_write_performed is False
    assert list(tk_env["conn"].iterdump()) == sqlite_before

    second = service.refresh(dossier_id)
    assert second.created == 0
    assert second.reused == 3
    assert service.get(dossier_id, open_row.candidate_id).status == "accepted"

    # Change the result into a Gate-invalid payload. The new open question must
    # never be promoted into the candidate store.
    (pack / "result" / "result.json").write_text(
        json.dumps(_result(pack, invalid=True), ensure_ascii=False), encoding="utf-8"
    )
    third = service.refresh(dossier_id)
    assert pack.name in third.invalid_task_ids
    assert not any(
        "INVALID TASK MUST NOT" in row.research_question
        for row in service.list_candidates(dossier_id)
    )


def test_dossier_source_version_change_becomes_deterministic_gap(tk_env):
    dossier_id, _pack, importer = _setup(tk_env)
    service = GapCandidateService(tk_env["cfg"], tk_env["conn"], None, importer)
    service.refresh(dossier_id)

    with tk_env["conn"]:
        tk_env["conn"].execute(
            "UPDATE chunks SET content_hash = ? WHERE id = ?",
            ("changed-hash", "M04:ch1:0001"),
        )

    report = service.refresh(dossier_id)
    rows = service.list_candidates(dossier_id)
    changed = [row for row in rows if row.source_type == "changed_source"]
    assert len(changed) == 1
    assert changed[0].source_ref == "evidence:M04:ch1:0001"
    assert changed[0].candidate_id in report.candidate_ids
    assert changed[0].formal_write_performed is False


def test_topic_candidate_http_refresh_list_and_review_are_planning_only(tk_env):
    dossier_id, _pack, importer = _setup(tk_env)
    app = FastAPI()
    app.state.cfg = tk_env["cfg"]
    app.state.conn = tk_env["conn"]
    app.state.cognition = {"enabled": False}
    app.state.taskpack_importer = importer
    app.include_router(topic_api.router)

    with TestClient(app) as client:
        refreshed = client.post(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/refresh"
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["auto_create_topic"] is False
        assert refreshed.json()["auto_apply"] is False
        assert refreshed.json()["formal_write_performed"] is False

        listed = client.get(f"/api/research-os/dossiers/{dossier_id}/topic-candidates")
        assert listed.status_code == 200
        candidates = listed.json()["candidates"]
        assert candidates
        candidate_id = candidates[0]["candidate_id"]

        sqlite_before = list(tk_env["conn"].iterdump())
        reviewed = client.post(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/{candidate_id}/review",
            json={"status": "accepted", "reason": "用于下一轮研究", "reviewer": "user"},
        )
        assert reviewed.status_code == 200
        body = reviewed.json()
        assert body["selected_for_research"] is True
        assert body["auto_create_topic"] is False
        assert body["auto_apply"] is False
        assert body["formal_write_performed"] is False
        assert list(tk_env["conn"].iterdump()) == sqlite_before

        missing = client.get(
            f"/api/research-os/dossiers/{dossier_id}/topic-candidates/tc_0000000000000000"
        )
        assert missing.status_code == 404
