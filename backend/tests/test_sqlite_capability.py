"""SQLite FTS5 能力检查（M0-08）。

验证 catalog 计划使用的能力：FTS5、unicode61、trigram tokenizer、bm25。
"""

import sqlite3

import pytest


def test_fts5_module_available():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(a)")


def test_fts5_trigram_tokenizer():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize='trigram')")
    conn.execute("INSERT INTO t VALUES ('TSMC N3E 与 CoWoS-L 在 HBM4 时代的价值量提升')")
    # trigram 精确子串命中；含 - / : 的标识符必须用双引号包裹（FTS5 语法），M4 查询解析时处理
    rows = conn.execute('SELECT * FROM t WHERE t MATCH \'"CoWoS-L"\'').fetchall()
    assert len(rows) == 1
    rows = conn.execute('SELECT * FROM t WHERE t MATCH \'"EXE:5000"\'').fetchall()
    assert rows == []  # 不存在时不误命中


def test_fts5_unicode61_and_bm25():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize='unicode61')")
    conn.execute("INSERT INTO t VALUES ('HBM4 接口位宽提升 2048-bit')")
    conn.execute("INSERT INTO t VALUES ('CoWoS 产能监测指标')")
    rows = conn.execute(
        "SELECT a FROM t WHERE t MATCH 'HBM4' ORDER BY bm25(t)"
    ).fetchall()
    assert len(rows) == 1


def test_fts5_trigram_short_query_no_hit():
    # trigram 要求 >=3 字符；短查询不崩溃即可
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize='trigram')")
    conn.execute("INSERT INTO t VALUES ('N3E 制程')")
    rows = conn.execute("SELECT * FROM t WHERE t MATCH 'N3E'").fetchall()
    assert len(rows) == 1
