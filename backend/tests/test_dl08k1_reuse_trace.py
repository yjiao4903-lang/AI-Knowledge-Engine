from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_os
from app.contracts.cognition import CognitionContextItem
from app.core.config import Config
from app.research.return_candidates import (
    ResearchReturnBatchRecord,
    ResearchReturnCandidateRecord,
    TargetSnapshot,
)
from app.research.reuse_trace import ReuseTraceReadService
from app.storage.migrations import init_schema
from app.storage.sqlite import connect
from app.taskpack.schemas import ResultEnvelope

OBJECT_ID = "cog:04_判断台账/income"
OTHER_ID = "cog:04_判断台账/other"
FORMAL_UUID = "11111111-1111-1111-1111-111111111111"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _task(
    root: Path,
    task_id: str,
    *,
    created_at: str,
    object_id: str = OBJECT_ID,
    include_candidate: bool = True,
    candidate_id: str | None = None,
    with_marker: bool = False,
    formal_write_performed: bool = False,
    question: str | None = None,
    other_candidate: bool = False,
) -> Path:
    pack = root / "completed" / task_id
    (pack / "result").mkdir(parents=True, exist_ok=True)
    _write_json(
        pack / "task.yaml",
        {
            "task_id": task_id,
            "task_type": "causal_synthesis",
            "query": f"query for {task_id}",
            "created_at": created_at,
        },
    )
    contexts = [
        CognitionContextItem(
            context_id=f"ctx-{task_id}-target",
            object_type="judgment",
            object_id=object_id,
            content_hash=f"snapshot-{task_id}",
            title="historical title",
            excerpt="historical excerpt",
        ),
        CognitionContextItem(
            context_id=f"ctx-{task_id}-other",
            object_type="judgment",
            object_id=OTHER_ID,
            content_hash=f"other-{task_id}",
            title="other title",
            excerpt="other excerpt",
        ),
    ]
    (pack / "cognition_context.jsonl").write_text(
        "\n".join(row.model_dump_json() for row in contexts) + "\n",
        encoding="utf-8",
    )

    result = ResultEnvelope.model_validate(
        {
            "schema_version": "1.0",
            "task_id": task_id,
            "task_type": "causal_synthesis",
            "query": f"query for {task_id}",
            "summary": "summary",
            "claims": [],
            "tensions": [],
            "uncertainties": [],
            "open_questions": [question] if question else [],
            "additional_evidence_needed": (
                [{"question": f"evidence for {task_id}?", "reason": "explicit gap"}]
                if question
                else []
            ),
            "worker": {"tool": "codex", "model": "fixture"},
            "generated_at": created_at,
        }
    )
    _write_json(pack / "result" / "result.json", result.model_dump(mode="json"))
    (pack / "result" / "IMPORTED").write_text("", encoding="utf-8")

    candidates: list[ResearchReturnCandidateRecord] = []
    if include_candidate:
        cid = candidate_id or f"rc-{task_id}"
        candidates.append(
            ResearchReturnCandidateRecord(
                intent="revise_judgment",
                target_cognition_object_ids=[object_id],
                proposed_text=f"proposal {task_id}",
                reason="fixture reason",
                evidence_chunk_ids=["M01:s1:c1"],
                source_claim_ids=["claim_001"],
                source_tension_ids=[],
                proposer="external_worker",
                candidate_id=cid,
                task_id=task_id,
                task_query=f"query for {task_id}",
                result_generated_at=created_at,
                target_snapshots=[
                    TargetSnapshot(
                        object_id=object_id,
                        object_type="judgment",
                        baseline_content_hash=f"snapshot-{task_id}",
                        current_content_hash=f"snapshot-{task_id}",
                        version_state="unchanged",
                        checked_at=created_at,
                    )
                ],
                has_version_conflict=False,
                version_check_incomplete=False,
                status="accepted",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        if other_candidate:
            candidates.append(
                ResearchReturnCandidateRecord(
                    intent="revise_judgment",
                    target_cognition_object_ids=[OTHER_ID],
                    proposed_text="other proposal",
                    reason="other fixture reason",
                    evidence_chunk_ids=["M01:s1:c1"],
                    source_claim_ids=[],
                    source_tension_ids=[],
                    proposer="external_worker",
                    candidate_id=f"rc-{task_id}-other",
                    task_id=task_id,
                    task_query=f"query for {task_id}",
                    result_generated_at=created_at,
                    target_snapshots=[
                        TargetSnapshot(
                            object_id=OTHER_ID,
                            object_type="judgment",
                            baseline_content_hash="other",
                            current_content_hash="other",
                            version_state="unchanged",
                            checked_at=created_at,
                        )
                    ],
                    status="accepted",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        batch = ResearchReturnBatchRecord(
            task_id=task_id,
            updated_at=created_at,
            candidates=candidates,
        )
        (pack / "result" / "return_candidates.json").write_text(
            batch.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

        if with_marker:
            marker = {
                "schema_version": "1.0",
                "task_id": task_id,
                "candidate_id": cid,
                "intent": "revise_judgment",
                "proposal_id": f"proposal-{task_id}",
                "proposal_item_id": f"item-{task_id}",
                "target_identities": [
                    {
                        "ke_target_id": object_id,
                        "cognition_target_id": FORMAL_UUID,
                        "object_type": "judgment",
                        "source_path": "historical/04_判断台账/income.md",
                    }
                ],
                "published_at": created_at,
                "published_target_hashes": {object_id: "official-hash-before"},
                "preview": {
                    "previewed_at": created_at,
                    "target_hashes": {object_id: "official-hash-before"},
                    "response": {"ok": True},
                },
                "apply": (
                    {
                        "applied_at": created_at,
                        "response": {"ok": True},
                        "readback": {"item": {"id": FORMAL_UUID}},
                    }
                    if formal_write_performed
                    else None
                ),
                "writer": "cognition_app",
                "formal_write_performed": formal_write_performed,
            }
            _write_json(pack / "result" / "formal_handoffs" / f"{cid}.json", marker)
    return pack


def _environment(tmp_path: Path):
    cfg = Config()
    cfg.taskpack.root_dir = str(tmp_path / "taskpacks")
    cfg.cognition.root = str(tmp_path / "cognition")
    Path(cfg.cognition.root, "04_判断台账").mkdir(parents=True)

    conn = connect(tmp_path / "catalog_cognition.db", check_same_thread=False)
    init_schema(conn)
    renamed = Path(cfg.cognition.root) / "04_判断台账" / "renamed.md"
    with conn:
        conn.execute(
            "INSERT INTO documents(id, title, source_path, file_name, sha256, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                OBJECT_ID,
                "current renamed title",
                str(renamed),
                renamed.name,
                "current-ke-sha256",
                "2026-09-12T20:00:00+08:00",
            ),
        )
        other = Path(cfg.cognition.root) / "04_判断台账" / "other.md"
        conn.execute(
            "INSERT INTO documents(id, title, source_path, file_name, sha256, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (OTHER_ID, "other", str(other), other.name, "other-sha", "2026-09-12T20:00:00+08:00"),
        )

    root = Path(cfg.taskpack.root_dir)
    task_a = _task(
        root,
        "task-a",
        created_at="2026-09-10T09:00:00+08:00",
        with_marker=True,
        formal_write_performed=True,
        question="question-a?",
        other_candidate=True,
    )
    task_b = _task(
        root,
        "task-b",
        created_at="2026-09-11T09:00:00+08:00",
        with_marker=False,
        question="question-b?",
    )
    _task(
        root,
        "task-unlinked",
        created_at="2026-09-09T09:00:00+08:00",
        object_id=OTHER_ID,
        with_marker=False,
        question="should-not-appear?",
    )
    return cfg, conn, task_a, task_b


def _snapshot_files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_reuse_trace_orders_exact_task_uses_and_avoids_false_candidate_linkage(tmp_path):
    cfg, conn, _task_a, _task_b = _environment(tmp_path)
    try:
        body = ReuseTraceReadService(cfg, conn).build(OBJECT_ID)
        assert body["object"] == {
            "object_id": OBJECT_ID,
            "resolved": True,
            "object_type": "judgment",
            "title": "current renamed title",
            "content_hash": "current-ke-sha256",
        }
        assert [row["task_id"] for row in body["task_uses"]] == ["task-a", "task-b"]
        assert all(row["role"] == "cognition_context" for row in body["task_uses"])
        assert [row["candidate_id"] for row in body["return_events"]] == [
            "rc-task-a",
            "rc-task-b",
        ]
        assert all(row["target_object_id"] == OBJECT_ID for row in body["return_events"])
        assert "rc-task-a-other" not in {row["candidate_id"] for row in body["return_events"]}
        assert "task-unlinked" not in {row["task_id"] for row in body["task_uses"]}
    finally:
        conn.close()


def test_formal_marker_dual_identity_and_missing_marker_are_fail_visible(tmp_path):
    cfg, conn, _task_a, _task_b = _environment(tmp_path)
    try:
        body = ReuseTraceReadService(cfg, conn).build(OBJECT_ID)
        event_a, event_b = body["return_events"]
        assert event_a["formal_handoff"] == {
            "state": "present",
            "proposal_id": "proposal-task-a",
            "proposal_item_id": "item-task-a",
            "cognition_uuid": FORMAL_UUID,
            "marker_source_path": "historical/04_判断台账/income.md",
            "previewed_at": "2026-09-10T09:00:00+08:00",
            "applied_at": "2026-09-10T09:00:00+08:00",
            "formal_write_performed": True,
        }
        assert event_b["formal_handoff"]["state"] == "missing"
        assert any(
            row["code"] == "formal_handoff_missing" and row["candidate_id"] == "rc-task-b"
            for row in body["quality"]["issues"]
        )

        # Current derived source path was renamed, but the reverse key stays the
        # exact historical KE id and UUID is shown only from the durable marker.
        typo = ReuseTraceReadService(cfg, conn).build(OBJECT_ID + " ")
        assert typo["task_uses"] == []
        assert typo["return_events"] == []
        assert typo["object"]["resolved"] is False
    finally:
        conn.close()


def test_unresolved_questions_are_explicit_and_only_from_linked_gate_proven_tasks(tmp_path):
    cfg, conn, _task_a, _task_b = _environment(tmp_path)
    try:
        body = ReuseTraceReadService(cfg, conn).build(OBJECT_ID)
        questions = [(row["task_id"], row["kind"], row["question"]) for row in body["unresolved_questions"]]
        assert questions == [
            ("task-a", "additional_evidence_needed", "evidence for task-a?"),
            ("task-a", "open_question", "question-a?"),
            ("task-b", "additional_evidence_needed", "evidence for task-b?"),
            ("task-b", "open_question", "question-b?"),
        ]
        assert all("should-not-appear" not in row["question"] for row in body["unresolved_questions"])
    finally:
        conn.close()


def test_malformed_marker_and_missing_task_artifact_remain_read_only_and_fail_visible(tmp_path):
    cfg, conn, task_a, task_b = _environment(tmp_path)
    try:
        marker = task_a / "result" / "formal_handoffs" / "rc-task-a.json"
        marker.write_text("[]\n", encoding="utf-8")
        (task_b / "task.yaml").unlink()

        body = ReuseTraceReadService(cfg, conn).build(OBJECT_ID)
        event_a = next(row for row in body["return_events"] if row["candidate_id"] == "rc-task-a")
        assert event_a["formal_handoff"]["state"] == "unreadable"
        codes = {row["code"] for row in body["quality"]["issues"]}
        assert "formal_handoff_unreadable" in codes
        assert "task_metadata_missing" in codes
        assert [row["task_id"] for row in body["task_uses"]] == ["task-b", "task-a"]
    finally:
        conn.close()


def test_repeated_read_is_deterministic_and_performs_no_write_or_external_call(tmp_path, monkeypatch):
    cfg, conn, _task_a, _task_b = _environment(tmp_path)
    root = Path(cfg.taskpack.root_dir)
    before_files = _snapshot_files(root)
    before_db = list(conn.iterdump())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("DL-08K1 read model attempted an external process/network call")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)

    try:
        service = ReuseTraceReadService(cfg, conn)
        first = service.build(OBJECT_ID)
        second = service.build(OBJECT_ID)
        assert first == second
        assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
            second, ensure_ascii=False, sort_keys=True
        )
        assert _snapshot_files(root) == before_files
        assert list(conn.iterdump()) == before_db
    finally:
        conn.close()


def test_api_returns_read_model_payload_and_malformed_marker_stays_http_200(tmp_path):
    cfg, conn, task_a, _task_b = _environment(tmp_path)
    marker = task_a / "result" / "formal_handoffs" / "rc-task-a.json"
    marker.write_text("not-json\n", encoding="utf-8")

    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = SimpleNamespace()
    app.state.cognition = {"enabled": True, "conn": conn}
    app.include_router(research_os.router)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/research-os/reuse-trace",
                params={"object_id": OBJECT_ID},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["object"]["object_id"] == OBJECT_ID
        assert body["return_events"][0]["formal_handoff"]["state"] == "unreadable"
        assert any(row["code"] == "formal_handoff_unreadable" for row in body["quality"]["issues"])
    finally:
        conn.close()
