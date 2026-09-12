from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import return_candidates as return_api
from app.integration.cognition_gateway import (
    CognitionGateway,
    CognitionGatewayError,
    PublishedProposal,
)
from app.integration.return_formal import (
    FormalApplyInput,
    FormalCognitionHandoffService,
    FormalHandoffStateError,
    build_formal_proposal_payload,
)
from app.research.return_candidates import ResearchReturnCandidateRecord, TargetSnapshot
from app.synthesis.schemas import Claim
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence, WorkerInfo

FORMAL_ID = "11111111-1111-4111-8111-111111111111"


def _result() -> ResultEnvelope:
    return ResultEnvelope(
        task_id="task-formal",
        task_type="causal_synthesis",
        query="AI 收入传导是否需要修订？",
        summary="test",
        claims=[
            Claim(
                id="claim_001",
                text="生产率改善并不保证劳动收入同步增长。",
                epistemic_state="supported",
                evidence_refs=["M06:s1:c1"],
            )
        ],
        tensions=[],
        uncertainties=[],
        open_questions=[],
        additional_evidence_needed=[],
        worker=WorkerInfo(tool="codex", model="test"),
        generated_at="2026-09-06T09:00:00+08:00",
    )


def _evidence() -> list[TaskPackEvidence]:
    return [
        TaskPackEvidence(
            evidence_id="EV001",
            source_type="report",
            document_id="M06",
            section_id="M06:s1",
            chunk_id="M06:s1:c1",
            content_hash="evidence-v1",
            title="AI 收入传导研究",
            heading_path=["结论"],
            start_line=1,
            end_line=10,
            excerpt="生产率改善并不保证劳动收入同步增长。",
        )
    ]


def _candidate(
    *,
    intent: str = "revise_judgment",
    status: str = "accepted",
    object_type: str = "judgment",
    targets: list[str] | None = None,
) -> ResearchReturnCandidateRecord:
    target_ids = targets if targets is not None else (["cog:j-income"] if intent != "new_judgment" else [])
    snapshots = [
        TargetSnapshot(
            object_id=object_id,
            object_type=object_type,
            baseline_content_hash="baseline-v1",
            baseline_title="旧判断",
            baseline_excerpt="旧判断正文",
            current_content_hash="baseline-v1",
            current_title="旧判断",
            current_excerpt="旧判断正文",
            version_state="unchanged",
            checked_at="2026-09-06T09:00:00+08:00",
        )
        for object_id in target_ids
    ]
    return ResearchReturnCandidateRecord(
        intent=intent,
        target_cognition_object_ids=target_ids,
        proposed_text="修订判断：收入传导可能存在显著时滞。",
        reason="新 Evidence 与快速传导假设存在张力。",
        evidence_chunk_ids=["M06:s1:c1"] if intent != "advance_question" else [],
        source_claim_ids=["claim_001"],
        source_tension_ids=[],
        source_open_question_indexes=[],
        source_additional_evidence_indexes=[],
        proposer="external_worker",
        candidate_id="rc_formal_001",
        task_id="task-formal",
        task_query="AI 收入传导是否需要修订？",
        result_generated_at="2026-09-06T09:00:00+08:00",
        target_snapshots=snapshots,
        has_version_conflict=False,
        version_check_incomplete=False,
        status=status,
        created_at="2026-09-06T09:00:00+08:00",
        updated_at="2026-09-06T09:00:00+08:00",
    )


def _write_cognition_file(path: Path, formal_id: str | None = FORMAL_ID) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    id_line = f"id: {formal_id}\n" if formal_id is not None else ""
    path.write_text(
        f"---\n{id_line}title: 旧判断\n---\n# 旧判断\n\n正文\n",
        encoding="utf-8",
    )


class FakeDocs:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def get(self, doc_id: str):
        return next((row for row in self.rows if row.get("id") == doc_id), None)

    def list_documents(self):
        return [dict(row) for row in self.rows]


def _docs(tmp_path: Path, *, formal_id: str | None = FORMAL_ID) -> FakeDocs:
    source = tmp_path / "cognition" / "04_判断台账" / "income.md"
    _write_cognition_file(source, formal_id)
    return FakeDocs(
        [
            {
                "id": "cog:j-income",
                "source_path": str(source),
                "sha256": "baseline-v1",
                "title": "旧判断",
            }
        ]
    )


def test_revision_mapping_keeps_content_and_traceable_evidence():
    payload = build_formal_proposal_payload(_candidate(), _result(), _evidence())
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["candidate_type"] == "judgment_update"
    assert item["target_ref"] == "cog:j-income"
    assert item["suggested_action"] == "update"
    assert item["sections"]["内容"].startswith("修订判断")
    assert "M06:s1:c1" in item["sections"]["支持证据"]
    assert "task-formal" in item["sections"]["来源定位"]


def test_add_evidence_requires_explicit_polarity_and_maps_both_roles():
    candidate = _candidate(intent="add_evidence")
    with pytest.raises(FormalHandoffStateError, match="evidence_role"):
        build_formal_proposal_payload(candidate, _result(), _evidence())

    supporting = build_formal_proposal_payload(
        candidate,
        _result(),
        _evidence(),
        evidence_role="supporting",
    )["items"][0]
    assert supporting["candidate_type"] == "add_supporting_evidence"
    assert "M06:s1:c1" in supporting["sections"]["支持证据"]
    assert supporting["sections"]["反方证据"] == ""

    counter = build_formal_proposal_payload(
        candidate,
        _result(),
        _evidence(),
        evidence_role="counter",
    )["items"][0]
    assert counter["candidate_type"] == "add_counter_evidence"
    assert counter["sections"]["支持证据"] == ""
    assert "M06:s1:c1" in counter["sections"]["反方证据"]


def test_formalization_rejects_unreviewed_relation_and_multi_target():
    with pytest.raises(FormalHandoffStateError, match="accepted"):
        build_formal_proposal_payload(
            _candidate(status="proposed"), _result(), _evidence()
        )
    with pytest.raises(FormalHandoffStateError, match="relation"):
        build_formal_proposal_payload(
            _candidate(intent="relation_change"), _result(), _evidence()
        )
    with pytest.raises(FormalHandoffStateError, match="exactly one"):
        build_formal_proposal_payload(
            _candidate(targets=["cog:j-1", "cog:j-2"]), _result(), _evidence()
        )


class FakeGateway:
    def __init__(self) -> None:
        self.hash = "official-h1"
        self.created = 0
        self.previewed = 0
        self.applied = 0
        self.object_ids: list[str] = []
        self.last_payload: dict | None = None
        self.last_apply_kwargs: dict | None = None

    def create_proposal(self, payload):
        self.created += 1
        self.last_payload = payload
        assert len(payload["items"]) == 1
        return PublishedProposal(
            proposal_id="proposal-1",
            raw={
                "ok": True,
                "item": {
                    "id": "proposal-1",
                    "title": payload["title"],
                    "status": "pending",
                    "path": "proposals/proposal-1.md",
                    "itemCount": 1,
                },
            },
        )

    def get_proposal(self, proposal_id):
        return {
            "ok": True,
            "item": {"id": proposal_id, "title": "proposal", "itemCount": 1},
            "items": [
                {
                    "itemId": "proposal-item-1",
                    "raw": {},
                    "meta": {},
                    "sections": {},
                    "evidence": [],
                    "preview": None,
                    "suggestedTarget": None,
                }
            ],
        }

    def get_object(self, object_type, object_id):
        self.object_ids.append(object_id)
        return {
            "ok": True,
            "item": {
                "id": object_id,
                "type": object_type,
                "title": "当前判断",
                "_hash": self.hash,
            },
        }

    def preview_proposal_item(self, proposal_id, item_id):
        self.previewed += 1
        return {
            "ok": True,
            "itemId": item_id,
            "diff": {"action": "update", "target": FORMAL_ID},
        }

    def apply_proposal_item(self, proposal_id, item_id, **kwargs):
        self.applied += 1
        self.last_apply_kwargs = kwargs
        return {
            "ok": True,
            "itemId": item_id,
            "status": "accepted",
            "created": None,
            "updatedId": FORMAL_ID,
            "proposalStatus": "accepted",
        }


def test_formal_lifecycle_bridges_ke_id_to_app_uuid_and_reads_back(tmp_path: Path):
    pack = tmp_path / "completed" / "task-formal"
    (pack / "result").mkdir(parents=True)
    gateway = FakeGateway()
    service = FormalCognitionHandoffService(
        gateway, cognition_docs=_docs(tmp_path)
    )  # type: ignore[arg-type]
    candidate = _candidate()

    first, reused = service.formalize(
        pack=pack,
        candidate=candidate,
        result=_result(),
        evidence=_evidence(),
    )
    assert reused is False
    assert first["proposal_id"] == "proposal-1"
    assert first["proposal_item_id"] == "proposal-item-1"
    assert first["formal_write_performed"] is False
    assert first["published_target_hashes"] == {"cog:j-income": "official-h1"}
    assert first["target_identities"][0]["ke_target_id"] == "cog:j-income"
    assert first["target_identities"][0]["cognition_target_id"] == FORMAL_ID
    assert gateway.created == 1
    assert gateway.last_payload is not None
    assert gateway.last_payload["items"][0]["target_ref"] == FORMAL_ID
    assert gateway.object_ids[-1] == FORMAL_ID
    assert candidate.target_snapshots[0].baseline_content_hash == "baseline-v1"

    second, reused2 = service.formalize(
        pack=pack,
        candidate=candidate,
        result=_result(),
        evidence=_evidence(),
    )
    assert reused2 is True
    assert second["proposal_id"] == first["proposal_id"]
    assert gateway.created == 1

    previewed = service.preview(pack=pack, candidate=candidate)
    assert previewed["preview"]["target_hashes"] == {"cog:j-income": "official-h1"}
    assert previewed["formal_write_performed"] is False
    assert gateway.previewed == 1

    with pytest.raises(FormalHandoffStateError, match="target_id"):
        service.apply(
            pack=pack,
            candidate=candidate,
            body=FormalApplyInput(confirm=True, target_id="cog:other"),
        )
    assert gateway.applied == 0

    with pytest.raises(FormalHandoffStateError, match="action"):
        service.apply(
            pack=pack,
            candidate=candidate,
            body=FormalApplyInput(confirm=True, action="create"),
        )
    assert gateway.applied == 0

    gateway.hash = "official-h2"
    with pytest.raises(FormalHandoffStateError, match="changed after Preview"):
        service.apply(
            pack=pack,
            candidate=candidate,
            body=FormalApplyInput(confirm=True),
        )
    assert gateway.applied == 0

    gateway.hash = "official-h1"
    applied = service.apply(
        pack=pack,
        candidate=candidate,
        body=FormalApplyInput(confirm=True, target_id="cog:j-income"),
    )
    assert gateway.applied == 1
    assert gateway.last_apply_kwargs is not None
    assert gateway.last_apply_kwargs["target_id"] == FORMAL_ID
    assert applied["formal_write_performed"] is True
    assert applied["writer"] == "cognition_app"
    assert applied["apply"]["readback"]["item"]["id"] == FORMAL_ID

    with pytest.raises(FormalHandoffStateError, match="already been formally applied"):
        service.apply(
            pack=pack,
            candidate=candidate,
            body=FormalApplyInput(confirm=True),
        )


def test_hash_change_between_publish_and_preview_blocks_preview(tmp_path: Path):
    pack = tmp_path / "completed" / "task-formal"
    (pack / "result").mkdir(parents=True)
    gateway = FakeGateway()
    service = FormalCognitionHandoffService(
        gateway, cognition_docs=_docs(tmp_path)
    )  # type: ignore[arg-type]
    candidate = _candidate()
    service.formalize(pack=pack, candidate=candidate, result=_result(), evidence=_evidence())
    gateway.hash = "official-h2"

    with pytest.raises(FormalHandoffStateError, match="changed after Proposal publication"):
        service.preview(pack=pack, candidate=candidate)
    assert gateway.previewed == 0


def test_missing_or_malformed_frontmatter_id_blocks_before_proposal_write(tmp_path: Path):
    for raw_id in (None, "not-a-uuid"):
        case = tmp_path / ("missing" if raw_id is None else "malformed")
        pack = case / "completed" / "task-formal"
        (pack / "result").mkdir(parents=True)
        gateway = FakeGateway()
        service = FormalCognitionHandoffService(
            gateway, cognition_docs=_docs(case, formal_id=raw_id)
        )  # type: ignore[arg-type]
        with pytest.raises(FormalHandoffStateError, match="front-matter id"):
            service.formalize(
                pack=pack,
                candidate=_candidate(),
                result=_result(),
                evidence=_evidence(),
            )
        assert gateway.created == 0


def test_ambiguous_frontmatter_uuid_blocks_before_proposal_write(tmp_path: Path):
    docs = _docs(tmp_path)
    duplicate = tmp_path / "cognition" / "04_判断台账" / "duplicate.md"
    _write_cognition_file(duplicate, FORMAL_ID)
    docs.rows.append(
        {
            "id": "cog:j-duplicate",
            "source_path": str(duplicate),
            "sha256": "other-ke-sha256",
            "title": "重复 UUID",
        }
    )
    gateway = FakeGateway()
    service = FormalCognitionHandoffService(gateway, cognition_docs=docs)  # type: ignore[arg-type]
    pack = tmp_path / "completed" / "task-formal"
    (pack / "result").mkdir(parents=True)

    with pytest.raises(FormalHandoffStateError, match="ambiguous"):
        service.formalize(
            pack=pack,
            candidate=_candidate(),
            result=_result(),
            evidence=_evidence(),
        )
    assert gateway.created == 0


def test_pure_rename_uses_current_source_path_but_ids_stay_stable(tmp_path: Path):
    pack = tmp_path / "completed" / "task-formal"
    (pack / "result").mkdir(parents=True)
    docs = _docs(tmp_path)
    gateway = FakeGateway()
    service = FormalCognitionHandoffService(gateway, cognition_docs=docs)  # type: ignore[arg-type]
    candidate = _candidate()
    marker, _ = service.formalize(
        pack=pack, candidate=candidate, result=_result(), evidence=_evidence()
    )
    old_path = Path(docs.rows[0]["source_path"])
    renamed = old_path.with_name("income-renamed.md")
    old_path.rename(renamed)
    docs.rows[0]["source_path"] = str(renamed)

    previewed = service.preview(pack=pack, candidate=candidate)
    assert previewed["preview"]["target_hashes"] == {"cog:j-income": "official-h1"}
    assert marker["target_identities"][0]["ke_target_id"] == "cog:j-income"
    assert marker["target_identities"][0]["cognition_target_id"] == FORMAL_ID
    assert gateway.object_ids[-1] == FORMAL_ID


def test_direct_uuid_adapter_harness_remains_supported_without_catalog(tmp_path: Path):
    candidate = _candidate(targets=[FORMAL_ID])
    pack = tmp_path / "completed" / "task-formal"
    (pack / "result").mkdir(parents=True)
    gateway = FakeGateway()
    service = FormalCognitionHandoffService(gateway)  # type: ignore[arg-type]
    marker, reused = service.formalize(
        pack=pack, candidate=candidate, result=_result(), evidence=_evidence()
    )
    assert reused is False
    assert marker["target_identities"][0]["cognition_target_id"] == FORMAL_ID


def test_gateway_normalizes_http_200_non_object_json(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return ["malformed"]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def request(*args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.integration.cognition_gateway.httpx.Client", FakeClient)
    with pytest.raises(CognitionGatewayError, match="must be an object"):
        CognitionGateway("http://127.0.0.1:3420/api").health()


def test_ke_preflight_stays_staging_only_when_formal_apply_is_enabled(monkeypatch):
    candidate = _candidate()
    record = SimpleNamespace(candidates=[candidate])
    service = SimpleNamespace(refresh_target_versions=lambda task_id: record)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                cfg=SimpleNamespace(
                    cognition=SimpleNamespace(formal_apply_enabled=True),
                )
            )
        )
    )

    monkeypatch.setattr(return_api, "_refresh_derived_cognition", lambda _request: None)
    monkeypatch.setattr(return_api, "_service", lambda _request: service)

    body = return_api.preflight_return_candidate(
        "task-formal",
        candidate.candidate_id,
        request,
    )

    assert body["ke_preflight_only"] is True
    assert body["formal_preview_supported"] is False
    assert body["formal_apply_supported"] is False
    assert body["formal_write_performed"] is False
