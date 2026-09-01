"""TaskPack Importer / Watcher（V3.0 方案 §40-§48/§69/§81 Task 6）。

状态机（§40-§41）：事实依据 = 目录位置 + marker 文件。
    outbox/                     -> READY
    processing/                 -> PROCESSING
    completed/ + result/DONE    -> COMPLETED
    failed/ + FAILED            -> FAILED
    validator fail（八步 Gate 失败）-> INVALID_RESULT
    用户打开并接受到 Viewer（result/IMPORTED）-> IMPORTED
    archive/                    -> ARCHIVED

Importer 只读取 completed 中带 `result/DONE` 的任务（§44），避免读到半写 JSON。
按 §46 顺序执行八步 Gate，任何失败 -> INVALID_RESULT，不进 Viewer；
stale（§48）单独标注 STALE_EVIDENCE 供 UI 提示，且不自动改写 TaskPack。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.errors import EvidenceNotFoundError, EvidenceStaleError
from app.synthesis.grounding import EvidenceResolver
from app.synthesis.validator import validate_draft
from app.taskpack.manifest import sha256_file
from app.taskpack.builder import PACK_INPUT_FILES
from app.taskpack.schemas import (
    Manifest,
    ResultEnvelope,
    RunMeta,
    TaskPackEvidence,
    TaskYaml,
    is_safe_task_id,
)

# 任务状态机枚举（§40）
READY = "READY"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
INVALID_RESULT = "INVALID_RESULT"
IMPORTED = "IMPORTED"
ARCHIVED = "ARCHIVED"

STATUSES = (READY, PROCESSING, COMPLETED, FAILED, INVALID_RESULT, IMPORTED, ARCHIVED)

# 顶层子目录（§5）
OUTBOX = "outbox"
PROCESSING_DIR = "processing"
COMPLETED_DIR = "completed"
FAILED_DIR = "failed"
ARCHIVE_DIR = "archive"

# Worker / 检索侧 marker 文件
DONE_MARKER = "result/DONE"
FAILED_MARKER = "result/FAILED"
INVALID_MARKER = "result/INVALID"
IMPORTED_MARKER = "result/IMPORTED"


@dataclass(frozen=True)
class GateResult:
    """单步 Gate 结果。passed=False 时 failure 记录人类可读原因。"""

    name: str
    passed: bool
    failure: str | None = None


class ImportFailure(Exception):
    """识别出的验证失败：构造函数携带 Gate 名 + 原因 + 是否 stale。"""

    def __init__(
        self,
        gate: str,
        reason: str,
        *,
        stale: bool = False,
        detail: dict | None = None,
    ) -> None:
        super().__init__(f"{gate}: {reason}")
        self.gate = gate
        self.reason = reason
        self.stale = stale
        self.detail = detail or {}


@dataclass
class ImportReport:
    """一次 import 的完整结果（八步 Gate 逐项 + grounding 指标）。"""

    task_id: str
    task_path: Path
    gates: list[GateResult] = field(default_factory=list)
    passed: bool = False
    schema_valid: bool = False
    citation_invalid: int = 0
    citation_coverage: float | None = None
    unsupported_claim_rate: float | None = None
    stale: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, passed: bool, failure: str | None = None) -> None:
        self.gates.append(GateResult(name=name, passed=passed, failure=failure))

    @property
    def first_failure(self) -> GateResult | None:
        return next((g for g in self.gates if not g.passed), None)


@dataclass
class TaskInfo:
    """单任务的可读摘要（Task Center 行 / API 视图，§38）。"""

    task_id: str
    task_path: str
    status: str
    task_type: str | None = None
    query: str | None = None
    created_at: str | None = None
    evidence_count: int | None = None
    worker: str | None = None
    model: str | None = None
    completed_at: str | None = None
    stale: bool = False
    error: str | None = None


class TaskPackImporter:
    """扫描 completed/ 并按八步 Gate 导入外部 Worker 的结果。

    不自行并行调度 Worker（§42：V1 无自动多 Worker），只做读与验证。
    """

    def __init__(self, cfg: Config, report_conn, cognition_conn=None) -> None:
        self.cfg = cfg
        self.root = Path(cfg.taskpack.root_dir)
        self.resolver = EvidenceResolver(cfg, report_conn, cognition_conn)

    # ---------------- 路径 / 状态 ----------------

    def _subdir(self, name: str) -> Path:
        return self.root / name

    @staticmethod
    def _read_json(path: Path) -> dict:
        """Read external JSON with optional UTF-8 BOM; validation remains separate."""
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _read_task_yaml(self, pack: Path) -> TaskYaml | None:
        p = pack / "task.yaml"
        if not p.exists():
            return None
        import yaml

        try:
            return TaskYaml.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _read_manifest(self, pack: Path) -> Manifest | None:
        p = pack / "manifest.json"
        if not p.exists():
            return None
        try:
            return Manifest.model_validate(self._read_json(p))
        except Exception:
            return None

    def _read_evidence(self, pack: Path) -> list[TaskPackEvidence]:
        p = pack / "evidence.jsonl"
        if not p.exists():
            return []
        out: list[TaskPackEvidence] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(TaskPackEvidence.model_validate(json.loads(line)))
            except Exception:
                continue
        return out

    def _read_result(self, pack: Path) -> tuple[ResultEnvelope, dict] | None:
        p = pack / "result" / "result.json"
        if not p.exists():
            return None
        try:
            raw = self._read_json(p)
        except Exception:
            return None
        try:
            return ResultEnvelope.model_validate(raw), raw
        except Exception:
            return None

    def _read_run_meta(self, pack: Path) -> RunMeta | None:
        p = pack / "result" / "run_meta.json"
        if not p.exists():
            return None
        try:
            return RunMeta.model_validate(self._read_json(p))
        except Exception:
            return None

    def status_of(self, pack: Path) -> str:
        """根据目录位置 + marker 判定状态（§40-§41，事实依据）。"""
        if not pack.is_dir():
            return INVALID_RESULT
        rel = pack.relative_to(self.root).parts
        top = rel[0] if rel else ""
        if top == OUTBOX:
            return READY
        if top == PROCESSING_DIR:
            return PROCESSING
        if top == FAILED_DIR:
            return FAILED if (pack / "result" / "FAILED").exists() else PROCESSING
        if top == ARCHIVE_DIR:
            return ARCHIVED
        if top == COMPLETED_DIR:
            if (pack / INVALID_MARKER).exists():
                return INVALID_RESULT
            if (pack / IMPORTED_MARKER).exists():
                return IMPORTED
            if (pack / DONE_MARKER).exists():
                return COMPLETED
            # completed 但无 DONE：结果未就绪，不导入（§44）
            return PROCESSING
        return READY  # 未知位置（应在根下子目录中）——保守视为待处理

    def locate(self, task_id: str) -> Path | None:
        """在全部子目录中定位任务目录（防止重复/移动后查找）。"""
        if not is_safe_task_id(task_id):
            return None
        for sub in (OUTBOX, PROCESSING_DIR, COMPLETED_DIR, FAILED_DIR, ARCHIVE_DIR):
            p = self.root / sub / task_id
            if p.is_dir():
                return p
        return None

    # ---------------- 八步 Gate（§46） ----------------

    def _gate_manifest(self, pack: Path) -> list[GateResult]:
        manifest = self._read_manifest(pack)
        if manifest is None:
            return [GateResult("manifest", False, "manifest.json 缺失或非法")]
        if manifest.files is None:
            return [GateResult("manifest", False, "manifest.files 缺失")]
        for name, expect in manifest.files.items():
            p = pack / name
            if not p.exists() or sha256_file(p) != expect:
                bad = name if not p.exists() else name
                return [GateResult("manifest", False, f"文件校验失败: {bad}")]
        # evidence / cognition 计数一致性
        ev_count = self._count_lines(pack / "evidence.jsonl")
        if ev_count != manifest.evidence_count:
            return [GateResult("manifest", False,
                               f"evidence_count 不一致({ev_count} != {manifest.evidence_count})")]
        cog_count = self._count_lines(pack / "cognition_context.jsonl") if (pack / "cognition_context.jsonl").exists() else 0
        if cog_count != manifest.cognition_context_count:
            return [GateResult("manifest", False,
                               f"cognition_context_count 不一致({cog_count} != {manifest.cognition_context_count})")]
        return [GateResult("manifest", True)]

    def _count_lines(self, p: Path) -> int:
        if not p.exists():
            return 0
        return len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])

    def _gate_schema(self, pack: Path) -> list[GateResult]:
        result = self._read_result(pack)
        if result is None:
            return [GateResult("result_schema", False, "result/result.json 缺失或不符合 SynthesisDraftV1")]
        return [GateResult("result_schema", True)]

    def _gate_task_id(self, pack: Path) -> list[GateResult]:
        task = self._read_task_yaml(pack)
        result = self._read_result(pack)
        if task is None or result is None:
            return [GateResult("task_id", False, "task.yaml 或 result.json 缺失")]
        if result[0].task_id != task.task_id:
            return [GateResult("task_id", False,
                               f"result.task_id({result[0].task_id}) != task.task_id({task.task_id})")]
        return [GateResult("task_id", True)]

    def _gate_prompt_sha(self, pack: Path) -> list[GateResult]:
        meta = self._read_run_meta(pack)
        if meta is None:
            return [GateResult("prompt_sha", False, "result/run_meta.json 缺失或非法")]
        instr = pack / "AGENT_INSTRUCTION.md"
        prompt_sha = sha256_file(instr) if instr.exists() else None
        if prompt_sha is None or meta.prompt_sha256 != prompt_sha:
            return [GateResult("prompt_sha", False,
                               "run_meta.prompt_sha256 与 AGENT_INSTRUCTION.md 不匹配")]
        manifest_sha = sha256_file(pack / "manifest.json") if (pack / "manifest.json").exists() else None
        if manifest_sha is None or meta.task_manifest_sha256 != manifest_sha:
            return [GateResult("prompt_sha", False,
                               "run_meta.task_manifest_sha256 与 manifest.json 不匹配")]
        return [GateResult("prompt_sha", True)]

    def _gate_evidence_membership(self, pack: Path) -> list[GateResult]:
        result = self._read_result(pack)
        evidence = self._read_evidence(pack)
        allowed = {e.chunk_id for e in evidence}
        refs: list[str] = []
        if result is not None:
            for c in result[0].claims:
                refs.extend(c.evidence_refs or [])
            for t in result[0].tensions:
                refs.extend(t.evidence_refs or [])
        bad = [r for r in refs if r not in allowed]
        if bad:
            return [GateResult("evidence_membership", False,
                               f"引用了 evidence.jsonl 之外的 chunk_id: {bad[:10]}")]
        return [GateResult("evidence_membership", True)]

    def _gate_citation(self, pack: Path) -> list[GateResult]:
        """步骤⑥ ⑦：重复利用已有 grounding 校验器（§47）。"""
        result = self._read_result(pack)
        evidence = self._read_evidence(pack)
        if result is None:
            return [GateResult("citation_coverage", False, "result.json 缺失")]
        allowed = {e.chunk_id for e in evidence}
        rep = validate_draft(result[0], allowed)
        if not rep.schema_valid:
            return [GateResult("citation_coverage", False, "; ".join(rep.errors[:5]))]
        return [
            GateResult("citation_invalid", not rep.citation_invalid,
                       None if not rep.citation_invalid else f"引用了未提供证据: {rep.citation_invalid[:10]}"),
            GateResult("citation_coverage",
                       rep.citation_coverage is not None and rep.citation_coverage >= 0.95,
                       None if (rep.citation_coverage is not None and rep.citation_coverage >= 0.95)
                       else f"coverage={rep.citation_coverage} < 95%"),
            GateResult("unsupported_claim",
                       rep.unsupported_claim_rate is not None and rep.unsupported_claim_rate <= 0.05,
                       None if (rep.unsupported_claim_rate is not None and rep.unsupported_claim_rate <= 0.05)
                       else f"unsupported={rep.unsupported_claim_rate} > 5%"),
        ]

    def _gate_stale(self, pack: Path) -> list[GateResult]:
        """步骤⑧：TaskPack evidence content_hash vs catalog 当前（§48）。
        不一致仅标注 stale，不自动改写 TaskPack。"""
        evidence = self._read_evidence(pack)
        stale_ids: list[str] = []
        for e in evidence:
            try:
                self.resolver.load_chunk(e.chunk_id, e.content_hash)
            except EvidenceStaleError:
                stale_ids.append(e.chunk_id)
            except EvidenceNotFoundError:
                stale_ids.append(e.chunk_id)
        if stale_ids:
            return [GateResult("stale", False, f"证据自创建后已变化: {stale_ids[:10]}")]
        return [GateResult("stale", True)]

    # ---------------- import ----------------

    def import_task(self, pack: Path) -> ImportReport:
        """按 §46 顺序执行八步 Gate，任何失败 -> INVALID_RESULT。"""
        manifest = self._read_manifest(pack)
        task_id = manifest.task_id if manifest is not None else pack.name
        report = ImportReport(task_id=task_id, task_path=pack)

        gate_fns = [
            self._gate_manifest,
            self._gate_schema,
            self._gate_task_id,
            self._gate_prompt_sha,
            self._gate_evidence_membership,
            self._gate_citation,
            self._gate_stale,
        ]
        failed: str | None = None
        for fn in gate_fns:
            gates = fn(pack)
            for g in gates:
                report.add(g.name, g.passed, g.failure)
                if not g.passed:
                    failed = f"{g.name}: {g.failure}"
            if failed:
                break

        result = self._read_result(pack)
        evidence = self._read_evidence(pack)
        if result is not None and evidence:
            allowed = {e.chunk_id for e in evidence}
            rep = validate_draft(result[0], allowed)
            report.schema_valid = rep.schema_valid
            report.citation_invalid = len(rep.citation_invalid)
            report.citation_coverage = rep.citation_coverage
            report.unsupported_claim_rate = rep.unsupported_claim_rate

        report.stale = any(g.name == "stale" and not g.passed for g in report.gates)
        report.passed = failed is None
        report.details = {
            "worker": result[0].worker.tool if result is not None else None,
            "model": result[0].worker.model if result is not None else None,
        }

        if not report.passed:
            self._mark_invalid(pack, report)
        return report

    def _mark_invalid(self, pack: Path, report: ImportReport) -> None:
        """INVALID_RESULT 落一个 result/INVALID 标记（含失败原因），供状态机识别。"""
        payload = {
            "task_id": report.task_id,
            "passed": False,
            "reason": report.first_failure.failure if report.first_failure else "unknown",
            "gate": report.first_failure.name if report.first_failure else None,
            "stale": report.stale,
        }
        (pack / "result").mkdir(parents=True, exist_ok=True)
        # 同时清理可能残留的 IMPORTED / COMPLETED 语义
        for marker in (IMPORTED_MARKER,):
            mp = pack / marker
            if mp.exists():
                try:
                    mp.unlink()
                except OSError:
                    pass
        (pack / INVALID_MARKER).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ---------------- Watcher ----------------

    def scan(self) -> list[ImportReport]:
        """扫描 completed/ 中带 result/DONE 的任务并导入；返回全部 import 报告。"""
        reports: list[ImportReport] = []
        completed = self._subdir(COMPLETED_DIR)
        if not completed.is_dir():
            return reports
        for entry in sorted(completed.iterdir()):
            if not entry.is_dir():
                continue
            if not (entry / DONE_MARKER).exists():
                continue  # 无 DONE 不导入（§44）
            # 已导入 / 已判 INVALID 的任务不重复导入
            if (entry / INVALID_MARKER).exists():
                continue
            if (entry / IMPORTED_MARKER).exists():
                continue
            report = self.import_task(entry)
            reports.append(report)
        return reports

    def list_tasks(self) -> list[TaskInfo]:
        """扫描全子目录，返回 Task Center 行（§38）。"""
        infos: list[TaskInfo] = []
        for sub in (OUTBOX, PROCESSING_DIR, COMPLETED_DIR, FAILED_DIR, ARCHIVE_DIR):
            base = self._subdir(sub)
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if not entry.is_dir():
                    continue
                infos.append(self._make_task_info(entry))
        return infos

    def _make_task_info(self, pack: Path) -> TaskInfo:
        task = self._read_task_yaml(pack)
        manifest = self._read_manifest(pack)
        result = self._read_result(pack)
        meta = self._read_run_meta(pack)
        status = self.status_of(pack)
        stale = (pack / INVALID_MARKER).exists() and self._invalid_marker_stale(pack)
        error = None
        if (pack / INVALID_MARKER).exists():
            try:
                error = json.loads((pack / INVALID_MARKER).read_text(encoding="utf-8")).get("reason")
            except Exception:
                error = "result 未通过验证"
        return TaskInfo(
            task_id=pack.name,
            task_path=str(pack),
            status=status,
            task_type=task.task_type if task is not None else None,
            query=task.query if task is not None else None,
            created_at=task.created_at if task is not None else manifest.created_at if manifest is not None else None,
            evidence_count=manifest.evidence_count if manifest is not None else (
                self._count_lines(pack / "evidence.jsonl")),
            worker=(meta.worker_tool if meta is not None
                    else (result[0].worker.tool if result is not None else None)),
            model=(meta.model if meta is not None
                   else (result[0].worker.model if result is not None else None)),
            completed_at=result[0].generated_at if result is not None else None,
            stale=stale,
            error=error,
        )

    def _invalid_marker_stale(self, pack: Path) -> bool:
        p = pack / INVALID_MARKER
        if not p.exists():
            return False
        try:
            return bool(json.loads(p.read_text(encoding="utf-8")).get("stale"))
        except Exception:
            return False

    def rescan_task(self, task_id: str) -> ImportReport | None:
        """对单个任务触发扫描（§43：前端轮询时触发 scan）。"""
        pack = self.locate(task_id)
        if pack is None:
            return None
        if pack.relative_to(self.root).parts[0] != COMPLETED_DIR:
            return None
        if not (pack / DONE_MARKER).exists():
            return None
        invalid_marker = pack / INVALID_MARKER
        if invalid_marker.exists():
            invalid_marker.unlink()
        return self.import_task(pack)

    def archive_task(self, task_id: str) -> Path:
        """移动 -> ARCHIVED（§40）。"""
        pack = self.locate(task_id)
        if pack is None:
            raise FileNotFoundError(f"任务不存在: {task_id}")
        if pack.relative_to(self.root).parts[0] == ARCHIVE_DIR:
            return pack
        dst = self._subdir(ARCHIVE_DIR)
        dst.mkdir(parents=True, exist_ok=True)
        target = dst / pack.name
        # 归档必须是同卷原子 rename；禁止 shutil.move 在目标已存在时产生
        # 覆盖/嵌套目录等平台相关行为。碰撞由调用方显式处理并保留原任务。
        if target.exists():
            raise FileExistsError(f"归档目标已存在: {target}")
        pack.rename(target)
        return target
