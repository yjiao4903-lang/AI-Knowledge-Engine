"""I6 测试：Cognition 只读 ingest + 独立 collection 检索（集成）。

使用 tmp cognition 目录与独立测试 collection，不触碰真实认知数据；
验证：默认索引对象/排除对象、物理隔离、READ ONLY、增量一致性、检索命中。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cfg():
    cfg = load_config()
    cfg.cognition.chunks_collection = "kb_cognition_i6test"
    return cfg


@pytest.fixture(scope="module")
def dense(cfg):
    """共享 DenseRetriever（索引嵌入 + 检索同一实例，GPU 串行）。"""
    from app.retrieval.dense import DenseRetriever

    try:
        d = DenseRetriever(cfg)
    except Exception as exc:
        pytest.skip(f"嵌入模型不可用: {exc}")
    from app.cognition.pipeline import ensure_cognition_collection

    client = d.store.client
    for col in (cfg.cognition.chunks_collection,):
        try:
            client.delete_collection(col)
        except Exception:
            pass
    ensure_cognition_collection(cfg)
    yield d
    try:
        client.delete_collection(cfg.cognition.chunks_collection)
    except Exception:
        pass


JUDGMENT = """---
id: "j-001"
type: judgment
title: "capex 扩张不等于回报改善"
status: active
---

# capex 扩张不等于回报改善

## 核心判断

资本开支扩张周期中，capex 增长不等于股东回报改善，因为边际回报与资本效率
共同决定。标记词 ZETA42BETA 用于检索验证。

## 依据

历史产业周期对比显示，投资高峰往往对应回报拐点。
"""

QUESTION = """---
id: "q-001"
type: question
title: "变压器瓶颈是否构成前置约束"
status: open
---

# 变压器瓶颈是否构成前置约束？

## 关键未知

变压器交付周期是否构成 GPU 之外的第二重前置约束，标记词 QUARKX917 验证检索。
"""


class _DenseAdapter:
    """把 DenseRetriever 适配成 pipeline 需要的 embed_documents 接口。"""

    def __init__(self, dense):
        self.dense = dense
        self.device_kind = dense.device_kind

    def embed_documents(self, texts, batch_size=8):
        return self.dense.embedder.embed_documents(texts, batch_size=batch_size)


def _build_cognition_root(tmp_path: Path) -> Path:
    root = tmp_path / "cognition"
    (root / "03_问题池").mkdir(parents=True)
    (root / "04_判断台账").mkdir(parents=True)
    (root / "04_判断台账" / "capex 扩张不等于回报改善.md").write_text(JUDGMENT, encoding="utf-8")
    (root / "03_问题池" / "变压器瓶颈问题.md").write_text(QUESTION, encoding="utf-8")
    # 排除对象：候选/收件箱/归档/模板/系统
    (root / "01A_认知候选" / "pending.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "01A_认知候选" / "pending.md").write_text("候选提案：不应索引\n", encoding="utf-8")
    (root / "01_每日收件箱" / "2026-08-30.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "01_每日收件箱" / "2026-08-30.md").write_text("收件箱内容\n", encoding="utf-8")
    (root / "99_归档" / "old.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "99_归档" / "old.md").write_text("归档旧内容\n", encoding="utf-8")
    (root / "00_驾驶舱.md").write_text("驾驶舱\n", encoding="utf-8")
    return root


@pytest.fixture()
def env(tmp_path, cfg, dense):
    from app.cognition.pipeline import CognitionPipeline
    from app.cognition.scanner import scan as cog_scan
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    root = _build_cognition_root(tmp_path)
    cfg.cognition.root = str(root)
    cfg.cognition.catalog_path = str(tmp_path / "catalog_cognition.db")
    cfg.cognition.include_dirs = ["03_问题池", "04_判断台账"]
    conn = connect(cfg.cognition.catalog_path)
    init_schema(conn)
    pipeline = CognitionPipeline(cfg, conn, _DenseAdapter(dense))
    result = cog_scan(cfg, conn)
    stats = pipeline.apply_scan(result)
    assert not stats["errors"], stats
    return {"root": root, "conn": conn, "pipeline": pipeline, "cfg": cfg, "dense": dense}


def test_ingest_indexes_only_formal_objects(env):
    conn = env["conn"]
    docs = conn.execute("SELECT id FROM documents ORDER BY id").fetchall()
    ids = [d["id"] for d in docs]
    assert len(ids) == 2, ids
    assert any("capex 扩张不等于回报改善" in i for i in ids)
    assert any("变压器瓶颈问题" in i for i in ids)
    # 排除对象绝不入 catalog
    assert conn.execute("SELECT count(*) FROM chunks WHERE document_id LIKE '%pending%'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM documents WHERE source_path LIKE '%收件箱%'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM documents WHERE source_path LIKE '%归档%'").fetchone()[0] == 0
    # catalog/FTS 一致
    chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    fts = conn.execute("SELECT count(*) FROM chunks_fts_terms").fetchone()[0]
    assert chunks == fts


def test_isolated_collection_and_search(env):
    from app.retrieval.search_engine import SearchEngine

    engine = SearchEngine(
        env["cfg"], env["conn"], env["dense"],
        chunks_collection=env["cfg"].cognition.chunks_collection,
        section_boost_enabled=False)
    resp = engine.search("capex 扩张 不等于 回报改善", mode="hybrid", top_k=5, rerank=False)
    assert resp["results"]
    assert all(r["document_id"].startswith("cog:") for r in resp["results"])
    # 独立 collection 物理隔离：点数仅来自 cognition 文档
    info = env["dense"].store.collection_info(env["cfg"].cognition.chunks_collection)
    assert info["points_count"] >= 2
    # lexical 也来自 cognition catalog
    resp2 = engine.search("QUARKX917", mode="lexical", top_k=5)
    assert resp2["results"] and "变压器瓶颈问题" in resp2["results"][0]["document_id"]


def test_readonly_no_write_to_source(env):
    """KE 索引后 cognition 源文件 mtime 不变（READ ONLY 硬约束）。"""
    files = {
        p: (p.stat().st_mtime_ns, p.read_text(encoding="utf-8"))
        for p in sorted((Path(env["cfg"].cognition.root)).rglob("*.md"))
    }
    # 再次扫描（无变更）不应触碰任何源文件
    from app.cognition.scanner import scan as cog_scan

    result = cog_scan(env["cfg"], env["conn"])
    env["pipeline"].apply_scan(result)
    for p, (mt, text) in files.items():
        assert p.stat().st_mtime_ns == mt, f"源文件被修改: {p}"
        assert p.read_text(encoding="utf-8") == text


def test_modify_and_delete_incremental(env):
    conn = env["conn"]
    target = Path(env["cfg"].cognition.root) / "04_判断台账" / "capex 扩张不等于回报改善.md"
    target.write_text(JUDGMENT.replace("ZETA42BETA", "GAMMA88"), encoding="utf-8")
    (Path(env["cfg"].cognition.root) / "03_问题池" / "变压器瓶颈问题.md").unlink()

    from app.cognition.scanner import scan as cog_scan

    result = cog_scan(env["cfg"], env["conn"])
    stats = env["pipeline"].apply_scan(result)
    assert stats["indexed"] == 1 and stats["deleted"] == 1, stats
    # 新词可检索，旧词与删除文档消失
    assert conn.execute(
        "SELECT count(*) FROM chunks WHERE plain_text LIKE '%GAMMA88%'").fetchone()[0] >= 1
    assert conn.execute(
        "SELECT count(*) FROM chunks WHERE plain_text LIKE '%ZETA42BETA%'").fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM documents WHERE id LIKE '%变压器瓶颈问题%'").fetchone()[0] == 0
    assert conn.execute(
        "SELECT count(*) FROM document_tombstones WHERE document_id LIKE '%变压器瓶颈问题%'"
    ).fetchone()[0] == 1
