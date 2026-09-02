import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import research_os
from app.core.config import load_config
from app.integration.cognition_gateway import CognitionGateway, PublishedProposal


def _request(tmp_path: Path):
    cognition = SimpleNamespace(
        proposal_publish_enabled=True,
        api_url="http://127.0.0.1:3220/api",
        api_timeout_seconds=1.0,
    )
    cfg = SimpleNamespace(cognition=cognition)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cfg=cfg)))


def test_gateway_has_no_formal_apply_surface():
    gateway = CognitionGateway("http://127.0.0.1:3220/api")
    assert not hasattr(gateway, "apply_proposal")
    assert not hasattr(gateway, "merge")
    assert not hasattr(gateway, "revise_judgment")


def test_gateway_create_proposal_uses_staging_endpoint(monkeypatch):
    gateway = CognitionGateway("http://127.0.0.1:3220/api")
    calls = []

    def fake_request(method, path, *, json_body=None):
        calls.append((method, path, json_body))
        return {"ok": True, "item": {"id": "proposal-001"}}

    monkeypatch.setattr(gateway, "_request", fake_request)
    published = gateway.create_proposal({"title": "candidate", "items": []})

    assert published.proposal_id == "proposal-001"
    assert calls == [
        ("POST", "/proposals", {"title": "candidate", "items": []})
    ]


def test_publish_proposal_is_idempotent_and_writes_local_marker(tmp_path, monkeypatch):
    pack = tmp_path / "task_001"
    (pack / "result").mkdir(parents=True)
    request = _request(tmp_path)

    monkeypatch.setattr(research_os, "_require_task", lambda _request, _task_id: (pack, object()))
    candidates_calls = []

    def fake_candidates(task_id, _request):
        candidates_calls.append(task_id)
        return {
            "proposal_payload": {
                "title": "TaskPack result",
                "origin_type": "external_llm",
                "origin_ref": task_id,
                "origin_title": "query",
                "generator": "codex:gpt",
                "description": "summary",
                "topics": [],
                "items": [{"candidate_type": "new_judgment", "sections": {"内容": "x"}}],
            },
            "warnings": [],
        }

    monkeypatch.setattr(research_os, "get_proposal_candidates", fake_candidates)

    class FakeGateway:
        calls = 0

        def create_proposal(self, payload):
            self.calls += 1
            return PublishedProposal(
                proposal_id="proposal-001",
                raw={"ok": True, "item": {"id": "proposal-001"}},
            )

    gateway = FakeGateway()
    monkeypatch.setattr(research_os, "_gateway", lambda _request: gateway)

    first = research_os.publish_proposal(
        "task_001", request, research_os.PublishProposalRequest(force=False)
    )
    assert first["published"] is True
    assert first["reused"] is False
    assert first["publication"]["proposal_id"] == "proposal-001"
    assert first["auto_apply"] is False
    assert gateway.calls == 1
    assert candidates_calls == ["task_001"]

    marker_path = pack / "result" / "proposal_publish.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["proposal_id"] == "proposal-001"
    assert marker["auto_apply"] is False

    second = research_os.publish_proposal(
        "task_001", request, research_os.PublishProposalRequest(force=False)
    )
    assert second["reused"] is True
    assert second["publication"]["proposal_id"] == "proposal-001"
    assert gateway.calls == 1
    assert candidates_calls == ["task_001"]


def test_publish_proposal_can_be_disabled(tmp_path, monkeypatch):
    request = _request(tmp_path)
    request.app.state.cfg.cognition.proposal_publish_enabled = False

    with pytest.raises(Exception) as exc:
        research_os.publish_proposal(
            "task_001", request, research_os.PublishProposalRequest(force=False)
        )
    assert getattr(exc.value, "status_code", None) == 403


def test_cognition_api_url_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNITION_API_URL", "http://127.0.0.1:3999/api")
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.cognition.api_url == "http://127.0.0.1:3999/api"
