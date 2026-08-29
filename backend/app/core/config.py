"""配置加载（M1-02）。

以 config/config.yaml 为准（不存在时回退 config.example.yaml），
全部参数可用 pydantic 模型校验与默认值兜底。
"""

from __future__ import annotations

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


class IndexingConfig(BaseModel):
    startup_scan: bool = True
    periodic_reconcile_seconds: int = 300
    watcher_enabled: bool = True


class InferenceConfig(BaseModel):
    """显式推理设备配置（Addendum §17）。

    优先级：force_device > preferred_gpu_name > 最大显存 > CPU fallback。
    """

    preferred_device: str = "auto"  # auto | cpu
    preferred_gpu_name: str = "RX 7900 XTX"
    force_device: str | None = None  # 如 "cuda:1"


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    knowledge_base: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    sqlite: SqliteConfig = Field(default_factory=SqliteConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)


def load_config(path: str | Path | None = None) -> Config:
    """加载配置；path 缺省时依次尝试 config/config.yaml 与 config.example.yaml。"""
    if path is None:
        candidates = [CONFIG_DIR / "config.yaml", CONFIG_DIR / "config.example.yaml"]
        for c in candidates:
            if c.exists():
                path = c
                break
    if path is None or not Path(path).exists():
        return Config()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Config.model_validate(data)


# 版本常量（写入 meta 表，供 reindex 判断，见 spec §48）
SCHEMA_VERSION = "1.0.0"
LEXICAL_VERSION = "4.0.0"  # M4: NFKC + identifier 保护 + jieba + tech_terms
