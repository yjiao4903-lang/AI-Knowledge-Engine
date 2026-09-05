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
