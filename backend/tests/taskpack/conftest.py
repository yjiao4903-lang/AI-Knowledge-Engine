"""TaskPack 测试 fixtures（conftest 才能被 pytest 自动注册）。

fixtures 不跨测试目录共享，syn_conn/syn_cfg 在此独立定义（逻辑与
tests/synthesis/conftest.py 一致），种子数据复用 tests.synthesis.helpers。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def tk_root(tmp_path):
    return tmp_path / "taskpacks"


@pytest.fixture()
def tk_conn(tmp_path):
    from app.storage.migrations import init_schema
    from app.storage.sqlite import connect

    conn = connect(tmp_path / "tk_catalog.db", check_same_thread=False)
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def tk_cfg(tmp_path, tk_root):
    from app.core.config import Config

    cfg = Config()
    cfg.paths.data_dir = str(tmp_path / "data")
    cfg.taskpack.root_dir = str(tk_root)
    return cfg


@pytest.fixture()
def tk_env(tk_conn, tk_cfg, tk_root):
    """种入 M04 两个 chunk，返回 {root, builder, refs, hashes, cfg, conn}。"""
    from app.synthesis.schemas import EvidenceRef
    from app.taskpack.builder import TaskPackBuilder
    from tests.synthesis.helpers import seed_chunk, seed_doc

    doc_id = seed_doc(tk_conn, "M04")
    ha = seed_chunk(
        tk_conn, "M04:ch1:0001", "HBM4 的接口位宽相比 HBM3E 显著提高。" * 4, doc_id=doc_id
    )
    hb = seed_chunk(
        tk_conn, "M04:ch1:0002", "更宽接口进一步提高了先进封装工艺的系统价值量。" * 4, doc_id=doc_id
    )
    builder = TaskPackBuilder(tk_cfg, tk_conn, None)
    refs = [
        EvidenceRef(source_type="report", document_id="M04",
                    chunk_id="M04:ch1:0001", content_hash=ha),
        EvidenceRef(source_type="report", document_id="M04",
                    chunk_id="M04:ch1:0002", content_hash=hb),
    ]
    return {"root": tk_root, "builder": builder, "refs": refs,
            "hashes": [ha, hb], "cfg": tk_cfg, "conn": tk_conn}
