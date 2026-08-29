"""SQLite 连接管理（M1-04）。

- WAL / foreign_keys / synchronous 启动 PRAGMA（spec §26）；
- Search 只读、Indexing 写入均经由此模块，事务在调用侧用 with conn: 控制。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.errors import SqliteError


def connect(path: str | Path, *, read_only: bool = False,
            check_same_thread: bool = True) -> sqlite3.Connection:
    p = Path(path)
    if not read_only:
        p.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(p, check_same_thread=check_same_thread)
        conn.row_factory = sqlite3.Row
        if read_only:
            conn.execute("PRAGMA query_only=ON")
        else:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as exc:
        raise SqliteError(f"SQLite 连接失败: {p}", detail={"error": str(exc)}) from exc
