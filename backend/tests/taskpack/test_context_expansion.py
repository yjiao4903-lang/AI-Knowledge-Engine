"""P1 Evidence Context Expansion deterministic contract tests."""

from __future__ import annotations

import json

import pytest
import yaml

from app.synthesis.schemas import EvidenceRef, SynthesisRequest
from tests.synthesis.helpers import seed_chunk


def _rows(created) -> list[dict]:
    return [
        json.loads(line)
        for line in (created.task_path / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _create(env, ref: EvidenceRef, mode: str = "none"):
    return env["builder"].create_task(
        task_type="causal_synthesis",
        query=f"context expansion {mode}",
        evidence_refs=[ref],
        evidence_context_mode=mode,
    )


def test_request_defaults_to_no_context_expansion(tk_env):
    request = SynthesisRequest(
        task_type="summary",
        query="test",
        evidence_refs=[tk_env["refs"][0]],
    )
    assert request.evidence_context_mode == "none"


def test_none_keeps_only_selected_anchor(tk_env):
    created = _create(tk_env, tk_env["refs"][0], "none")
    rows = _rows(created)

    assert created.evidence_count == 1
    assert [row["chunk_id"] for row in rows] == ["M04:ch1:0001"]
    task = yaml.safe_load((created.task_path / "task.yaml").read_text(encoding="utf-8"))
    assert task["evidence_context_mode"] == "none"


def test_neighbor_1_adds_immediate_previous_and_next_chunks(tk_env):
    hc = seed_chunk(
        tk_env["conn"],
        "M04:ch1:0003",
        "第三段用于验证邻接上下文。",
        doc_id="M04",
    )
    middle = EvidenceRef(
        source_type="report",
        document_id="M04",
        chunk_id="M04:ch1:0002",
        content_hash=tk_env["hashes"][1],
    )

    created = _create(tk_env, middle, "neighbor_1")
    chunk_ids = [row["chunk_id"] for row in _rows(created)]

    assert hc
    assert chunk_ids == ["M04:ch1:0001", "M04:ch1:0002", "M04:ch1:0003"]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_section_expands_to_all_chunks_in_anchor_section(tk_env):
    created = _create(tk_env, tk_env["refs"][0], "section")
    chunk_ids = [row["chunk_id"] for row in _rows(created)]

    assert chunk_ids == ["M04:ch1:0001", "M04:ch1:0002"]
    assert all(row["section_id"] == "M04:ch1" for row in _rows(created))
    task = yaml.safe_load((created.task_path / "task.yaml").read_text(encoding="utf-8"))
    assert task["evidence_context_mode"] == "section"


def test_overlapping_context_is_deduplicated_by_chunk_id(tk_env):
    created = tk_env["builder"].create_task(
        task_type="comparison",
        query="dedupe context",
        evidence_refs=tk_env["refs"],
        evidence_context_mode="neighbor_1",
    )
    chunk_ids = [row["chunk_id"] for row in _rows(created)]

    assert chunk_ids == ["M04:ch1:0001", "M04:ch1:0002"]
    assert created.evidence_count == 2


def test_expansion_respects_taskpack_max_evidence_without_truncation(tk_env):
    tk_env["cfg"].taskpack.max_evidence = 1

    with pytest.raises(ValueError, match="Evidence Context Expansion"):
        _create(tk_env, tk_env["refs"][0], "neighbor_1")

    assert list((tk_env["root"] / "outbox").iterdir()) == []


def test_expanded_rows_keep_independent_citation_identity(tk_env):
    created = _create(tk_env, tk_env["refs"][0], "section")
    rows = _rows(created)

    assert [row["evidence_id"] for row in rows] == ["EV001", "EV002"]
    assert [row["chunk_id"] for row in rows] == ["M04:ch1:0001", "M04:ch1:0002"]
    assert all(row["content_hash"] for row in rows)
    assert all(isinstance(row["excerpt"], str) and row["excerpt"] for row in rows)

    manifest = json.loads((created.task_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence_count"] == 2


def test_invalid_context_mode_is_rejected_by_request_schema(tk_env):
    with pytest.raises(Exception):
        SynthesisRequest(
            task_type="summary",
            query="test",
            evidence_refs=[tk_env["refs"][0]],
            evidence_context_mode="whole_document",
        )
