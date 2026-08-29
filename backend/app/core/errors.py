"""错误分类（spec §46）。所有错误必须显式分类，禁止静默 except。"""

from __future__ import annotations


class AppError(Exception):
    code = "APP_ERROR"

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


class QdrantError(AppError):
    code = "QDRANT_ERROR"


class GpuError(AppError):
    code = "GPU_ERROR"


class EmbeddingError(AppError):
    code = "EMBEDDING_ERROR"


class RerankError(AppError):
    code = "RERANK_ERROR"


class IndexInconsistencyError(AppError):
    code = "INDEX_INCONSISTENCY"


class ApiValidationError(AppError):
    code = "API_VALIDATION_ERROR"
