"""TaskPack Builder（V3.0 方案 §31/§67）。

输入 query / task_type / EvidenceReference[] / 可选 cognition context，在
`<root>/outbox/<task_id>/` 生成完整只读任务包：

    task.yaml / AGENT_INSTRUCTION.md / evidence.jsonl /
    [cognition_context.jsonl] / output_schema.json / README.md /
    result/.gitkeep / manifest.json（最后写入）

正文与身份字段一律按 chunk_id 从 KE catalog 权威解析（EvidenceResolver，
F2 纪律），不信任调用方传入的 excerpt；document_id / section_id /
content_hash 以 catalog 为准，作为 Importer stale Gate（§48）的比对基准。
chunk 不存在 / hash 不一致时分别抛 404 / 409，由 API 层映射。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from app.core.config import Config
from app.synthesis.grounding import EvidenceResolver
from app.synthesis.schemas import EvidenceRef
from app.taskpack.manifest import build_manifest, sha256_file
from app.taskpack.schemas import (
    CognitionContextItem,
    Constraints,
    Manifest,
    TaskPackEvidence,
    TaskYaml,
)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
# 根目录 templates/ 下的正典模板（§5）；Builder 每次构建时同步到根目录
TEMPLATE_FILES: tuple[str, ...] = (
    "AGENT_INSTRUCTION_V1.md",
    "OUTPUT_SCHEMA_V1.json",
    "TASKPACK_README.md",
)
# TaskPack 根目录的固定子目录（§5）
ROOT_SUBDIRS: tuple[str, ...] = (
    "templates", "outbox", "processing", "completed", "failed", "archive",
)
# 每个包内的固定输入文件（§6）；cognition_context.jsonl 仅在提供时生成
PACK_INPUT_FILES: tuple[str, ...] = (
    "task.yaml", "AGENT_INSTRUCTION.md", "evidence.jsonl",
    "output_schema.json", "README.md",
)
MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class CreatedTask:
    """create_task 返回值：API 立即响应 {task_id, status, task_path}（§34）。"""

    task_id: str
    task_path: Path
    evidence_count: int
    cognition_context_count: int
    status: str = "READY"


def _slugify(text: str) -> str:
    """query 提取 ASCII 字母数字小写词作为 task_id 后缀（§7 示例形态）。"""
    words = re.findall(r"[a-zA-Z0-9]+", text)
    slug = "-".join(w.lower() for w in words)[:40].strip("-")
    return slug or "task"


class TaskPackBuilder:
    """TaskPack 构建器：只做本地文件编排，不感知任何模型与 Worker（§29）。"""

    def __init__(
        self,
        cfg: Config,
        report_conn,
        cognition_conn=None,
    ) -> None:
        self.cfg = cfg
        self.resolver = EvidenceResolver(cfg, report_conn, cognition_conn)
        self.root = Path(cfg.taskpack.root_dir)
        self.template_dir = TEMPLATE_DIR

    def _ensure_root(self) -> None:
        """确保根目录树存在，并把正典模板同步到 <root>/templates/（覆盖）。"""
        for sub in ROOT_SUBDIRS:
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        for name in TEMPLATE_FILES:
            src = self.template_dir / name
            if src.exists():
                shutil.copyfile(src, self.root / "templates" / name)

    def _resolve_evidence(self, evidence_refs) -> list[TaskPackEvidence]:
        """把 EvidenceReference[] 解析为 evidence.jsonl 行（EV001.. 编号）。"""
        resolved: list[TaskPackEvidence] = []
        for i, raw in enumerate(evidence_refs, start=1):
            ref = raw if isinstance(raw, EvidenceRef) else EvidenceRef.model_validate(raw)
            chunk = self.resolver.load_chunk(ref.chunk_id, ref.content_hash)
            text = chunk.get("plain_text") or chunk.get("raw_markdown") or ""
            heading = chunk.get("heading_path") or ref.heading_path or ""
            parts = [p for p in re.split(r"\s*>\s*", heading) if p]
            resolved.append(TaskPackEvidence(
                evidence_id=f"EV{i:03d}",
                source_type=ref.source_type,
                document_id=chunk.get("document_id") or ref.document_id,
                section_id=chunk.get("section_id"),
                chunk_id=ref.chunk_id,
                content_hash=chunk.get("content_hash") or ref.content_hash,
                title=heading or ref.title or ref.document_id,
                heading_path=parts,
                start_line=chunk.get("start_line"),
                end_line=chunk.get("end_line"),
                excerpt=text[: self.cfg.taskpack.evidence_max_chars],
            ))
        return resolved

    def _new_task_id(self, outbox: Path, now: datetime, query: str) -> str:
        """task_id = {YYYYMMDD_HHMMSS}_{slug}，同秒冲突时追加 -2/-3（§7）。"""
        base = f"{now.strftime('%Y%m%d_%H%M%S')}_{_slugify(query)}"
        task_id, n = base, 1
        while (outbox / task_id).exists():
            n += 1
            task_id = f"{base}-{n}"
        return task_id

    def create_task(
        self,
        *,
        task_type: str,
        query: str,
        evidence_refs: list,
        cognition_context: list | None = None,
        task_specific_instruction: str | None = None,
        max_claims: int | None = None,
        now: datetime | None = None,
    ) -> CreatedTask:
        query = (query or "").strip()
        if not query:
            raise ValueError("query 不能为空")
        if not evidence_refs:
            raise ValueError("evidence_refs 至少需要一条证据")
        if len(evidence_refs) > self.cfg.taskpack.max_evidence:
            raise ValueError(
                f"evidence_refs 数量（{len(evidence_refs)}）超过配置上限"
                f" taskpack.max_evidence={self.cfg.taskpack.max_evidence}"
            )
        now = now or datetime.now().astimezone()
        self._ensure_root()
        outbox = self.root / "outbox"
        task_id = self._new_task_id(outbox, now, query)
        pack = outbox / task_id
        pack.mkdir(parents=True)  # 不用 exist_ok：目录被并发占用时显式失败

        # 目录先占位以解决同秒并发冲突；在所有输入解析、模板复制和 manifest
        # 写完之前，任何异常都必须清理占位目录，避免外部 Worker 看见半成品 READY。
        try:
            return self._write_task_pack(
                pack=pack, task_id=task_id, task_type=task_type, query=query,
                evidence_refs=evidence_refs, cognition_context=cognition_context,
                task_specific_instruction=task_specific_instruction,
                max_claims=max_claims, now=now,
            )
        except BaseException:
            shutil.rmtree(pack, ignore_errors=True)
            raise

    def _write_task_pack(
        self, *, pack: Path, task_id: str, task_type: str, query: str, evidence_refs: list,
        cognition_context: list | None, task_specific_instruction: str | None,
        max_claims: int | None, now: datetime,
    ) -> CreatedTask:
        """Write a reserved pack; caller removes it on any failure/interruption."""

        created_at = now.isoformat(timespec="seconds")
        evidence = self._resolve_evidence(evidence_refs)
        cog_items = [
            CognitionContextItem.model_validate(c) for c in (cognition_context or [])
        ]

        task = TaskYaml(
            task_id=task_id,
            task_type=task_type,
            query=query,
            created_at=created_at,
            task_specific_instruction=task_specific_instruction,
            constraints=Constraints(
                max_claims=max_claims or self.cfg.taskpack.max_claims
            ),
        )
        (pack / "task.yaml").write_text(
            yaml.safe_dump(
                task.model_dump(by_alias=True, exclude_none=True),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        shutil.copyfile(
            self.template_dir / "AGENT_INSTRUCTION_V1.md", pack / "AGENT_INSTRUCTION.md"
        )
        (pack / "evidence.jsonl").write_text(
            "".join(json.dumps(e.model_dump(), ensure_ascii=False) + "\n" for e in evidence),
            encoding="utf-8",
        )
        if cog_items:
            (pack / "cognition_context.jsonl").write_text(
                "".join(json.dumps(c.model_dump(), ensure_ascii=False) + "\n" for c in cog_items),
                encoding="utf-8",
            )
        shutil.copyfile(
            self.template_dir / "OUTPUT_SCHEMA_V1.json", pack / "output_schema.json"
        )
        shutil.copyfile(self.template_dir / "TASKPACK_README.md", pack / "README.md")
        (pack / "result").mkdir()
        (pack / "result" / ".gitkeep").write_text("", encoding="utf-8")

        files = {name: sha256_file(pack / name) for name in PACK_INPUT_FILES}
        if cog_items:
            files["cognition_context.jsonl"] = sha256_file(pack / "cognition_context.jsonl")
        manifest: Manifest = build_manifest(
            task_id=task_id,
            created_at=created_at,
            files=files,
            evidence_count=len(evidence),
            cognition_context_count=len(cog_items),
        )
        (pack / MANIFEST_FILE).write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return CreatedTask(
            task_id=task_id,
            task_path=pack,
            evidence_count=len(evidence),
            cognition_context_count=len(cog_items),
        )
