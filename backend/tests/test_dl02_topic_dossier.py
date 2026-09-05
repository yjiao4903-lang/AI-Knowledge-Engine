from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dossiers as dossiers_api
from app.core.config import Config
from app.research.dossier import DossierUpsert, TopicDossierService
from app.storage.migrations import init_schema
from app.storage.repositories.knowledge import DocumentRepository
from app.storage.sqlite import connect
from app.synthesis.schemas import EvidenceRef


def _seed_document(
    conn,
    *,
    doc_id: str,
    source_path: Path,
    title: str,
    doc_hash: str,
    chunk_id: str,
    chunk_hash: str,
    text: str,
) -> None:
    section_id = f"{doc_id}:s1"
    with conn:
        conn.execute(
            """
            INSERT INTO documents(id, title, source_path, file_name, sha256, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_id, title, str(source_path), source_path.name, doc_hash, "2026-09-05T12:00:00+08:00"),
        )
        conn.execute(
            """
            INSERT INTO sections(
                id, document_id, level, heading, heading_path, ordinal,
                start_line, end_line, raw_text
            ) VALUES (?, ?, 1, ?, ?, 1, 1, 10, ?)
            """,
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


def _fixture(tmp_path: Path):
    data = tmp_path / "data"
    cognition_root = tmp_path / "cognition"
    report_root = tmp_path / "reports"
    (cognition_root / "03_问题池").mkdir(parents=True)
    (cognition_root / "04_判断台账").mkdir(parents=True)
    (cognition_root / "05_主题页").mkdir(parents=True)
    report_root.mkdir(parents=True)

    cfg = Config()
    cfg.paths.data_dir = str(data)
    cfg.cognition.root = str(cognition_root)

    report_conn = connect(data / "catalog.db")
    cognition_conn = connect(data / "catalog_cognition.db")
    init_schema(report_conn)
    init_schema(cognition_conn)

    _seed_document(
        cognition_conn,
        doc_id="cog:topic-ai-econ",
        source_path=cognition_root / "05_主题页" / "ai_economy.md",
        title="AI 与宏观经济",
        doc_hash="topic-v1",
        chunk_id="cog:topic-ai-econ:s1:c1",
        chunk_hash="topic-chunk-v1",
        text="研究 AI 投资、生产率、收入分配与需求约束之间的机制。",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:q-demand",
        source_path=cognition_root / "03_问题池" / "demand.md",
        title="AI 是否内生制造需求不足",
        doc_hash="question-v1",
        chunk_id="cog:q-demand:s1:c1",
        chunk_hash="question-chunk-v1",
        text="核心问题：生产率提升是否快于劳动收入和总需求增长？",
    )
    _seed_document(
        cognition_conn,
        doc_id="cog:j-capex",
        source_path=cognition_root / "04_判断台账" / "capex.md",
        title="AI CAPEX 当前判断",
        doc_hash="judgment-v1",
        chunk_id="cog:j-capex:s1:c1",
        chunk_hash="judgment-chunk-v1",
        text="当前判断仍需区分短期现金流改善与长期增长预期下降。",
    )
    _seed_document(
        report_conn,
        doc_id="M99",
        source_path=report_root / "M99_最终报告.md",
        title="AI 需求约束报告",
        doc_hash="report-v1",
        chunk_id="M99:s1:c1",
        chunk_hash="evidence-v1",
        text="企业采用 AI 后，生产率收益与工资增长之间可能存在分配时滞。",
    )

    service = TopicDossierService(cfg, report_conn, cognition_conn)
    ref = EvidenceRef(
        source_type="report",
        document_id="M99",
        section_id="M99:s1",
        chunk_id="M99:s1:c1",
        content_hash="evidence-v1",
        start_line=1,
        end_line=10,
    )
    body = DossierUpsert(
        title="AI 需求约束",
        direction="研究 AI 生产率、收入分配与总需求之间的反馈。",
        scope_include=["美国科技行业", "企业 AI 采用", "美国科技行业"],
        scope_exclude=["纯模型 benchmark"],
        topic_object_id="cog:topic-ai-econ",
        question_ids=["cog:q-demand", "cog:q-demand"],
        judgment_ids=["cog:j-capex"],
        evidence_refs=[ref, ref],
    )
    return cfg, report_conn, cognition_conn, service, body


def test_dossier_persists_planning_metadata_and_projects_authoritative_sources(tmp_path):
    cfg, report_conn, cognition_conn, service, body = _fixture(tmp_path)
    try:
        created = service.upsert("ai-demand", body)
        assert created["formal_topic_bound"] is True
        assert created["planning_only"] is False
        assert created["semantic_required"] is False
        assert created["needs_refresh"] is False
        assert created["dossier"]["scope_include"] == ["美国科技行业", "企业 AI 采用"]
        assert created["dossier"]["question_ids"] == ["cog:q-demand"]
        assert len(created["dossier"]["evidence_refs"]) == 1
        assert created["sources"]["topic"][0]["object_id"] == "cog:topic-ai-econ"
        assert "生产率提升" in created["sources"]["questions"][0]["excerpt"]
        assert "分配时滞" in created["sources"]["evidence"][0]["excerpt"]

        # New service instance simulates browser/app restart: planning state survives.
        reloaded = TopicDossierService(cfg, report_conn, cognition_conn).get("ai-demand")
        assert reloaded["dossier"]["title"] == "AI 需求约束"
        assert reloaded["needs_refresh"] is False
        assert service.list_dossiers()[0]["dossier_id"] == "ai-demand"
    finally:
        report_conn.close()
        cognition_conn.close()


def test_cognition_rename_preserves_stable_id_without_false_refresh(tmp_path):
    cfg, report_conn, cognition_conn, service, body = _fixture(tmp_path)
    try:
        service.upsert("ai-demand", body)
        renamed = Path(cfg.cognition.root) / "05_主题页" / "ai_macro_renamed.md"
        with cognition_conn:
            cognition_conn.execute(
                "UPDATE documents SET source_path = ?, file_name = ? WHERE id = ?",
                (str(renamed), renamed.name, "cog:topic-ai-econ"),
            )

        current = service.get("ai-demand")
        assert current["needs_refresh"] is False
        assert current["sources"]["topic"][0]["object_id"] == "cog:topic-ai-econ"
        assert current["sources"]["topic"][0]["source_bucket"] == "05_主题页"
    finally:
        report_conn.close()
        cognition_conn.close()


def test_changed_sources_are_distinct_from_missing_sources(tmp_path):
    _, report_conn, cognition_conn, service, body = _fixture(tmp_path)
    try:
        service.upsert("ai-demand", body)
        with cognition_conn:
            cognition_conn.execute(
                "UPDATE documents SET sha256 = ? WHERE id = ?",
                ("question-v2", "cog:q-demand"),
            )
        with report_conn:
            report_conn.execute(
                """
                UPDATE chunks
                SET content_hash = ?, plain_text = ?, raw_markdown = ?, embedding_text = ?, lexical_text = ?
                WHERE id = ?
                """,
                (
                    "evidence-v2",
                    "更新后的报告证据。",
                    "更新后的报告证据。",
                    "更新后的报告证据。",
                    "更新后的报告证据。",
                    "M99:s1:c1",
                ),
            )

        current = service.get("ai-demand")
        changes = {item["source"]: item for item in current["source_changes"]}
        assert current["needs_refresh"] is True
        assert changes["cognition:cog:q-demand"]["change"] == "changed"
        assert changes["evidence:M99:s1:c1"]["change"] == "changed"
        assert current["sources"]["evidence"][0]["content_hash"] == "evidence-v2"
        assert "更新后的报告证据" in current["sources"]["evidence"][0]["excerpt"]

        DocumentRepository(cognition_conn).delete("cog:j-capex")
        cognition_conn.commit()
        current = service.get("ai-demand")
        changes = {item["source"]: item for item in current["source_changes"]}
        assert changes["cognition:cog:j-capex"]["change"] == "missing"
        assert current["sources"]["judgments"][0]["missing"] is True
    finally:
        report_conn.close()
        cognition_conn.close()


def test_save_rejects_stale_reference_without_persisting_partial_dossier(tmp_path):
    _, report_conn, cognition_conn, service, body = _fixture(tmp_path)
    try:
        stale = body.model_copy(
            update={
                "evidence_refs": [
                    body.evidence_refs[0].model_copy(update={"content_hash": "wrong-hash"})
                ]
            }
        )
        with pytest.raises(ValueError, match="evidence chunk not found or stale"):
            service.upsert("bad-stale", stale)
        assert service.store.load_definition("bad-stale") is None
    finally:
        report_conn.close()
        cognition_conn.close()


def test_planning_only_dossier_requires_no_formal_topic_or_semantic_service(tmp_path):
    data = tmp_path / "data"
    cfg = Config()
    cfg.paths.data_dir = str(data)
    report_conn = connect(data / "catalog.db")
    init_schema(report_conn)
    try:
        service = TopicDossierService(cfg, report_conn, None)
        result = service.upsert(
            "draft-topic",
            DossierUpsert(
                title="尚未进入正式 Cognition 的研究方向",
                direction="先保存用户明确的研究范围，不伪造正式 Topic。",
            ),
        )
        assert result["planning_only"] is True
        assert result["formal_topic_bound"] is False
        assert result["semantic_required"] is False
        assert result["sources"]["topic"] == []
    finally:
        report_conn.close()


def test_http_api_uses_same_persistent_projection_contract(tmp_path):
    cfg, report_conn, cognition_conn, _, body = _fixture(tmp_path)
    app = FastAPI()
    app.state.cfg = cfg
    app.state.conn = report_conn
    app.state.cognition = {"enabled": True, "conn": cognition_conn}
    app.include_router(dossiers_api.router)
    try:
        with TestClient(app) as client:
            put = client.put("/api/research-os/dossiers/ai-demand", json=body.model_dump(mode="json"))
            assert put.status_code == 200, put.text
            get = client.get("/api/research-os/dossiers/ai-demand")
            assert get.status_code == 200, get.text
            assert get.json()["dossier"]["title"] == "AI 需求约束"
            listing = client.get("/api/research-os/dossiers")
            assert listing.status_code == 200
            assert listing.json()["dossiers"][0]["dossier_id"] == "ai-demand"

            bad = client.put("/api/research-os/dossiers/../escape", json=body.model_dump(mode="json"))
            assert bad.status_code in {404, 422}
    finally:
        report_conn.close()
        cognition_conn.close()
