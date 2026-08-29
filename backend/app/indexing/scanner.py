"""Manifest Scanner（M8，Addendum §31-33）。

扫描知识库根目录，与 documents 表 manifest 对比，产出文件状态：
NEW / UNCHANGED / MODIFIED / DELETED / RENAMED / ERROR。
Fast Path：size + mtime_ns 均未变 -> 跳过 SHA256。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Config
from app.core.errors import SourceFileError


@dataclass
class FileState:
    path: str
    status: str  # NEW | UNCHANGED | MODIFIED | DELETED | RENAMED | ERROR
    size: int = 0
    mtime_ns: int = 0
    sha256: str | None = None  # 仅 MODIFIED/NEW/RENAMED 需要时计算
    renamed_from: str | None = None
    document_id: str | None = None
    error: str | None = None


@dataclass
class ScanResult:
    states: list[FileState] = field(default_factory=list)

    def by_status(self, status: str) -> list[FileState]:
        return [s for s in self.states if s.status == status]

    @property
    def has_changes(self) -> bool:
        return any(s.status != "UNCHANGED" for s in self.states)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(cfg: Config, conn: sqlite3.Connection, *, hash_changed: bool = True) -> ScanResult:
    """全量 manifest 扫描。只读知识源目录。"""
    result = ScanResult()
    exts = set(cfg.knowledge_base.extensions)
    roots = [Path(r) for r in cfg.knowledge_base.roots]

    # 磁盘文件
    disk: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            raise SourceFileError(f"知识库根目录不存在: {root}")
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$"):
                try:
                    st = p.stat()
                    disk[str(p)] = (st.st_size, st.st_mtime_ns)
                except OSError as exc:
                    result.states.append(FileState(str(p), "ERROR", error=str(exc)))

    # manifest（documents 表）
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
                    # 内容未变（仅 mtime 变化）：不重索引
                    state.status = "UNCHANGED"
        # RENAME 检测：本路径是 NEW，且存在同 sha256 的已删除 manifest 项
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
        # 未被 RENAME 认领的删除
        if not any(s.renamed_from == dpath for s in result.states):
            result.states.append(FileState(dpath, "DELETED", document_id=m["id"]))

    return result
