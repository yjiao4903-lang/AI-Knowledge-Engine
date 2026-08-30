"""Grounding：证据解析与引用合法性（主计划 §9/§10）。"""

from __future__ import annotations

import pytest

from app.core.errors import EvidenceNotFoundError, EvidenceStaleError
from app.synthesis.grounding import EvidenceResolver, provided_chunk_ids
from app.synthesis.schemas import EvidenceRef

from tests.synthesis.helpers import seed_chunk


def _ref(chunk_id, *, hash_=None):
    return EvidenceRef(source_type="report", document_id="M04", chunk_id=chunk_id, content_hash=hash_)


def test_resolve_loads_catalog_text(seeded):
    resolver = seeded["resolver"]
    refs = [_ref(c) for c in seeded["chunk_ids"]]
    resolved = resolver.resolve(refs, evidence_max_chars=5000)
    assert len(resolved) == 2
    assert resolved[0].ref_id == "E1"
    assert resolved[0].chunk_id == "M04:ch1:0001"
    # 正文应来自 catalog，而不是客户端 excerpt
    assert "HBM4 的接口位宽" in resolved[0].excerpt


def test_provided_chunk_ids(seeded):
    resolver = seeded["resolver"]
    resolved = resolver.resolve([_ref(c) for c in seeded["chunk_ids"]])
    assert provided_chunk_ids(resolved) == set(seeded["chunk_ids"])


def test_not_found(seeded):
    resolver = seeded["resolver"]
    with pytest.raises(EvidenceNotFoundError):
        resolver.resolve([_ref("M04:ch1:9999")])


def test_stale_hash(seeded):
    resolver = seeded["resolver"]
    with pytest.raises(EvidenceStaleError):
        resolver.resolve([_ref(seeded["chunk_ids"][0], hash_="wronghash")])


def test_truncation(seeded):
    resolver = seeded["resolver"]
    resolved = resolver.resolve([_ref(seeded["chunk_ids"][0])], evidence_max_chars=10)
    assert len(resolved[0].excerpt) == 10


def test_max_evidence_limit(seeded):
    conn, doc = seeded["conn"], "M04"
    seed_chunk(conn, "M04:ch1:0101", "x" * 100, doc_id=doc)
    seed_chunk(conn, "M04:ch1:0102", "y" * 100, doc_id=doc)
    resolver = seeded["resolver"]
    refs = [_ref(c) for c in ["M04:ch1:0001", "M04:ch1:0002", "M04:ch1:0101", "M04:ch1:0102"]]
    resolved = resolver.resolve(refs, max_evidence=3)
    assert len(resolved) == 3
    assert resolved[-1].chunk_id == "M04:ch1:0101"


def test_cognition_prefix_routes_to_cog_repo(seeded):
    from tests.synthesis.helpers import seed_doc

    cfg = seeded["cfg"]
    conn = seeded["conn"]
    seed_doc(conn, "cog:j1", title="认知研判")
    seed_chunk(conn, "cog:04_judgment:0001", "认知研判内容" * 5, doc_id="cog:j1")
    resolver = EvidenceResolver(cfg, conn, conn)  # 两库都给同一 conn（测试）
    r = resolver.resolve([_ref("cog:04_judgment:0001")])
    assert "认知研判" in r[0].excerpt


def test_cog_repo_missing_when_cognition_conn_none(seeded):
    resolver = seeded["resolver"]  # cognition_conn=None
    with pytest.raises(EvidenceNotFoundError):
        resolver.resolve([_ref("cog:04_judgment:0001")])