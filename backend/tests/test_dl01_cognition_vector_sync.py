from threading import Lock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.index import VectorSyncBody, cognition_index_status, cognition_vector_sync


class FakeCatalog:
    def __init__(self, pending):
        self._pending = [dict(item) for item in pending]
        self.cleared = []

    def pending_vector_sync(self):
        return [dict(item) for item in self._pending]

    def clear_vector_pending(self, document_id):
        self.cleared.append(document_id)
        self._pending = [
            item for item in self._pending if item["document_id"] != document_id
        ]


class FakeSemantic:
    def __init__(self, *, mismatch_id=None):
        self.mismatch_id = mismatch_id
        self.index_calls = []
        self.remove_calls = []

    def index_file(self, source_path, *, doc_id=None):
        self.index_calls.append((source_path, doc_id))
        return {"document_id": self.mismatch_id or doc_id}

    def remove_document(self, doc_id, source_path):
        self.remove_calls.append((doc_id, source_path))


def _request(catalog, semantic=None, *, semantic_available=True, enabled=True):
    cognition = {
        "enabled": enabled,
        "semantic_available": semantic_available,
        "catalog_pipeline": catalog,
        "semantic_pipeline": semantic,
    }
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(cognition=cognition, index_lock=Lock())
        )
    )


def test_cognition_status_exposes_lexical_semantic_and_pending_separately():
    catalog = FakeCatalog(
        [
            {"document_id": "cog:03_问题池/a", "operation": "upsert"},
            {"document_id": "cog:04_判断台账/b", "operation": "delete"},
        ]
    )
    response = cognition_index_status(
        _request(catalog, semantic=None, semantic_available=False)
    )

    assert response == {
        "enabled": True,
        "lexical_available": True,
        "semantic_available": False,
        "vector_pending": 2,
        "vector_pending_documents": [
            "cog:03_问题池/a",
            "cog:04_判断台账/b",
        ],
    }


def test_cognition_vector_sync_uses_catalog_stable_id_for_upsert_and_delete():
    stable_id = "cog:03_问题池/变压器问题"
    renamed_path = "D:/cognition/03_问题池/变压器问题_重命名.md"
    deleted_id = "cog:04_判断台账/旧判断"
    deleted_path = "D:/cognition/04_判断台账/旧判断.md"
    catalog = FakeCatalog(
        [
            {
                "document_id": stable_id,
                "operation": "upsert",
                "source_path": renamed_path,
            },
            {
                "document_id": deleted_id,
                "operation": "delete",
                "source_path": deleted_path,
            },
        ]
    )
    semantic = FakeSemantic()

    response = cognition_vector_sync(
        VectorSyncBody(limit=20), _request(catalog, semantic)
    )

    assert response == {
        "requested": 2,
        "synced": 2,
        "failed": 0,
        "remaining": 0,
        "errors": [],
    }
    assert semantic.index_calls == [(renamed_path, stable_id)]
    assert semantic.remove_calls == [(deleted_id, deleted_path)]
    assert catalog.cleared == [stable_id, deleted_id]


def test_cognition_vector_sync_preserves_pending_when_semantic_unavailable():
    stable_id = "cog:03_问题池/未同步问题"
    catalog = FakeCatalog(
        [
            {
                "document_id": stable_id,
                "operation": "upsert",
                "source_path": "D:/cognition/03_问题池/未同步问题.md",
            }
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        cognition_vector_sync(
            VectorSyncBody(),
            _request(catalog, semantic=None, semantic_available=False),
        )

    assert exc_info.value.status_code == 503
    assert "lexical" in str(exc_info.value.detail)
    assert catalog.cleared == []
    assert [item["document_id"] for item in catalog.pending_vector_sync()] == [stable_id]


def test_cognition_vector_sync_rejects_semantic_document_id_drift():
    stable_id = "cog:03_问题池/rename-stable-id"
    catalog = FakeCatalog(
        [
            {
                "document_id": stable_id,
                "operation": "upsert",
                "source_path": "D:/cognition/03_问题池/rename-new-path.md",
            }
        ]
    )
    semantic = FakeSemantic(mismatch_id="cog:03_问题池/rename-new-path")

    response = cognition_vector_sync(
        VectorSyncBody(), _request(catalog, semantic)
    )

    assert response["requested"] == 1
    assert response["synced"] == 0
    assert response["failed"] == 1
    assert response["remaining"] == 1
    assert "document_id mismatch" in response["errors"][0]["error"]
    assert catalog.cleared == []
    assert semantic.index_calls == [
        ("D:/cognition/03_问题池/rename-new-path.md", stable_id)
    ]
