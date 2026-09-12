"""配置加载（M1-02 + I8 Research OS runtime overrides）。

以 config/config.yaml 为准（不存在时回退 config.example.yaml），全部参数可用
pydantic 模型校验与默认值兜底。I8 增加少量显式环境变量覆盖，使统一 runtime、
备份脚本与后端实际读取路径保持一致。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "config"


class AppConfig(BaseModel):
    name: str = "AI Research Knowledge Engine"
    bind_host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"


class KnowledgeBaseConfig(BaseModel):
    roots: list[str] = Field(default_factory=lambda: ["D:/AI深度报告归档"])
    read_only: bool = True
    extensions: list[str] = Field(default_factory=lambda: [".md"])


class PathsConfig(BaseModel):
    data_dir: str = str(PROJECT_ROOT / "data")
    model_dir: str = "D:/AI-Models"
    log_dir: str = str(PROJECT_ROOT / "logs")


class SqliteConfig(BaseModel):
    path: str = str(PROJECT_ROOT / "data" / "catalog.db")
    wal: bool = True


class QdrantConfig(BaseModel):
    url: str = "http://127.0.0.1:6333"
    chunks_collection: str = "kb_chunks_v1"
    sections_collection: str = "kb_sections_v1"


class CognitionConfig(BaseModel):
    """Cognition read-only retrieval + Proposal/Human-Apply integration."""

    enabled: bool = True
    root: str = "E:/CODEX/AI深度研究/cognition"
    catalog_path: str = str(PROJECT_ROOT / "data" / "catalog_cognition.db")
    chunks_collection: str = "kb_cognition_chunks_v1"
    include_dirs: list[str] = Field(default_factory=lambda: [
        "02_来源与阅读",
        "03_问题池",
        "04_判断台账",
        "05_主题页",
        "06_研究项目",
        "07_复盘",
    ])
    startup_scan: bool = True
    periodic_reconcile_seconds: int = 300
    docid_prefix: str = "cog"
    api_url: str = "http://127.0.0.1:3220/api"
    api_timeout_seconds: float = 8.0
    proposal_publish_enabled: bool = True
    # Formal Apply remains opt-in even after a candidate is accepted and Previewed.
    formal_apply_enabled: bool = False


class EmbeddingConfig(BaseModel):
    model: str = "Qwen/Qwen3-Embedding-0.6B"
    local_path: str = "D:/AI-Models/Qwen3-Embedding-0.6B"
    dimension: int = 1024
    normalize: bool = True
    preferred_device: str = "rocm"
    fallback_device: str = "cpu"
    dtype_gpu: str = "float16"
    batch_size_gpu: int = 8
    batch_size_cpu: int = 2
    max_tokens: int = 4096
    query_instruction: str = (
        "Given a query for a private research knowledge base, retrieve the most "
        "relevant passages from Chinese and English technical, semiconductor, AI, "
        "macroeconomic, industry, and investment research reports. Preserve exact "
        "entities, model names, technical terms, causal relationships, "
        "quantitative indicators, and evidence levels."
    )


class RerankerConfig(BaseModel):
    model: str = "Qwen/Qwen3-Reranker-0.6B"
    local_path: str = "D:/AI-Models/Qwen3-Reranker-0.6B"
    preferred_device: str = "rocm"
    fallback_device: str = "cpu"
    dtype_gpu: str = "float16"
    max_tokens: int = 3072
    candidate_k: int = 24
    enabled: bool = True
    batch_size: int = 8
    instruction: str = (
        "Given a query for a private research knowledge base, judge whether the "
        "document passage is highly relevant and useful for answering the query."
    )
    cpu_max_candidates: int = 8


class ChunkingConfig(BaseModel):
    target_chars: int = 900
    soft_min_chars: int = 350
    soft_max_chars: int = 1400
    hard_max_chars: int = 2200
    overlap_chars: int = 100
    keep_tables_whole: bool = True
    keep_formulas_with_explanation: bool = True


class RetrievalConfig(BaseModel):
    dense_k: int = 50
    fts_terms_k: int = 50
    fts_trigram_k: int = 30
    fused_k: int = 30
    rerank_k: int = 24
    final_k: int = 10


class FusionConfig(BaseModel):
    method: str = "rrf"
    rrf_k: int = 60
    dense_weight: float = 1.0
    terms_weight: float = 0.9
    trigram_weight: float = 0.7
    parent_boost: float = 1.08
    parent_boost_sections_k: int = 8
    parent_boost_enabled: bool = True


class IndexingConfig(BaseModel):
    startup_scan: bool = True
    periodic_reconcile_seconds: int = 300
    watcher_enabled: bool = True


class InferenceConfig(BaseModel):
    """显式推理设备配置（Addendum §17）。"""

    preferred_device: str = "auto"
    preferred_gpu_name: str = "RX 7900 XTX"
    force_device: str | None = None
    worker_timeout_seconds: float = 120.0
    worker_start_timeout_seconds: float = 300.0
    max_consecutive_crashes: int = 2


class TaskPackConfig(BaseModel):
    """TaskPack 外部模型工作流配置。"""

    enabled: bool = True
    root_dir: str = str(PROJECT_ROOT / "data" / "taskpacks")
    prompt_version: str = "taskpack-synthesis-v1"
    max_evidence: int = 20
    evidence_max_chars: int = 1200
    max_claims: int = 12
    periodic_scan_seconds: int = 0


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    knowledge_base: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    sqlite: SqliteConfig = Field(default_factory=SqliteConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    cognition: CognitionConfig = Field(default_factory=CognitionConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    taskpack: TaskPackConfig = Field(default_factory=TaskPackConfig)


def _env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _apply_runtime_env_overrides(cfg: Config) -> Config:
    """Apply operational overrides shared with runtime/research-os.ps1."""

    if os.environ.get("AIKE_KE_PORT"):
        cfg.app.port = int(os.environ["AIKE_KE_PORT"])
    if os.environ.get("COGNITION_DATA_ROOT"):
        cfg.cognition.root = os.environ["COGNITION_DATA_ROOT"]
    if os.environ.get("COGNITION_API_URL"):
        cfg.cognition.api_url = os.environ["COGNITION_API_URL"]
    if os.environ.get("AIKE_COGNITION_FORMAL_APPLY"):
        cfg.cognition.formal_apply_enabled = _env_bool(os.environ["AIKE_COGNITION_FORMAL_APPLY"])
    if os.environ.get("AIKE_TASKPACK_ROOT"):
        cfg.taskpack.root_dir = os.environ["AIKE_TASKPACK_ROOT"]
    if os.environ.get("AIKE_KB_ROOT"):
        cfg.knowledge_base.roots = [os.environ["AIKE_KB_ROOT"]]
    if os.environ.get("AIKE_MODEL_ROOT"):
        model_root = Path(os.environ["AIKE_MODEL_ROOT"])
        cfg.paths.model_dir = str(model_root)
        cfg.embedding.local_path = str(model_root / "Qwen3-Embedding-0.6B")
        cfg.reranker.local_path = str(model_root / "Qwen3-Reranker-0.6B")
    return cfg


def load_config(path: str | Path | None = None) -> Config:
    """加载配置；支持 KE_CONFIG 与 I8 runtime 显式环境覆盖。"""
    if path is None:
        env = os.environ.get("KE_CONFIG")
        if env:
            path = env
    if path is None:
        candidates = [CONFIG_DIR / "config.yaml", CONFIG_DIR / "config.example.yaml"]
        for c in candidates:
            if c.exists():
                path = c
                break
    if path is None or not Path(path).exists():
        return _apply_runtime_env_overrides(Config())
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return _apply_runtime_env_overrides(Config.model_validate(data))


SCHEMA_VERSION = "1.0.0"
LEXICAL_VERSION = "4.0.0"
