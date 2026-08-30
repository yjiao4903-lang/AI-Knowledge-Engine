"""Service 编排：resolve→prompt→provider(retry/fallback)→validate→log（主计划 §38）。"""

from __future__ import annotations

import json

import pytest

from app.core.config import SynthesisConfig
from app.core.errors import SynthesisInvalidError, SynthesisUnavailableError
from app.synthesis.provider import MockProvider, SynthesisProvider
from app.synthesis.service import SynthesisService, _parse_json
from app.synthesis.schemas import SynthesisRequest, EvidenceRef

from tests.synthesis.conftest import NoopResolver


def _req(chunk_ids):
    return SynthesisRequest(
        task_type="summary", query="HBM4 位宽综合",
        evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id=id_)
                       for id_ in chunk_ids],
    )


def test_mock_end_to_end(seeded):
    cfg, resolver = seeded["cfg"], seeded["resolver"]
    svc = SynthesisService(cfg, MockProvider(cfg.synthesis), resolver)
    draft = svc.synthesize(_req(seeded["chunk_ids"]))
    assert draft.schema_version == "1.0"
    assert draft.status == "draft"
    assert len(draft.evidence) == 2
    assert draft.claims[0].evidence_refs  # 绑定证据
    assert draft.claims[0].evidence_refs[0] in set(seeded["chunk_ids"])
    assert draft.generator.provider == "mock"


def test_evidence_not_found_aborts(seeded):
    cfg, resolver = seeded["cfg"], seeded["resolver"]
    svc = SynthesisService(cfg, MockProvider(cfg.synthesis), resolver)
    from app.core.errors import EvidenceNotFoundError
    with pytest.raises(EvidenceNotFoundError):
        svc.synthesize(_req(["M04:ch1:0001", "M04:ch1:NOPE"]))


def test_fallback_model_when_primary_unavailable():
    class FlakyProvider(SynthesisProvider):
        provider_name = "flaky"
        def chat(self, messages, *, model=None):
            if model == "primary-model":
                raise SynthesisUnavailableError("primary down")
            return json.dumps({"claims": [
                {"id": "claim_001", "text": "fallback ok", "epistemic_state": "supported",
                 "evidence_refs": ["E1"]}],
                "tensions": [], "uncertainties": [], "open_questions": [], "summary": "s"})

    cfg = SynthesisConfig(model="primary-model", fallback_model="fallback-model")
    # 最小 resolver（无库）：由 flaky provider 直接返回内容
    svc = SynthesisService(cfg, FlakyProvider(cfg), NoopResolver())
    draft = svc.synthesize(SynthesisRequest(
        task_type="summary", query="q",
        evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id="E1")]),
    )
    assert draft.generator.model == "fallback-model"
    assert draft.claims[0].evidence_refs == ["E1"]


def test_unavailable_when_all_models_fail():
    class DownProvider(SynthesisProvider):
        provider_name = "down"
        def chat(self, messages, *, model=None):
            raise SynthesisUnavailableError("down")
        def is_available(self):
            return False

    cfg = SynthesisConfig(model="a", fallback_model="b")
    svc = SynthesisService(cfg, DownProvider(cfg), NoopResolver())
    with pytest.raises(SynthesisUnavailableError):
        svc.synthesize(SynthesisRequest(
            task_type="summary", query="q",
            evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id="E1")]),
        )


def test_invalid_json_after_retries_raises():
    class GarbageProvider(SynthesisProvider):
        provider_name = "garbage"
        def chat(self, messages, *, model=None):
            return "not json at all"

    cfg = SynthesisConfig(model="a", fallback_model="")
    svc = SynthesisService(cfg, GarbageProvider(cfg), NoopResolver())
    with pytest.raises(SynthesisUnavailableError):
        svc.synthesize(SynthesisRequest(
            task_type="summary", query="q",
            evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id="E1")]),
        )


def test_invalid_schema_after_retries_wrapped():
    class BadSchemaProvider(SynthesisProvider):
        provider_name = "badschema"
        def chat(self, messages, *, model=None):
            return json.dumps({"claims": [{"id": "c1", "text": "x",
                                           "epistemic_state": "bad_state", "evidence_refs": []}],
                               "tensions": [], "uncertainties": [], "open_questions": [],
                               "summary": "s"})

    cfg = SynthesisConfig(model="a", fallback_model="")
    svc = SynthesisService(cfg, BadSchemaProvider(cfg), NoopResolver())
    with pytest.raises(SynthesisInvalidError):
        svc.synthesize(SynthesisRequest(
            task_type="summary", query="q",
            evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id="E1")]),
        )


def test_invalid_citation_retries_then_recovers():
    calls = {"n": 0}

    class HealingProvider(SynthesisProvider):
        provider_name = "healing"
        def chat(self, messages, *, model=None):
            calls["n"] += 1
            refs = ["bogus:ref:9999"] if calls["n"] == 1 else ["E1"]
            return json.dumps({"claims": [
                {"id": "claim_001", "text": "x", "epistemic_state": "supported",
                 "evidence_refs": refs}],
                "tensions": [], "uncertainties": [], "open_questions": [], "summary": "s"})

    cfg = SynthesisConfig(model="a", fallback_model="", max_invalid_retries=1)
    svc = SynthesisService(cfg, HealingProvider(cfg), NoopResolver())
    draft = svc.synthesize(SynthesisRequest(
        task_type="summary", query="q",
        evidence_refs=[EvidenceRef(source_type="report", document_id="M04", chunk_id="E1")]),
    )
    assert calls["n"] == 2
    assert draft.claims[0].evidence_refs == ["E1"]


def test_parse_json_strips_fence():
    ok = _parse_json("```json\n{\"a\": 1}\n```")
    assert ok == {"a": 1}
    ok2 = _parse_json('前后文字 {"a":1} 结尾')
    assert ok2 == {"a": 1}
    assert _parse_json("not json") is None
    assert _parse_json("") is None