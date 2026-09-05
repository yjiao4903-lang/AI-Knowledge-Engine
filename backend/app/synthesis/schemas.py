"""SynthesisDraft Schema V1（主计划 §6/§7/§8）。

核心对象：`SynthesisDraft`——LLM 根据显式 Evidence 生成的结构化研究草稿。
它不是 Judgment / Proposal，也不写入正式认知（L1A 硬约束）。

设计要点：
- `EvidenceRef`：与 Integration Contract V1 §3 的持久 Identity 保持一致
  （source_type/document_id/section_id/chunk_id/content_hash/start_line/end_line）。
- `CognitionContextItem`：与 TaskPack 共用的只读 Cognition Context V1 contract。
- Claim 级 grounding（主计划 §7）：每个事实性 Claim 的 `evidence_refs` 显式绑定
  证据（用 chunk_id 作为稳定引用标识）。
- epistemic_state（主计划 §8）：supported / inference / hypothesis / uncertain /
  contradicted 固定枚举。
- Evidence Context Expansion 只扩展为更多显式 chunk identity，不拼接匿名上下文。
- LLM Context Envelope 中的证据统一以 `[En|chunk_id]` 形式呈现，模型须逐字引用
  chunk_id（Citation Rules §9），禁止虚构来源。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.contracts.cognition import CognitionContextItem

SCHEMA_VERSION = "1.0"
TASK_TYPES: tuple[str, ...] = (
    "summary",
    "comparison",
    "causal_synthesis",
    "tension_extraction",
)
EvidenceContextMode = Literal["none", "neighbor_1", "section"]

# 事实性（需要证据绑定）与断言性之分的依据：
# supported / inference / hypothesis / contradicted 均构成"断言"；
# uncertain 表示证据不足，不作为事实断言（不要求 evidence_refs）。
FACTUAL_STATES: tuple[str, ...] = (
    "supported",
    "inference",
    "hypothesis",
    "contradicted",
)
EPISTEMIC_STATES: tuple[str, ...] = (*FACTUAL_STATES, "uncertain")


class EvidenceRef(BaseModel):
    """EvidenceReference V1（Integration Contract §3 持久 Identity 子集）。

    请求方（Cognition 侧）传入持久 Identity 字段；正文由 KE 侧按 chunk_id
    从 catalog 权威解析，不信任客户端 excerpt（grounding 完整性）。
    """

    schema_version: str = Field(default="1.0", description="EvidenceReference V1")
    source_type: str = Field(..., description="report | cognition")
    document_id: str = Field(..., description="稳定 doc id（如 M04 / cog:...）")
    section_id: str | None = None
    chunk_id: str = Field(..., description="稳定 chunk id，作为引用标识")
    content_hash: str | None = None
    title: str | None = None
    heading_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence_level: int | None = Field(default=None, ge=1, le=5)
    excerpt: str | None = None  # 客户端快照，仅展示用；正文以 catalog 为准

    @field_validator("chunk_id")
    @classmethod
    def _chunk_id_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("chunk_id 不能为空")
        return v


class GeneratorInfo(BaseModel):
    """Draft 生成溯源（§36：不保存完整 Chain-of-Thought，只存结构化信息）。"""

    provider: str
    model: str
    prompt_version: str


class Claim(BaseModel):
    """一个事实性/推断性断言，Claim 级绑定 Evidence（主计划 §7）。"""

    id: str = Field(..., description="如 claim_001")
    text: str = Field(..., min_length=1)
    epistemic_state: Literal["supported", "inference", "hypothesis", "uncertain", "contradicted"]
    evidence_refs: list[str] = Field(
        default_factory=list, description="支持的证据 chunk_id 列表"
    )
    rationale: str | None = Field(default=None, description="简短依据（可选，非 CoT）")


class Tension(BaseModel):
    """证据之间的矛盾/张力（多证据指向不同方向）。"""

    id: str = Field(..., description="如 tension_001")
    text: str = Field(..., min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class SynthesisDraft(BaseModel):
    """非正式认知对象：LLM 根据显式 Evidence 生成的结构化研究草稿（主计划 §5/§6）。"""

    schema_version: str = SCHEMA_VERSION
    id: str = Field(..., description="如 synthesis_xxx")
    task_type: Literal["summary", "comparison", "causal_synthesis", "tension_extraction"]
    query: str = Field(..., min_length=1)
    created_at: str = Field(..., description="ISO 8601")
    generator: GeneratorInfo
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="本次实际使用的证据全集（含正文已经历 grounding）"
    )
    claims: list[Claim] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    summary: str = Field(default="", description="综述摘要")
    status: Literal["draft"] = "draft"


class SynthesisRequest(BaseModel):
    """POST /api/synthesis/tasks 请求体。

    Evidence、Dossier 与 Cognition stable IDs 都由调用方显式选择。Evidence 正文、
    Cognition 正文和 Dossier 当前状态由服务端从权威派生 catalog / planning store
    重新解析，不信任浏览器 excerpt。旧 `cognition_context` 字段保留协议兼容，但
    只把其中的 object_id/object_type 当选择提示，其正文/hash 会被服务端覆盖。

    `topic_candidate_id` 是 DL-05 研究规划层到 DL-03 TaskPack 的可选链接。服务端
    会重新读取候选并要求其已被用户 accepted；浏览器提供的 query 不是该候选的
    权威正文。链接只用于研究任务规划/去重，不会自动启动 Worker 或写 Cognition。
    """

    task_type: Literal["summary", "comparison", "causal_synthesis", "tension_extraction"]
    query: str = Field(..., min_length=1, max_length=1000)
    evidence_refs: list[EvidenceRef] = Field(
        ...,
        description="用户显式选定的 anchor evidence；Builder 可按 evidence_context_mode 扩展",
    )
    evidence_context_mode: EvidenceContextMode = "none"
    dossier_id: str | None = Field(
        default=None,
        max_length=80,
        description="可选 Topic Research Dossier stable ID；服务端生成研究上下文快照",
    )
    topic_candidate_id: str | None = Field(
        default=None,
        max_length=80,
        description="可选 accepted TopicCard candidate；仅用于研究规划链接与 TaskPack 去重",
    )
    cognition_object_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="推荐的新路径：用户显式选择的 Cognition stable object IDs",
    )
    cognition_context: list[CognitionContextItem] = Field(
        default_factory=list,
        description="兼容旧调用方；只复用 object_id/object_type 提示，正文由服务端重读",
    )


class SynthesisResponse(BaseModel):
    draft: SynthesisDraft
