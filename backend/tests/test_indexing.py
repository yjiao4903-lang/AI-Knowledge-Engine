"""M8 测试：Incremental Index（Addendum §44-46）。

使用 tmp 知识库目录与独立测试 collection，不触碰真实知识源。
"""

import shutil
from pathlib import Path

import pytest

from app.core.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cfg():
    cfg = load_config()
    cfg.qdrant.chunks_collection = "kb_chunks_m8test"
    cfg.qdrant.sections_collection = "kb_sections_m8test"
    return cfg


@pytest.fixture(scope="module")
def worker(cfg):
    from app.inference.manager import InferenceManager

    try:
        mgr = InferenceManager(cfg)
    except Exception as exc:
        pytest.skip(f"GPU worker 不可用: {exc}")
    # 确保测试 collection 存在
    from app.storage.qdrant import QdrantStore

    store = QdrantStore(cfg.qdrant)
    for col in (cfg.qdrant.chunks_collection, cfg.qdrant.sections_collection):
        try:
            store.client.delete_collection(col)
        except Exception:
            pass
    store.ensure_collections()
    yield mgr
    mgr.shutdown()


@pytest.fixture()
def env(tmp_path, cfg, worker, monkeypatch):
    """tmp 知识库 + tmp catalog + pipeline。roots 必须指向 tmp，禁止扫真实知识源。"""
    from app.indexing.pipeline import EmbedderAdapter, IndexPipeline
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    kb = tmp_path / "kb"
    kb.mkdir()
    cfg.knowledge_base.roots = [str(kb)]
    shutil.copy(FIXTURES / "M14_sample.md", kb / "M14_测试_最终报告.md")  # 命名须满足收录策略（ADR-013 v2）
    conn = connect(tmp_path / "catalog.db")
    init_schema(conn)
    pipeline = IndexPipeline(cfg, conn, EmbedderAdapter(cfg, worker))
    return {"kb": kb, "conn": conn, "pipeline": pipeline, "cfg": cfg}


MINI_DOC = """# 测试文档 T99

> **专题代号**：`T99_Test`  
> **完成日期**：2026-08-29  

## 1.1 独有内容段

本段包含独一无二的测试标记词 QUARKX917 用于检索验证。[L1]
"""


def _scan(env):
    from app.indexing.scanner import scan

    return scan(env["cfg"], env["conn"])


def _fts_count(env, term):
    return env["conn"].execute(
        "SELECT count(*) FROM chunks_fts_terms WHERE chunks_fts_terms MATCH ?",
        (f'"{term}"',)).fetchone()[0]


def test_add_new_file(env):
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    stats = env["pipeline"].apply_scan(_scan(env))
    assert stats["indexed"] == 2 and not stats["errors"]  # M14 fixture + T99
    assert any(d["document_id"] == "T99" for d in stats.get("details", []))
    assert _fts_count(env, "QUARKX917") >= 1
    # Qdrant 点数一致
    from app.indexing.reconcile import check_consistency

    report = check_consistency(env["cfg"], env["conn"])
    assert report["consistent"], report


def test_modify_file(env):
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))

    modified = MINI_DOC.replace("独有内容段", "被改写的第二版内容").replace(
        "QUARKX917", "ZETA42BETA")
    (env["kb"] / "T99_mini_最终报告.md").write_text(modified, encoding="utf-8")
    stats = env["pipeline"].apply_scan(_scan(env))
    assert stats["indexed"] == 1 and not stats["errors"]

    # 新内容可检索，旧内容消失，无孤儿
    assert _fts_count(env, "ZETA42BETA") >= 1
    assert _fts_count(env, "QUARKX917") == 0
    from app.indexing.reconcile import check_consistency

    assert check_consistency(env["cfg"], env["conn"])["consistent"]


def test_staging_failure_preserves_old_version(env, monkeypatch):
    """MODIFIED 的 staging 失败 => 旧版本继续可搜索（Addendum §35/52）。"""
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))

    from app.indexing import pipeline as pipeline_mod

    def boom(self, doc, document_id=None):
        raise RuntimeError("模拟解析/分块崩溃")

    monkeypatch.setattr(pipeline_mod.SemanticChunker, "chunk_document", boom)
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC + "\n损坏的新版本", encoding="utf-8")
    stats = env["pipeline"].apply_scan(_scan(env))
    monkeypatch.undo()

    assert stats["errors"], "staging 失败应记录错误"
    # 旧版本完好：第一版内容仍在，损坏的新版本未入库
    assert _fts_count(env, "QUARKX917") >= 1
    assert _fts_count(env, "ZETA42BETA") == 0
    from app.indexing.reconcile import check_consistency

    assert check_consistency(env["cfg"], env["conn"])["consistent"]


def test_rename_file_no_reembed(env, worker, monkeypatch):
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))

    from app.indexing.pipeline import EmbedderAdapter

    calls = {"n": 0}
    orig = EmbedderAdapter.embed_documents

    def counting(self, texts, batch_size=8):
        calls["n"] += 1
        return orig(self, texts, batch_size)

    monkeypatch.setattr(EmbedderAdapter, "embed_documents", counting)

    (env["kb"] / "T99_mini_最终报告_renamed.md").write_text(MINI_DOC, encoding="utf-8")
    (env["kb"] / "T99_mini_最终报告.md").unlink()
    stats = env["pipeline"].apply_scan(_scan(env))

    monkeypatch.undo()
    assert stats["renamed"] == 1 and stats["indexed"] == 0, stats
    assert calls["n"] == 0, "RENAMED 不应重新嵌入"
    row = env["conn"].execute(
        "SELECT source_path FROM documents WHERE id='T99'").fetchone()
    assert row["source_path"].endswith("T99_mini_最终报告_renamed.md")


def test_delete_file_tombstone(env):
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))
    (env["kb"] / "T99_mini_最终报告.md").unlink()
    stats = env["pipeline"].apply_scan(_scan(env))
    assert stats["deleted"] == 1

    assert _fts_count(env, "QUARKX917") == 0
    assert env["conn"].execute(
        "SELECT count(*) FROM chunks WHERE document_id='T99'").fetchone()[0] == 0
    assert env["conn"].execute(
        "SELECT count(*) FROM document_tombstones WHERE document_id='T99'").fetchone()[0] == 1
    from app.indexing.reconcile import check_consistency

    assert check_consistency(env["cfg"], env["conn"])["consistent"]


def test_repair_restores_missing_points(env):
    """Qdrant 点被删 -> check 不一致 -> repair 恢复（Addendum §42-43）。"""
    from qdrant_client import models as qm

    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))
    col = env["cfg"].qdrant.chunks_collection
    client = env["pipeline"].qdrant_client()

    # 模拟事故：删掉该文档全部 Qdrant 点
    flt = qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value="T99"))])
    client.delete(collection_name=col, points_selector=qm.FilterSelector(filter=flt))

    from app.indexing.reconcile import check_consistency, repair

    report = check_consistency(env["cfg"], env["conn"])
    bad = [d for d in report["documents"] if not d["ok"]]
    assert bad, "应检测到不一致"

    stats = repair(env["cfg"], env["conn"], embedder=env["pipeline"].embedder)
    assert stats["reindexed_documents"] >= 1
    assert check_consistency(env["cfg"], env["conn"])["consistent"]


def test_fast_path_unchanged(env):
    """size+mtime 未变 -> UNCHANGED（跳过 sha256 重索引）。"""
    (env["kb"] / "T99_mini_最终报告.md").write_text(MINI_DOC, encoding="utf-8")
    env["pipeline"].apply_scan(_scan(env))
    result = _scan(env)
    states = [s for s in result.states if s.path.endswith("T99_mini_最终报告.md")]
    assert states and states[0].status == "UNCHANGED"
    stats = env["pipeline"].apply_scan(result)
    assert stats["indexed"] == 0 and stats["unchanged"] >= 1
