"""Synthesis 测试 fixtures（conftest 才能被 pytest 自动注册）。"""

from __future__ import annotations

import pytest


@pytest.fixture()
def syn_conn(tmp_path):
    from app.core.config import Config
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    conn = connect(tmp_path / "syn_catalog.db", check_same_thread=False)
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def syn_cfg(tmp_path):
    from app.core.config import Config

    cfg = Config()
    cfg.paths.data_dir = str(tmp_path / "data")
    return cfg


@pytest.fixture()
def seeded(syn_conn, syn_cfg):
    """种入一篇文档 + 两个 chunk，返回 {conn, cfg, resolver, chunk_ids, hashes}。"""
    from app.synthesis.grounding import EvidenceResolver

    from tests.synthesis.helpers import seed_chunk, seed_doc

    doc_id = seed_doc(syn_conn, "M04")
    text_a = "HBM4 的接口位宽相比 HBM3E 显著提高。" * 4
    text_b = "更宽接口进一步提高了先进封装工艺的系统价值量。" * 4
    ha = seed_chunk(syn_conn, "M04:ch1:0001", text_a, doc_id=doc_id)
    hb = seed_chunk(syn_conn, "M04:ch1:0002", text_b, doc_id=doc_id)
    resolver = EvidenceResolver(syn_cfg, syn_conn, None)
    return {"conn": syn_conn, "cfg": syn_cfg, "resolver": resolver,
            "chunk_ids": ["M04:ch1:0001", "M04:ch1:0002"], "hashes": [ha, hb]}