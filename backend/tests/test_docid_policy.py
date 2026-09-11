"""I0 docid_policy 单元测试：收录排除规则与 doc_id 命名策略（ADR-013）。"""

import sqlite3

from app.indexing.docid_policy import (
    build_index_plan,
    default_doc_id,
    exclusion_reason,
)
from app.indexing.scanner import FileState, ScanResult
from app.storage.migrations import init_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _scan(states):
    r = ScanResult()
    for path, status, sha in states:
        r.states.append(FileState(path, status, sha256=sha))
    return r


def _md_file(tmp_path, rel: str, code: str | None = None) -> str:
    """在 tmp_path 下建真实 md（含可选专题代号 blockquote），返回绝对路径字符串。"""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 标题"]
    if code:
        lines += ["", f"> **专题代号**：`{code}_test`"]
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


# ---- exclusion_reason ----

def test_excluded_dirs():
    assert exclusion_reason("D:/归档/研究输出/主题A/11_最终报告.md") == "EXCLUDED_DIR"
    assert exclusion_reason("D:/归档/_废弃_旧镜像/x/M04.md") == "EXCLUDED_DIR"
    assert exclusion_reason("D:/归档/版本存档/2026-08-16/M04.md") == "EXCLUDED_DIR"
    assert exclusion_reason("D:/归档/.agents/a.md") == "EXCLUDED_DIR"


def test_excluded_non_final():
    # v2：仅收录终版报告；思维增量/负知识/审核意见/草稿/分章报告均排除
    assert exclusion_reason("D:/归档/02/B/主题A/11b_思维增量.md") == "EXCLUDED_NON_FINAL"
    assert exclusion_reason("D:/归档/02/B/主题A/11c_负知识.md") == "EXCLUDED_NON_FINAL"
    assert exclusion_reason("D:/归档/02/B/主题A/审核意见_20260816.md") == "EXCLUDED_NON_FINAL"
    assert exclusion_reason("D:/归档/02/B/主题A/量化投资_第1章_草稿.md") == "EXCLUDED_NON_FINAL"
    assert exclusion_reason("D:/归档/02/F/朝贡/朝贡体系历史沿革报告.md") == "EXCLUDED_NON_FINAL"
    assert exclusion_reason("D:/归档/00_归档索引.md") in ("EXCLUDED_NON_FINAL", "EXCLUDED_PROCESS")
    assert exclusion_reason("D:/归档/02/B/主题A/11_最终报告.md") is None
    assert exclusion_reason("D:/归档/02/A/M01_专题/M01_专题_最终报告.md") is None


def test_excluded_process_stems():
    assert exclusion_reason("D:/归档/旗舰/M04 专题/03_报告草稿_v1.md") == "EXCLUDED_PROCESS"
    assert exclusion_reason("D:/归档/旗舰/M04 专题/00c_思维涌现日志.md") == "EXCLUDED_PROCESS"
    assert exclusion_reason("D:/归档/旗舰/M04 专题/10_验收记录.md") == "EXCLUDED_PROCESS"
    assert exclusion_reason("D:/归档/02/00_旗舰专题开题/M04_开题报告.md") == "EXCLUDED_PROCESS"
    # 11/11b/11c 与 M-code 文件不排除
    assert exclusion_reason("D:/归档/02/B/主题A/11_最终报告.md") is None
    assert exclusion_reason("D:/归档/02/A/M01_专题/M01_专题_最终报告.md") is None


# ---- default_doc_id ----

def test_default_doc_id_rules():
    # M-code 思维增量/负知识手册 -> code__后缀
    assert default_doc_id("D:/x/M01_专题/M01_专题_思维增量.md", "M01") == "M01__思维增量"
    assert default_doc_id("D:/x/M01_专题/M01_专题_负知识手册.md", "M01") == "M01__负知识"
    # 旗舰最终报告 -> code
    assert default_doc_id("D:/x/M04_专题/M04_专题_最终报告.md", "M04") == "M04"
    # 无 code 的成品层：11_最终报告 -> 主题目录名；11b/11c -> 主题__后缀
    assert default_doc_id("D:/归档/02/B/液冷研究/11_最终报告.md", None) == "液冷研究"
    assert default_doc_id("D:/归档/02/B/液冷研究/11b_思维增量.md", None) == "液冷研究__思维增量"
    assert default_doc_id("D:/归档/02/B/液冷研究/11c_负知识.md", None) == "液冷研究__负知识"
    # 其他 -> stem
    assert default_doc_id("D:/归档/02/B/X_专项审阅报告.md", None) == "X_专项审阅报告"


# ---- build_index_plan ----

def test_plan_dedupes_identical_copies(tmp_path):
    conn = _conn()
    p1 = _md_file(tmp_path, "02_主题研究报告/A/主题A/11_最终报告.md")
    p2 = _md_file(tmp_path, "旗舰战略专题报告_完整备份_M01-M24/M04_专题/M04_专题_最终报告.md",
                  code="M04")
    plan = build_index_plan(_scan([(p1, "NEW", "aaa"), (p2, "NEW", "bbb")]), conn)
    assert plan.assignments[p1] == "主题A"
    assert plan.assignments[p2] == "M04"


def test_plan_disambiguates_same_id_different_content(tmp_path):
    conn = _conn()
    # 两个同名 stem（11_最终报告）位于不同主题目录 -> 同 default_id，内容不同
    p1 = _md_file(tmp_path, "02_主题研究报告/B/主题甲/11_最终报告.md")
    p2 = _md_file(tmp_path, "02_主题研究报告/C/主题甲/11_最终报告.md")
    plan = build_index_plan(_scan([(p1, "NEW", "aaa"), (p2, "NEW", "bbb")]), conn)
    ids = sorted(plan.assignments.values())
    assert len(ids) == 2
    # canonical（路径较短者）保留原名，其余 sha8 消歧
    assert plan.assignments[p1] == "主题甲"
    assert plan.assignments[p2].startswith("主题甲__")
    assert plan.disambiguated == 1


def test_plan_canonical_priority_prefers_02(tmp_path):
    conn = _conn()
    p_flag = _md_file(tmp_path, "旗舰战略专题报告_完整备份_M01-M24/M04_专题/M04_专题_最终报告.md",
                      code="M04")
    p_02 = _md_file(tmp_path, "02_主题研究报告/A/M04_专题/M04_专题_最终报告.md", code="M04")
    plan = build_index_plan(_scan([(p_flag, "NEW", "same"), (p_02, "NEW", "same")]), conn)
    # 同内容同 id：保留 02 成品层，旗舰备份记为 EXCLUDED_DUPLICATE
    assert plan.assignments == {p_02: "M04"}
    dup = [e for e in plan.exclusions if e["reason"] == "EXCLUDED_DUPLICATE"]
    assert len(dup) == 1 and p_flag in dup[0]["path"]


def test_plan_dedupes_against_existing_catalog(tmp_path):
    conn = _conn()
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M04', 'M04', 'old.md', 'same', 'D:/old.md')")
    p = _md_file(tmp_path, "02_主题研究报告/A/M04_专题/M04_专题_最终报告.md", code="M04")
    plan = build_index_plan(_scan([(p, "NEW", "same")]), conn)
    assert plan.assignments == {}
    assert plan.exclusions[0]["reason"] == "EXCLUDED_DUPLICATE"


# ---- P8-ENG-01：跨批次身份冲突（catalog 既有文档 vs 新候选） ----

def test_plan_disambiguates_against_existing_catalog_different_content(tmp_path):
    """库内已有同 id 不同内容文档时，新候选必须 sha8 消歧，禁止占用裸 id。

    否则 index_file 会 DELETE+替换既有文档（P8 中 M09 45↔77 chunk 抖动）。
    """
    conn = _conn()
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M09', 'M09 Transformer', 'old.md', 'oldsha', 'D:/old/M09_old.md')")
    p = _md_file(tmp_path, "02_主题研究报告/M09_男女身体构造差异/M09_男女身体构造差异_最终报告.md",
                 code="M09")
    plan = build_index_plan(_scan([(p, "NEW", "newsha1234")]), conn)
    assert plan.assignments == {p: "M09__newsha12"}
    assert "M09" not in plan.assignments.values()
    assert plan.disambiguated == 1


def test_plan_modified_same_source_keeps_id(tmp_path):
    """MODIFIED 的是库内文档自身路径 -> 沿用原 id，不做消歧。"""
    conn = _conn()
    p = _md_file(tmp_path, "02_主题研究报告/M04_专题/M04_专题_最终报告.md", code="M04")
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M04', 'M04', 'x.md', 'oldsha', ?)", (p,))
    plan = build_index_plan(_scan([(p, "MODIFIED", "newsha")]), conn)
    assert plan.assignments == {p: "M04"}
    assert plan.disambiguated == 0


def test_plan_excludes_all_copies_when_canonical_matches_existing(tmp_path):
    """canonical 与库内同 sha 时，整组拷贝都必须排除，不得留下未分配候选。

    否则 apply_scan 会对未分配路径回退到默认 doc_id 再次写入（manifest 路径抖动）。
    """
    conn = _conn()
    keep = _md_file(tmp_path, "02_主题研究报告/A/M04_专题/M04_专题_最终报告.md", code="M04")
    other = _md_file(
        tmp_path, "旗舰战略专题报告_完整备份_M01-M24/M04_专题/M04_专题_最终报告.md", code="M04")
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M04', 'M04', 'old.md', 'same', 'D:/old/M04.md')")
    plan = build_index_plan(_scan([(keep, "NEW", "same"), (other, "NEW", "same")]), conn)
    assert plan.assignments == {}
    assert keep in plan.excluded_paths and other in plan.excluded_paths
    reasons = {e["path"]: e["reason"] for e in plan.exclusions}
    assert reasons[keep] == "EXCLUDED_DUPLICATE"
    assert reasons[other] == "EXCLUDED_DUPLICATE"


def test_plan_accounts_for_every_included_candidate(tmp_path):
    """每个通过排除规则的候选都必须落到 assignments 或 excluded_paths。"""
    conn = _conn()
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M09', 'M09', 'old.md', 'oldsha', 'D:/old/M09.md')")
    p_new = _md_file(tmp_path, "02_主题研究报告/M09_A/M09_A_最终报告.md", code="M09")
    p_upd = _md_file(tmp_path, "02_主题研究报告/M04_B/M04_B_最终报告.md", code="M04")
    conn.execute(
        "INSERT INTO documents (id, title, file_name, sha256, source_path) "
        "VALUES ('M04', 'M04', 'm04.md', 'm04old', ?)", (p_upd,))
    plan = build_index_plan(
        _scan([(p_new, "NEW", "newsha"), (p_upd, "MODIFIED", "m04new")]), conn)
    for p in (p_new, p_upd):
        assert p in plan.assignments or p in plan.excluded_paths


def test_plan_excludes_dirs_and_process(tmp_path):
    conn = _conn()
    p_draft = _md_file(tmp_path, "02_主题研究报告/A/M04_专题/03_报告草稿_v1.md", code="M04")
    p_work = _md_file(tmp_path, "研究输出/主题A/11_最终报告.md")
    plan = build_index_plan(_scan([(p_draft, "NEW", "x"), (p_work, "NEW", "y")]), conn)
    assert plan.assignments == {}
    reasons = {e["path"]: e["reason"] for e in plan.exclusions}
    assert reasons[p_draft] == "EXCLUDED_PROCESS"
    assert reasons[p_work] == "EXCLUDED_DIR"
    assert p_draft in plan.excluded_paths and p_work in plan.excluded_paths
