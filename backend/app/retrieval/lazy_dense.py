"""Lazy dense retrieval adapter for the no-model base runtime.

The base Research OS path is lexical-first. Importing or starting the backend must
not load the local embedding model just because dense retrieval is configured.
The real DenseRetriever is therefore constructed only when an explicit
``dense``/``hybrid`` search reaches this adapter.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.core.config import Config
from app.core.errors import EmbeddingError


class LazyDenseRetriever:
    """Construct ``DenseRetriever`` on first semantic-search use.

    ``factory`` is injectable so the lazy boundary can be tested without
    importing torch/transformers or contacting Qdrant.
    """

    def __init__(
        self,
        cfg: Config,
        *,
        factory: Callable[[Config], Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self._factory = factory
        self._instance: Any | None = None
        self._lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        return self._instance is not None

    def _build(self) -> Any:
        factory = self._factory
        if factory is None:
            # Keep the heavyweight embedding stack out of the base import/startup
            # path. DenseRetriever imports torch/transformers through its provider.
            from app.retrieval.dense import DenseRetriever

            factory = DenseRetriever
        try:
            return factory(self.cfg)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"语义检索模型初始化失败: {exc}") from exc

    def _get(self) -> Any:
        if self._instance is not None:
            return self._instance
        with self._lock:
            if self._instance is None:
                self._instance = self._build()
        return self._instance

    def search(self, *args: Any, **kwargs: Any):
        return self._get().search(*args, **kwargs)
