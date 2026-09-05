from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.index import VectorSyncBody, cognition_vector_sync, vector_sync
from app.api.search import SearchOptions, SearchRequest, cognition_search, search
from app.indexing import semantic_runtime


class FakeCatalog:
    def __init__(self, pending=None):
        self._pending = list(pending or [])
        self.cleared = []

    def pending_vector_sync(self):
        return list(self._pending)

    def clear_vector_pending(self, doc_id):
        self.cleared.append(doc_id)
        self._pending = [x for x in self._pending if x["document_id"] != doc_id]


class FakeSemantic:
    def __init__(self):
        self.indexed = []
        self.deleted = []

    def index_file(self, source_path, *, doc_id=None):
        self.indexed.append((source_path, doc_id))
        return {"document_id": doc_id}

    def remove_document(self, doc_id, source_path):
        self.deleted.append((doc_id, source_path))


class FakeSearchEngine:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {"mode": kwargs["mode"], "results": []}


def _app_state(**kwargs):
    defaults = {
        "cfg": SimpleNamespace(),
        "conn": object(),
        "manager": object(),
        "pipeline": None,
        "qdrant_available": False,
        "semantic_last_error": None,
        "catalog_pipeline": FakeCatalog(),
        "index_lock": __import__("threading").Lock(),
        "engine": FakeSearchEngine(),
        "cognition": {"enabled": False},
    }
    defaults.update(kwargs)
    return SimpleNamespace(state=SimpleNamespace(**defaults))


def _request(app):
    return SimpleNamespace(app=app)


def test_report_semantic_recovery_can_succeed_after_initial_failure(monkeypatch):
    app = _app_state()
    semantic = FakeSemantic()
    attempts = []

    def build(_app):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("qdrant down")
        return semantic

    monkeypatch.setattr(semantic_runtime, "_build_report_pipeline", build)

    assert semantic_runtime.ensure_report_semantic(app) is False
    assert app.state.pipeline is None
    assert app.state.qdrant_available is False
    assert "qdrant down" in app.state.semantic_last_error

    assert semantic_runtime.ensure_report_semantic(app) is True
    assert app.state.pipeline is semantic
    assert app.state.qdrant_available is True
    assert app.state.semantic_last_error is None

    assert semantic_runtime.ensure_report_semantic(app) is True
    assert len(attempts) == 2


def test_cognition_semantic_recovery_can_succeed_after_initial_failure(monkeypatch):
    semantic = FakeSemantic()
    cog = {
        "enabled": True,
        "conn": object(),
        "semantic_pipeline": None,
        "semantic_available": False,
    }
    app = _app_state(cognition=cog)
    attempts = []

    def build(_app, received_cog):
        assert received_cog is cog
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("cognition collection unavailable")
        return semantic

    monkeypatch.setattr(semantic_runtime, "_build_cognition_pipeline", build)

    assert semantic_runtime.ensure_cognition_semantic(app) is False
    assert cog["semantic_pipeline"] is None
    assert cog["semantic_available"] is False
    assert "collection unavailable" in cog["semantic_last_error"]

    assert semantic_runtime.ensure_cognition_semantic(app) is True
    assert cog["semantic_pipeline"] is semantic
    assert cog["semantic_available"] is True
    assert cog["semantic_last_error"] is None

    assert semantic_runtime.ensure_cognition_semantic(app) is True
    assert len(attempts) == 2


def test_report_dense_search_recovers_semantic_runtime(monkeypatch):
    engine = FakeSearchEngine()
    app = _app_state(engine=engine)

    def recover(received_app):
        assert received_app is app
        app.state.qdrant_available = True
        app.state.pipeline = object()
        return True

    monkeypatch.setattr("app.api.search.ensure_report_semantic", recover)
    monkeypatch.setattr("app.api.search._record_impressions", lambda *_args, **_kwargs: None)

    response = search(
        SearchRequest(query="recover-report", options=SearchOptions(mode="dense")),
        _request(app),
    )

    assert response["mode"] == "dense"
    assert engine.calls[0][0] == "recover-report"
    assert app.state.qdrant_available is True


def test_cognition_dense_search_recovers_semantic_runtime(monkeypatch):
    engine = FakeSearchEngine()
    cog = {
        "enabled": True,
        "engine": engine,
        "semantic_pipeline": None,
        "semantic_available": False,
    }
    app = _app_state(cognition=cog)

    def recover(received_app):
        assert received_app is app
        cog["semantic_pipeline"] = object()
        cog["semantic_available"] = True
        return True

    monkeypatch.setattr("app.api.search.ensure_cognition_semantic", recover)

    response = cognition_search(
        SearchRequest(query="recover-cognition", options=SearchOptions(mode="hybrid")),
        _request(app),
    )

    assert response["mode"] == "hybrid"
    assert response["scope"] == "cognition"
    assert engine.calls[0][0] == "recover-cognition"
    assert cog["semantic_available"] is True


def test_report_vector_sync_recovers_semantic_runtime_and_clears_pending(monkeypatch):
    catalog = FakeCatalog(
        [{"document_id": "R1", "operation": "upsert", "source_path": "R1.md"}]
    )
    app = _app_state(catalog_pipeline=catalog)
    semantic = FakeSemantic()

    def recover(received_app):
        assert received_app is app
        app.state.pipeline = semantic
        app.state.qdrant_available = True
        return True

    monkeypatch.setattr("app.api.index.ensure_report_semantic", recover)

    result = vector_sync(VectorSyncBody(limit=20), _request(app))

    assert result == {
        "requested": 1,
        "synced": 1,
        "failed": 0,
        "remaining": 0,
        "errors": [],
    }
    assert semantic.indexed == [("R1.md", "R1")]
    assert catalog.cleared == ["R1"]


def test_report_vector_sync_keeps_pending_when_recovery_fails(monkeypatch):
    catalog = FakeCatalog(
        [{"document_id": "R1", "operation": "upsert", "source_path": "R1.md"}]
    )
    app = _app_state(catalog_pipeline=catalog)
    monkeypatch.setattr("app.api.index.ensure_report_semantic", lambda _app: False)

    with pytest.raises(HTTPException) as exc_info:
        vector_sync(VectorSyncBody(limit=20), _request(app))

    assert exc_info.value.status_code == 503
    assert catalog.pending_vector_sync()[0]["document_id"] == "R1"
    assert catalog.cleared == []


def test_cognition_vector_sync_recovers_semantic_runtime(monkeypatch):
    catalog = FakeCatalog(
        [{"document_id": "cog:stable", "operation": "upsert", "source_path": "renamed.md"}]
    )
    cog = {
        "enabled": True,
        "catalog_pipeline": catalog,
        "semantic_pipeline": None,
        "semantic_available": False,
        "conn": object(),
    }
    app = _app_state(cognition=cog)
    semantic = FakeSemantic()

    def recover(received_app):
        assert received_app is app
        cog["semantic_pipeline"] = semantic
        cog["semantic_available"] = True
        return True

    monkeypatch.setattr("app.api.index.ensure_cognition_semantic", recover)

    result = cognition_vector_sync(VectorSyncBody(limit=20), _request(app))

    assert result["synced"] == 1
    assert result["remaining"] == 0
    assert semantic.indexed == [("renamed.md", "cog:stable")]
    assert catalog.cleared == ["cog:stable"]
