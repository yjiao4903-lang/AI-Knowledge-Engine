"""P1 Personal Retrieval Feedback deterministic contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.search import (
    RetrievalFeedbackBatch,
    RetrievalFeedbackEvent,
    SearchOptions,
    SearchRequest,
    _record_impressions,
)
from app.retrieval.feedback import (
    FEEDBACK_SCHEMA_VERSION,
    append_feedback_events,
    build_impression_events,
    feedback_path,
)


def _event(**overrides):
    payload = {
        "search_id": "search-1",
        "query": "HBM4 接口位宽",
        "chunk_id": "M04:ch1:0001",
        "document_id": "M04",
        "rank": 1,
        "mode": "lexical",
        "rerank": False,
        "event_type": "useful",
        "useful": True,
        "selected_as_evidence": False,
    }
    payload.update(overrides)
    return payload


def test_feedback_ledger_is_append_only_jsonl(tmp_path):
    path = feedback_path(tmp_path)
    assert append_feedback_events(path, [_event()]) == 1
    assert append_feedback_events(
        path,
        [_event(search_id="search-2", event_type="evidence_select", selected_as_evidence=True)],
    ) == 1

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["search_id"] == "search-1"
    assert rows[1]["search_id"] == "search-2"
    assert all(row["schema_version"] == FEEDBACK_SCHEMA_VERSION for row in rows)
    assert all(row["timestamp"].endswith("+00:00") for row in rows)


def test_impression_builder_records_rank_mode_without_inventing_labels():
    events = build_impression_events(
        search_id="run-1",
        query="AI capex",
        mode="hybrid",
        rerank=True,
        results=[
            {"rank": 1, "chunk_id": "c1", "document_id": "d1"},
            {"rank": 2, "chunk_id": "c2", "document_id": "d2"},
        ],
    )

    assert [event["rank"] for event in events] == [1, 2]
    assert all(event["mode"] == "hybrid" for event in events)
    assert all(event["rerank"] is True for event in events)
    assert all(event["event_type"] == "impression" for event in events)
    assert all(event["useful"] is None for event in events)
    assert all(event["selected_as_evidence"] is None for event in events)


def test_record_impressions_annotates_results_and_writes_local_ledger(tmp_path):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                cfg=SimpleNamespace(paths=SimpleNamespace(data_dir=str(tmp_path)))
            )
        )
    )
    body = SearchRequest(
        query="HBM4",
        options=SearchOptions(mode="lexical", rerank=False, top_k=10),
    )
    response = {
        "mode": "lexical",
        "results": [
            {"rank": 1, "chunk_id": "c1", "document_id": "d1"},
            {"rank": 2, "chunk_id": "c2", "document_id": "d2"},
        ],
    }

    _record_impressions(request, body, response)

    search_id = response["search_id"]
    assert search_id
    assert all(result["search_id"] == search_id for result in response["results"])
    assert all(result["search_mode"] == "lexical" for result in response["results"])
    assert all(result["rerank_enabled"] is False for result in response["results"])

    rows = [
        json.loads(line)
        for line in feedback_path(tmp_path).read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert all(row["search_id"] == search_id for row in rows)


def test_action_contract_requires_explicit_action_value():
    with pytest.raises(ValidationError):
        RetrievalFeedbackEvent(**_event(useful=None))

    with pytest.raises(ValidationError):
        RetrievalFeedbackEvent(
            **_event(
                event_type="evidence_select",
                useful=None,
                selected_as_evidence=None,
            )
        )

    item = RetrievalFeedbackEvent(
        **_event(event_type="evidence_remove", useful=None, selected_as_evidence=False)
    )
    assert item.selected_as_evidence is False


def test_feedback_batch_is_bounded_to_search_top_k_limit():
    RetrievalFeedbackBatch(events=[RetrievalFeedbackEvent(**_event())])

    with pytest.raises(ValidationError):
        RetrievalFeedbackBatch(
            events=[
                RetrievalFeedbackEvent(**_event(search_id=f"search-{index}"))
                for index in range(51)
            ]
        )
