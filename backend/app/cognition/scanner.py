"""Cognition Manifest Scanner（I6，主计划 §48-50）。

只读扫描 cognition 根目录下 include_dirs 白名单子目录的正式认知 Markdown，
与 cognition catalog documents 表 manifest 对比，产出文件状态：
NEW / UNCHANGED / MODIFIED / DELETED / RENAMED / ERROR。

白名单之外（认知候选/每日收件箱/模板/系统/归档）一律不进入磁盘清单，
避免候选内容看起来像正式认知（主计划 §49）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.config import Config
from app.core.errors import SourceFileError
from app.indexing.scanner import FileState, ScanResult, sha256_file


def scan(cfg: Config, conn: sqlite3.Connection, *, hash_changed: bool = True) -> ScanResult:
    """全量 manifest 扫描（仅 include_dirs 白名单；语义与报告 scanner 一致）。"""
    result = ScanResult()
    cog = cfg.cognition
    root = Path(cog.root)
    if not root.exists():
        raise SourceFileError(f"cognition 根目录不存在: {root}")
    exts = set(cfg.knowledge_base.extensions)

    # 磁盘文件（只遍历白名单子目录；目录缺失视为空，不报错）
    disk: dict[str, tuple[int, int]] = {}
    for sub in cog.include_dirs:
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$"):
                try:
                    st = p.stat()
                    disk[str(p)] = (st.st_size, st.st_mtime_ns)
                except OSError as exc:
                    result.states.append(FileState(str(p), "ERROR", error=str(exc)))

    # manifest（cognition catalog documents 表）
    manifest = {
        r["source_path"]: {"id": r["id"], "size": r["file_size"] or 0,
                           "mtime": r["file_mtime_ns"] or 0, "sha256": r["sha256"]}
        for r in conn.execute(
            "SELECT id, source_path, file_size, file_mtime_ns, sha256 FROM documents").fetchall()
    }
    deleted_paths = [p for p in manifest if p not in disk]

    for path, (size, mtime) in disk.items():
        m = manifest.get(path)
        if m is None:
            state = FileState(path, "NEW", size, mtime)
        elif m["size"] == size and m["mtime"] == mtime:
            state = FileState(path, "UNCHANGED", size, mtime, document_id=m["id"])
        else:
            state = FileState(path, "MODIFIED", size, mtime, document_id=m["id"])
            if hash_changed:
                state.sha256 = sha256_file(Path(path))
                if state.sha256 == m["sha256"]:
                    state.status = "UNCHANGED"  # 内容未变（仅 mtime 变化）
        if state.status == "NEW" and hash_changed:
            new_hash = sha256_file(Path(path))
            state.sha256 = new_hash
            for dpath in deleted_paths:
                if manifest[dpath]["sha256"] == new_hash:
                    state.status = "RENAMED"
                    state.renamed_from = dpath
                    state.document_id = manifest[dpath]["id"]
                    break
        result.states.append(state)

    for dpath in deleted_paths:
        m = manifest[dpath]
        if not any(s.renamed_from == dpath for s in result.states):
            result.states.append(FileState(dpath, "DELETED", document_id=m["id"]))

    return result
