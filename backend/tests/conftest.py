"""M1 测试 fixtures。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Config  # noqa: E402
from app.storage.migrations import init_schema  # noqa: E402
from app.storage.sqlite import connect  # noqa: E402


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Config:
    data_dir = tmp_path / "data"
    cfg = Config()
    cfg.paths.data_dir = str(data_dir)
    cfg.paths.log_dir = str(tmp_path / "logs")
    cfg.sqlite.path = str(data_dir / "catalog.db")
    return cfg


@pytest.fixture()
def db(tmp_path: Path):
    conn = connect(tmp_path / "test_catalog.db")
    init_schema(conn)
    yield conn
    conn.close()
