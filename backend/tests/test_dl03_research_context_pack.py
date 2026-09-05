from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import synthesis as synthesis_api
from app.core.config import Config
from app.research.context_pack import build_research_context
from app.research.dossier import DossierUpsert, TopicDossierService
from app.storage.migrations import init_schema
from app.storage.sqlite import connect
from app.synthesis.schemas import EvidenceRef
from app.taskpack.builder import TaskPackBuilder
from app.taskpack.importer import TaskPackImporter
from app.taskpack.schemas import Manifest


def _seed_document(conn, *, doc_id: str, path: Path, title: str, doc_hash: str, chunk_id: str, chunk_hash: str, text: str):
    section_id = f"{doc_id}:s1"
    with conn:
        conn.execute(
            "INSERT INTO documents(id, title, source_path, file_name, sha256, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, title, str(path), path.name, doc_hash, "2026-09-05T12:00:00+08:00"),
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
    (cognition / "03_问题池").mkdir(parents=True)
    (cognition / "04_判断台账").mkdir(parents=True)
    reports.mkdir(parents=True)

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
        doc_id="M99",
        path=reports / "M99_最终报告.md",
        title="AI 需求约束报告",
        doc_hash="report-v1",
        chunk_id="M99:s1:c1",
        chunk_hash="evidence-v1",
        text="企业采用 AI 后，生产率收益与工资增长之间可能存在分配时滞。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:q-demand",
        path=cognition / "03_问题池" / "demand.md",
        title="AI 是否内生制造需求不足",
        doc_hash="question-v1",
        chunk_id="cog:q-demand:s1:c1",
        chunk_hash="question-chunk-v1",
        text="权威 Cognition：需要检验生产率提升是否快于劳动收入和总需求增长。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:j-capex",
        path=cognition / "04_判断台账" / "capex.md",
        title="AI CAPEX 当前判断",
        doc_hash="judgment-v1",
        chunk_id="cog:j-capex:s1:c1",
        chunk_hash="judgment-chunk-v1",
        text="权威 Cognition：短期现金流改善与长期增长预期下降必须分开判断。",
    )

    evidence = EvidenceRef(
        source_type="report",
        document_id="M99",
        section_id="M99:s1",
        chunk_id="M99:s1:c1",
        content_hash="evidence-v1",
        start_line=1,
        end_line=10,
    )
    TopicDossierService(cfg, report_conn, cognition_conn).upsert(
        "ai-demand",
        DossierUpsert(
            title="AI 生产率与需求约束",
            direction="研究 AI 生产率、收入分配与总需求之间的反馈。",
            scope_include=["企业 AI 采用", "劳动收入"],
            scope_exclude=["纯 benchmark"],
            question_ids=["cog:q-demand"],
            judgment_ids=["cog:j-capex"],
            evidence_refs=[evidence],
        ),
    )
    return cfg, report_conn, cognition_conn, evidence


def test_dossier_backed_taskpack_re_resolves_cognition_and_writes_manifested_context(tmp_path):
    cfg, report_conn, cognition_conn, evidence = _environment(tmp_path)
    builder = TaskPackBuilder(cfg, report_conn, cognition_conn)
    importer = TaskPackImporter(cfg, report_conn, cognition_conn)
    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = report_conn
    app.state.cognition = {"enabled": True, "conn": cognition_conn}
    app.state.taskpack_builder = builder
    app.state.taskpack_importer = importer
    app.include_router(synthesis_api.router)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/synthesis/tasks",
                json={
                    "task_type": "causal_synthesis",
                    "query": "AI 生产率提升是否可能形成需求约束？",
                    "dossier_id": "ai-demand",
                    "evidence_context_mode": "none",
                    "evidence_refs": [evidence.model_dump(mode="json")],
                    "cognition_object_ids": ["cog:q-demand"],
                    # Legacy payload is intentionally forged. Server must ignore
                    # its text/hash and use only the stable object identity/type hint.
                    "cognition_context": [
                        {
                            "context_id": "FAKE",
                            "object_type": "question",
                            "object_id": "cog:q-demand",
                            "content_hash": "client-fake-hash",
                            "title": "CLIENT FAKE TITLE",
                            "excerpt": "CLIENT FAKE EXCERPT",
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["research_context_included"] is True
            assert payload["cognition_context_count"] == 1
            pack = Path(payload["task_path"])

            context = json.loads((pack / "research_context.json").read_text(encoding="utf-8"))
            brief = (pack / "research_brief.md").read_text(encoding="utf-8")
            cognition_rows = [
                json.loads(line)
                for line in (pack / "cognition_context.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert context["direction"]["dossier_id"] == "ai-demand"
            assert context["task"]["task_id"] == payload["task_id"]
            assert context["task"]["allow_network"] is False
            assert context["task"]["selected_cognition_object_ids"] == ["cog:q-demand"]
            assert "AI 生产率、收入分配与总需求" in brief
            assert "事实性 claim 必须引用 `evidence.jsonl`" in brief
            assert cognition_rows[0]["context_id"] == "CTX001"
            assert cognition_rows[0]["title"] == "AI 是否内生制造需求不足"
            assert "权威 Cognition" in cognition_rows[0]["excerpt"]
            assert "CLIENT FAKE" not in json.dumps(cognition_rows[0], ensure_ascii=False)
            assert cognition_rows[0]["content_hash"] == "question-v1"

            manifest = Manifest.model_validate_json((pack / "manifest.json").read_text(encoding="utf-8"))
            assert "research_context.json" in manifest.files
            assert "research_brief.md" in manifest.files
            assert "cognition_context.jsonl" in manifest.files

            # Context files are immutable TaskPack inputs and must be covered by Gate 1.
            (pack / "research_context.json").write_text("{}\n", encoding="utf-8")
            gates = importer._gate_manifest(pack)
            assert gates[0].passed is False
            assert "research_context.json" in (gates[0].failure or "")
    finally:
        report_conn.close()
        cognition_conn.close()


def test_old_taskpack_path_remains_compatible_without_dossier(tmp_path):
    cfg, report_conn, cognition_conn, evidence = _environment(tmp_path)
    try:
        created = TaskPackBuilder(cfg, report_conn, cognition_conn).create_task(
            task_type="summary",
            query="Summarize evidence only",
            evidence_refs=[evidence],
        )
        pack = created.task_path
        assert created.research_context_included is False
        assert not (pack / "research_context.json").exists()
        assert not (pack / "research_brief.md").exists()
        manifest = Manifest.model_validate_json((pack / "manifest.json").read_text(encoding="utf-8"))
        assert "research_context.json" not in manifest.files
        assert "research_brief.md" not in manifest.files
    finally:
        report_conn.close()
        cognition_conn.close()


def test_missing_selected_cognition_object_is_rejected_before_task_creation(tmp_path):
    cfg, report_conn, cognition_conn, evidence = _environment(tmp_path)
    builder = TaskPackBuilder(cfg, report_conn, cognition_conn)
    importer = TaskPackImporter(cfg, report_conn, cognition_conn)
    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = report_conn
    app.state.cognition = {"enabled": True, "conn": cognition_conn}
    app.state.taskpack_builder = builder
    app.state.taskpack_importer = importer
    app.include_router(synthesis_api.router)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/synthesis/tasks",
                json={
                    "task_type": "summary",
                    "query": "test",
                    "dossier_id": "ai-demand",
                    "evidence_refs": [evidence.model_dump(mode="json")],
                    "cognition_object_ids": ["cog:missing"],
                },
            )
            assert response.status_code == 400
            assert "cognition object not found" in response.text
        outbox = Path(cfg.taskpack.root_dir) / "outbox"
        assert not outbox.exists() or not any(outbox.iterdir())
    finally:
        report_conn.close()
        cognition_conn.close()


def test_context_budget_reports_omitted_sources_without_silent_drop(tmp_path):
    cfg, report_conn, cognition_conn, _ = _environment(tmp_path)
    try:
        detail = TopicDossierService(cfg, report_conn, cognition_conn).get("ai-demand")
        context = build_research_context(
            detail,
            task_type="summary",
            query="test",
            evidence_context_mode="none",
            selected_cognition=[],
            max_sources=1,
            excerpt_chars=80,
        )
        assert len(context["topic_state"]["sources"]) == 1
        assert context["topic_state"]["omitted_sources"]
        assert "DOSSIER_CONTEXT_BUDGET_OMITTED_SOURCES" in context["warnings"]
    finally:
        report_conn.close()
        cognition_conn.close()
