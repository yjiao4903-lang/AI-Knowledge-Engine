import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.api.search import SearchOptions
from app.core.errors import EmbeddingError
from app.retrieval.lazy_dense import LazyDenseRetriever


def test_backend_search_defaults_to_lexical_without_rerank():
    options = SearchOptions()

    assert options.mode == "lexical"
    assert options.rerank is False


def test_lazy_dense_does_not_construct_backend_until_explicit_search():
    cfg = SimpleNamespace()
    created = []

    class FakeDense:
        def search(self, query, **kwargs):
            return ([{"payload": {"chunk_id": query}}], 0.0)

    def factory(received_cfg):
        created.append(received_cfg)
        return FakeDense()

    lazy = LazyDenseRetriever(cfg, factory=factory)

    assert lazy.initialized is False
    assert created == []

    hits, embed_ms = lazy.search("semantic-query", k=1)

    assert lazy.initialized is True
    assert created == [cfg]
    assert hits[0]["payload"]["chunk_id"] == "semantic-query"
    assert embed_ms == 0.0

    lazy.search("second-query", k=1)
    assert created == [cfg]


def test_lazy_dense_reports_model_initialization_failure_as_embedding_unavailable():
    cfg = SimpleNamespace()

    def broken_factory(_cfg):
        raise FileNotFoundError("model files missing")

    lazy = LazyDenseRetriever(cfg, factory=broken_factory)

    with pytest.raises(EmbeddingError, match="语义检索模型初始化失败"):
        lazy.search("query", k=1)

    assert lazy.initialized is False


def test_base_app_import_does_not_require_qdrant_client():
    """The lexical base process must import even when Qdrant SDK is unavailable."""

    code = r'''
import importlib.abc
import sys

class BlockQdrant(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "qdrant_client" or fullname.startswith("qdrant_client."):
            raise ImportError("qdrant_client intentionally blocked for DL-01 base-runtime test")
        return None

sys.meta_path.insert(0, BlockQdrant())
import app.main
print("BASE_IMPORT_OK")
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "BASE_IMPORT_OK" in result.stdout
