"""TaskPack manifest 构建与文件 sha256（V3.0 方案 §11/§12）。

manifest.json 是任务包不可变输入的 sha256 清单：Builder 在全部输入文件落盘后
最后写入（保证清单反映最终内容），Importer 第一步 Gate 逐文件重算比对，
任何输入被改动都会导致结果被拒绝。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.taskpack.schemas import Manifest


def sha256_file(path: str | Path) -> str:
    """流式计算文件 sha256（小写十六进制）；清单构建与 Importer 校验共用。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    *,
    task_id: str,
    created_at: str,
    files: dict[str, str],
    evidence_count: int,
    cognition_context_count: int,
) -> Manifest:
    """构造 manifest.json（§11）：至少包含版本/任务号/时间/files/count 字段。"""
    return Manifest(
        taskpack_version="1.0",
        task_id=task_id,
        created_at=created_at,
        files=files,
        evidence_count=evidence_count,
        cognition_context_count=cognition_context_count,
    )
