"""M7 测试：Worker 进程隔离、restart/timeout/fallback、Reranker 链路（Addendum §28）。

GPU worker 相关用例共享 module 级 manager fixture（加载一次）。
"""

import pytest

from app.core.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def manager(cfg):
    from app.inference.manager import InferenceManager

    try:
        mgr = InferenceManager(cfg)
    except Exception as exc:
        pytest.skip(f"GPU worker 不可用: {exc}")
    yield mgr
    mgr.shutdown()


def test_worker_start(manager):
    assert manager.is_alive()
    assert manager.device is not None
    assert manager.total_restarts == 0


def test_worker_health(manager):
    h = manager.health()
    assert h["alive"] and h["detail"]["pid"] > 0
    assert h["detail"]["device_kind"] in ("rocm", "cuda", "cpu")


def test_worker_embed(manager):
    vec = manager.call("embed_query", {"query": "先进封装产能"})
    assert len(vec) == 1024


def test_worker_restart(manager):
    """crash -> watchdog 检测 -> restart -> 恢复推理（Addendum §15）。"""
    from app.core.errors import GpuError

    with pytest.raises(GpuError):
        manager.call("test_crash", timeout=30)
    import time

    time.sleep(1)
    assert manager.is_alive()  # watchdog 已重启
    assert manager.total_restarts >= 1
    vec = manager.call("embed_query", {"query": "restart 后推理"})
    assert len(vec) == 1024


def test_worker_timeout(manager):
    from app.core.errors import GpuError

    with pytest.raises(GpuError):
        manager.call("test_sleep", {"seconds": 8}, timeout=3)


def test_device_explicit(cfg):
    """force_device 优先级：显式指定/无效值回退（不经模型加载）。"""
    from app.inference.device import get_inference_device

    dev, reason = get_inference_device(force_device="cuda:9")
    assert dev == "cpu" and "无效" in reason
    dev, reason = get_inference_device(force_device="cpu")
    assert dev == "cpu"
    # 无 force 时按 preferred_gpu_name 匹配
    dev, reason = get_inference_device()
    assert dev.startswith("cuda:")
    assert "RX 7900 XTX" in reason


def test_rerank_order(manager):
    """相关文档得分必须高于无关文档。"""
    scores = manager.call("rerank", {
        "query": "HBM4 的接口位宽是多少？",
        "documents": [
            "HBM4 将接口位宽从 1024-bit 提升至 2048-bit，同时保持引脚速度。",
            "全球利率周期由基钦库存周期与朱格拉资本周期嵌套驱动。",
        ],
        "batch_size": 1,
    })
    assert scores[0] > scores[1]
    assert all(s == s and 0.0 <= s <= 1.0 for s in scores)


def test_rerank_empty(manager):
    scores = manager.call("rerank", {"query": "任意", "documents": [], "batch_size": 1})
    assert scores == []


def test_rerank_long_input():
    """长文档截断：保留 heading + 查询词邻域 + 开头（Addendum §9）。"""
    from app.retrieval.rerank import build_rerank_document

    long_text = "开头内容。" + "填充" * 1200 + "中间出现 HBM4 关键词。" + "尾部" * 500
    doc = build_rerank_document(
        "HBM4 相关问题", title="T", heading_path="S > S2", content_type="prose",
        evidence_level=1, plain_text=long_text,
    )
    assert len(doc) < 1600  # 有界
    assert doc.startswith("Title: T")
    assert "HBM4 关键词" in doc  # 查询词邻域被保留


def test_rerank_debug_trace(engine_with_reranker):
    resp = engine_with_reranker.search(
        "HBM4 的接口位宽是多少？", mode="hybrid", top_k=5, rerank=True, debug=True)
    trace = resp["debug"]["rerank"]
    assert trace and "reranker_score" in trace[0] and "pre_rerank_rank" in trace[0]
    top = resp["results"][0]["scores"]
    assert top["reranker"] is not None and top["pre_rerank_rank"] is not None
    # rerank 后分数降序
    scores = [t["reranker_score"] for t in trace]
    assert scores == sorted(scores, reverse=True)


def test_engine_no_reranker_regression(engine_with_reranker):
    """rerank=False 时输出不含 reranker 分数，行为与 M6 一致。"""
    resp = engine_with_reranker.search("先进封装", mode="hybrid", top_k=3, rerank=False)
    assert resp["results"]
    assert all(r["scores"]["reranker"] is None for r in resp["results"])
    assert resp["timing_ms"].get("rerank_ms", 0) == 0.0


@pytest.fixture(scope="module")
def engine_with_reranker(manager):
    """复用已索引的 Qdrant 集合 + worker。"""
    import tempfile
    from pathlib import Path

    from app.lexical.corpus import build_corpus_db
    from app.retrieval.dense import DenseRetriever
    from app.retrieval.rerank import RerankerService
    from app.retrieval.search_engine import SearchEngine

    cfg = load_config()
    dense = DenseRetriever(cfg)
    try:
        points = dense.store.collection_info(cfg.qdrant.chunks_collection)["points_count"]
    except Exception:
        points = 0
    if not points:
        pytest.skip("Qdrant 无索引（先运行 backend/scripts/m5_index.py）")
    tmp = Path(tempfile.mkdtemp())
    conn, _ = build_corpus_db(tmp / "corpus.db")
    return SearchEngine(cfg, conn, dense, RerankerService(cfg, manager))


def test_worker_cpu_fallback(cfg):
    """CPU fallback：worker 可在 CPU 设备上加载并推理（Addendum §17）。"""
    from app.inference.manager import InferenceManager

    mgr = InferenceManager(cfg, device_override="cpu")
    try:
        assert mgr.device == "cpu"
        vec = mgr.call("embed_query", {"query": "CPU fallback 验证"}, timeout=180)
        assert len(vec) == 1024
    finally:
        mgr.shutdown()
