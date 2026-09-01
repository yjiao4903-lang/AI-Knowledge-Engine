"""TaskPack V1 Schema（V3.0 方案 §7/§9/§10/§11/§13/§14/§17/§23/§66）。

TaskPack 是 Research OS 与外部 Worker（Trae/Codex/Claude Code 等）之间的唯一
正式边界：KE 侧 Builder 生成只读任务包，外部工具读取并产出 result.json，
Importer 按八步 Gate 校验后导入（方案 §46）。所有 Schema 显式版本化（§66），
升级时新增版本号，不原地变更字段语义。

- TaskYaml：task.yaml（§7），任务身份/权限/约束/期望输出。
- TaskPackEvidence：evidence.jsonl 每行（§9），Fixed Evidence Set 成员快照。
- CognitionContextItem：cognition_context.jsonl 每行（§10，可选）。
- Manifest：manifest.json（§11），不可变输入 sha256 清单，Importer 必校验。
- RunMeta：result/run_meta.json（§23），Worker 运行溯源。
- ResultEnvelope：result/result.json（§13），SynthesisDraft V1 的 TaskPack 派生
  形态——claims/tensions 直接复用 app.synthesis.schemas 的 Claim/Tension（§14
  示例中的 claim_id 统一为 Claim.id），新增 additional_evidence_needed（§17）。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.synthesis.schemas import Claim, Tension

TASKPACK_VERSION = "1.0"
RESULT_SCHEMA_VERSION = "1.0"
DEFAULT_PROMPT_VERSION = "taskpack-synthesis-v1"

TaskType = Literal["summary", "comparison", "causal_synthesis", "tension_extraction"]

_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _check_task_id(value: str) -> str:
    v = value.strip()
    if ".." in v or not _TASK_ID_RE.fullmatch(v):
        raise ValueError(
            f"task_id 非法（只允许 [A-Za-z0-9._-]，不得包含 ..，作为目录名必须路径安全）：{value!r}"
        )
    return v


def is_safe_task_id(value: str) -> bool:
    """Return whether a value is valid for both a TaskPack ID and directory name.

    Importer callers are not all HTTP routes, so path safety must be enforced at
    the filesystem boundary as well as by the request schema.
    """
    try:
        _check_task_id(value)
    except (AttributeError, ValueError):
        return False
    return True


def _check_sha256(value: str) -> str:
    v = value.strip().lower()
    if not _SHA256_RE.fullmatch(v):
        raise ValueError(f"sha256 必须是 64 位十六进制字符串：{value!r}")
    return v


def _check_iso_datetime(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"必须是 ISO 8601 时间字符串：{value!r}") from exc
    return value


class Permissions(BaseModel):
    """task.yaml permissions（§7）：默认全禁，唯一可写目录为 result/。"""

    read_only_inputs: bool = True
    allow_network: bool = False
    allow_external_sources: bool = False
    allow_write_paths: list[str] = Field(default_factory=lambda: ["result/"])


class Constraints(BaseModel):
    """task.yaml constraints（§7）：Evidence only、claims 条数上限、输出语言。"""

    evidence_only: bool = True
    max_claims: int = Field(default=12, ge=1)
    language: str = "zh-CN"


class ExpectedOutput(BaseModel):
    """task.yaml expected_output（§7）。

    YAML 键名为 `schema`，通过别名承接以避开 pydantic 模型方法名；序列化时
    以 by_alias=True 输出 `schema`，保证与 §7 示例一致。
    """

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(default="SynthesisDraftV1", alias="schema")
    path: str = "result/result.json"


class TaskYaml(BaseModel):
    """task.yaml（§7）。task_id 同时是任务目录名，必须路径安全（§6）。"""

    schema_version: Literal["1.0"] = "1.0"
    task_id: str
    task_type: TaskType
    query: str = Field(..., min_length=1)
    created_at: str
    taskpack_version: Literal["1.0"] = TASKPACK_VERSION
    prompt_version: str = DEFAULT_PROMPT_VERSION
    task_specific_instruction: str | None = None
    permissions: Permissions = Field(default_factory=Permissions)
    constraints: Constraints = Field(default_factory=Constraints)
    expected_output: ExpectedOutput = Field(default_factory=ExpectedOutput)

    @field_validator("task_id")
    @classmethod
    def _valid_task_id(cls, v: str) -> str:
        return _check_task_id(v)

    @field_validator("created_at")
    @classmethod
    def _valid_created_at(cls, v: str) -> str:
        return _check_iso_datetime(v)


class TaskPackEvidence(BaseModel):
    """evidence.jsonl 单行（§9）：任务级 Fixed Evidence Set 成员快照。

    与 API 层 EvidenceRef（app.synthesis.schemas）的差异：heading_path 为数组、
    携带 evidence_id 与截断正文 excerpt。content_hash 是 Importer stale Gate
    （§48）与 catalog 比对的基准；evidence_refs 只允许引用其中的 chunk_id（§16）。
    """

    evidence_id: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    section_id: str | None = None
    chunk_id: str = Field(..., min_length=1)
    content_hash: str | None = None
    title: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str | None = None


class CognitionContextItem(BaseModel):
    """cognition_context.jsonl 单行（§10，可选）：最小必要的既有认知快照，只读。"""

    context_id: str = Field(..., min_length=1)
    object_type: str = Field(..., min_length=1)
    object_id: str = Field(..., min_length=1)
    content_hash: str | None = None
    title: str | None = None
    excerpt: str | None = None


class Manifest(BaseModel):
    """manifest.json（§11）：不可变输入 sha256 清单，Importer 第一步 Gate（§46）。

    files 的键为任务包内文件名，值为该文件的 sha256（小写十六进制）；
    读取侧 extra="allow" 以兼容后续版本附加字段。
    """

    model_config = ConfigDict(extra="allow")

    taskpack_version: Literal["1.0"] = TASKPACK_VERSION
    task_id: str
    created_at: str
    files: dict[str, str] = Field(default_factory=dict)
    evidence_count: int = Field(default=0, ge=0)
    cognition_context_count: int = Field(default=0, ge=0)

    @field_validator("task_id")
    @classmethod
    def _valid_task_id(cls, v: str) -> str:
        return _check_task_id(v)

    @field_validator("created_at")
    @classmethod
    def _valid_created_at(cls, v: str) -> str:
        return _check_iso_datetime(v)

    @field_validator("files")
    @classmethod
    def _valid_file_hashes(cls, v: dict[str, str]) -> dict[str, str]:
        return {name: _check_sha256(h) for name, h in v.items()}


class RunMeta(BaseModel):
    """result/run_meta.json（§23）：Worker 运行溯源。

    时间与 token 由外部工具填写，不可得时填 null（§19 第六节）；时间字段不做
    严格 ISO 校验（避免把格式瑕疵误判为 INVALID_RESULT），prompt/manifest 的
    sha256 则必须可校验——它们是 Importer 第四步 Gate 的匹配基准。
    """

    worker_tool: str = Field(..., min_length=1)
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    prompt_version: str = DEFAULT_PROMPT_VERSION
    prompt_sha256: str
    task_manifest_sha256: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    @field_validator("prompt_sha256", "task_manifest_sha256")
    @classmethod
    def _valid_hashes(cls, v: str) -> str:
        return _check_sha256(v)


class WorkerInfo(BaseModel):
    """result.json `worker` 字段（§13）：生成工具溯源。"""

    model_config = ConfigDict(extra="allow")

    tool: str = Field(..., min_length=1)
    model: str | None = None


class AdditionalEvidenceNeeded(BaseModel):
    """additional_evidence_needed 条目（§17）：证据不足时的显式缺口声明。

    这是 TaskPack 协议的核心安全阀——禁止 Worker 用包外知识补洞，
    必须把缺口写成结构化问题。
    """

    question: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ResultEnvelope(BaseModel):
    """result/result.json（§13）：SynthesisDraft V1 的 TaskPack 派生形态。

    与 SynthesisDraft 的差异：task_id 替代 id、worker 替代 generator、
    generated_at 替代 created_at、新增 additional_evidence_needed。
    epistemic_state 固定五枚举（§15）；evidence_refs 的逐字 chunk_id membership
    由 Importer 独立 Gate（§46 步骤⑤）校验，本 Schema 不重复。读取侧
    extra="allow"：多出的无害元数据不触发 INVALID_RESULT。
    """

    model_config = ConfigDict(extra="allow")

    schema_version: Literal["1.0"] = RESULT_SCHEMA_VERSION
    task_id: str
    task_type: TaskType
    query: str = Field(..., min_length=1)
    summary: str = ""
    claims: list[Claim] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    additional_evidence_needed: list[AdditionalEvidenceNeeded] = Field(default_factory=list)
    worker: WorkerInfo
    generated_at: str = Field(..., min_length=1)

    @field_validator("task_id")
    @classmethod
    def _valid_task_id(cls, v: str) -> str:
        return _check_task_id(v)


class TaskPackV1(BaseModel):
    """单个 TaskPack 的聚合 Schema（§66）：task.yaml + 输入行集 + manifest。"""

    task: TaskYaml
    evidence: list[TaskPackEvidence] = Field(default_factory=list)
    cognition_context: list[CognitionContextItem] = Field(default_factory=list)
    manifest: Manifest

    @model_validator(mode="after")
    def _check_consistency(self) -> "TaskPackV1":
        if self.manifest.task_id != self.task.task_id:
            raise ValueError(
                f"manifest.task_id（{self.manifest.task_id!r}）与 task.task_id"
                f"（{self.task.task_id!r}）不一致"
            )
        if self.manifest.evidence_count != len(self.evidence):
            raise ValueError(
                f"manifest.evidence_count（{self.manifest.evidence_count}）与实际"
                f" evidence 行数（{len(self.evidence)}）不一致"
            )
        if self.manifest.cognition_context_count != len(self.cognition_context):
            raise ValueError(
                f"manifest.cognition_context_count（{self.manifest.cognition_context_count}）"
                f"与实际 cognition_context 行数（{len(self.cognition_context)}）不一致"
            )
        return self
