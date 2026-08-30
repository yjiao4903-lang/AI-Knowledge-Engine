"""错误分类（spec §46）。所有错误必须显式分类，禁止静默 except。"""

from __future__ import annotations


class AppError(Exception):
    code = "APP_ERROR"
    http_status = 400  # 服务故障类子类覆盖为 503（I0 Error Model）

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


class ConfigError(AppError):
    code = "CONFIG_ERROR"


class SourceFileError(AppError):
    code = "SOURCE_FILE_ERROR"


class MarkdownParseError(AppError):
    code = "MARKDOWN_PARSE_ERROR"


class SqliteError(AppError):
    code = "SQLITE_ERROR"
    http_status = 503  # RETRIEVAL_UNAVAILABLE（Integration Contract V1）


class QdrantError(AppError):
    code = "QDRANT_ERROR"
    http_status = 503  # RETRIEVAL_UNAVAILABLE（Integration Contract V1）


class GpuError(AppError):
    code = "GPU_ERROR"
    http_status = 503  # RETRIEVAL_UNAVAILABLE（Integration Contract V1）


class EmbeddingError(AppError):
    code = "EMBEDDING_ERROR"
    http_status = 503  # RETRIEVAL_UNAVAILABLE（Integration Contract V1）


class RerankError(AppError):
    code = "RERANK_ERROR"


class IndexInconsistencyError(AppError):
    code = "INDEX_INCONSISTENCY"


class ApiValidationError(AppError):
    code = "API_VALIDATION_ERROR"


# ---- L1 Synthesis（证据定位与校验；生成已改为 TaskPack 外部 Worker，V3.0）----
class EvidenceNotFoundError(AppError):
    code = "EVIDENCE_NOT_FOUND"
    http_status = 404


class EvidenceStaleError(AppError):
    """content_hash 不一致：引用时与当前 catalog 不同（契约 §3）。"""

    code = "EVIDENCE_STALE"
    http_status = 409
