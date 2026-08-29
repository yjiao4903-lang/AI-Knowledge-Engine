"""I6 测试：Cognition Scanner（include/exclude 白名单 + manifest 状态判定）。"""

from __future__ import annotations

from pathlib import Path

from app.cognition.pipeline import cognition_doc_id
from app.cognition.scanner import scan
from app.core.config import Config
from app.storage.migrations import init_schema
from app.storage.sqlite import connect


def _cognition_env(tmp_path: Path) -> tuple[Config, object]:
    root = tmp_path / "cognition"
    inc = root / "03_问题池"
    (inc / "sub").mkdir(parents=True)
    (inc / "变压器瓶颈.md").write_text("# 问题\n\n变压器瓶颈是否构成约束？\n", encoding="utf-8")
    (inc / "sub" / "第二个问题.md").write_text("# 问题\n\n内容 B。\n", encoding="utf-8")
    # 白名单之外：不应进入磁盘清单
    (root / "01_每日收件箱").mkdir(parents=True)
    (root / "01_每日收件箱" / "inbox.md").write_text("收件箱内容\n", encoding="utf-8")
    (root / "01A_认知候选" / "cand.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "01A_认知候选" / "cand.md").write_text("候选内容\n", encoding="utf-8")
    (root / "99_归档" / "old.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "99_归档" / "old.md").write_text("归档内容\n", encoding="utf-8")
    (root / "00_驾驶舱.md").write_text("驾驶舱\n", encoding="utf-8")  # 根目录文件

    cfg = Config()
    cfg.cognition.root = str(root)
    cfg.cognition.include_dirs = ["03_问题池"]
    cfg.cognition.catalog_path = str(tmp_path / "catalog_cognition.db")
    conn = connect(cfg.cognition.catalog_path)
    init_schema(conn)
    return cfg, conn


def test_scan_only_includes_whitelist(tmp_path: Path):
    cfg, conn = _cognition_env(tmp_path)
    try:
        result = scan(cfg, conn)
        states = {s.status: s for s in result.states}
        assert states["NEW"].status == "NEW"
        assert len([s for s in result.states if s.status == "NEW"]) == 2
        # 白名单之外的任何路径不得出现在结果中
        paths = [s.path for s in result.states]
        assert not any(("收件箱" in p or "候选" in p or "归档" in p or "驾驶舱" in p) for p in paths)
    finally:
        conn.close()


def test_scan_detect_modified_deleted(tmp_path: Path):
    cfg, conn = _cognition_env(tmp_path)
    try:
        # 模拟已索引状态：首次 scan 的 NEW 文件写入 manifest
        for s in scan(cfg, conn).states:
            if s.status == "NEW":
                conn.execute(
                    "INSERT INTO documents (id, title, source_path, file_name, file_size, "
                    "file_mtime_ns, sha256) VALUES (?,?,?,?,?,?,?)",
                    (f"dummy:{s.path}", "t", s.path, Path(s.path).name,
                     s.size, s.mtime_ns, s.sha256 or ""))
        conn.commit()

        doc = Path(cfg.cognition.root) / "03_问题池" / "变压器瓶颈.md"
        doc.write_text("# 问题\n\n变压器瓶颈是否构成约束？【修改版】\n", encoding="utf-8")
        r2 = scan(cfg, conn)
        mod = [s for s in r2.states if s.status == "MODIFIED"]
        assert len(mod) == 1 and "变压器瓶颈" in mod[0].path
        (Path(cfg.cognition.root) / "03_问题池" / "sub" / "第二个问题.md").unlink()
        r3 = scan(cfg, conn)
        dele = [s for s in r3.states if s.status == "DELETED"]
        assert len(dele) == 1 and "第二个问题" in dele[0].path
    finally:
        conn.close()


def test_cognition_doc_id(tmp_path: Path):
    cfg, conn = _cognition_env(tmp_path)
    try:
        p = Path(cfg.cognition.root) / "03_问题池" / "sub" / "第二个问题.md"
        assert cognition_doc_id(cfg, p) == "cog:03_问题池/sub/第二个问题"
    finally:
        conn.close()


def test_scan_missing_root_raises(tmp_path: Path):
    cfg = Config()
    cfg.cognition.root = str(tmp_path / "nope")
    conn = connect(tmp_path / "c.db")
    init_schema(conn)
    try:
        try:
            scan(cfg, conn)
            raise AssertionError("应抛 SourceFileError")
        except Exception as exc:
            assert "cognition 根目录不存在" in str(exc)
    finally:
        conn.close()
