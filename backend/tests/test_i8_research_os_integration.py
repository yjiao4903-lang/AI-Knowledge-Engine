from pathlib import Path
from types import SimpleNamespace

from app.api import synthesis as synthesis_api
from app.contracts.cognition import CognitionContextItem
from app.core.config import load_config
from app.integration.proposals import build_cognition_proposal_payload
from app.synthesis.schemas import Claim, SynthesisRequest, Tension
from app.taskpack.importer import COMPLETED
from app.taskpack.schemas import (
    AdditionalEvidenceNeeded,
    ResultEnvelope,
    TaskPackEvidence,
    WorkerInfo,
)


def _evidence(chunk_id: str = "M04:ch1:o1:0001") -> TaskPackEvidence:
    return TaskPackEvidence(
        evidence_id="EV001",
        source_type="report",
        document_id="M04",
        section_id="ch1",
        chunk_id=chunk_id,
        content_hash="a" * 64,
        title="HBM4",
        heading_path=["第一章", "HBM4"],
        start_line=10,
        end_line=20,
        excerpt="HBM4 evidence snapshot",
    )


def _result(task_id: str = "task_001", chunk_id: str = "M04:ch1:o1:0001") -> ResultEnvelope:
    return ResultEnvelope(
        task_id=task_id,
        task_type="causal_synthesis",
        query="AI CAPEX 如何影响现金流？",
        summary="summary",
        claims=[
            Claim(
                id="claim_001",
                text="CAPEX 上升会压低短期自由现金流。",
                epistemic_state="supported",
                evidence_refs=[chunk_id],
            )
        ],
        tensions=[
            Tension(
                id="tension_001",
                text="投资扩张与短期现金流之间存在张力。",
                evidence_refs=[chunk_id],
            )
        ],
        open_questions=["收入增速能否覆盖折旧增长？"],
        additional_evidence_needed=[
            AdditionalEvidenceNeeded(
                question="需要哪些未来收入数据？",
                reason="现有固定证据没有覆盖未来收入兑现。",
            )
        ],
        worker=WorkerInfo(tool="codex", model="gpt"),
        generated_at="2026-09-01T12:00:00+08:00",
    )


def test_synthesis_request_accepts_structured_cognition_context():
    req = SynthesisRequest(
        task_type="summary",
        query="test",
        evidence_refs=[
            {
                "source_type": "report",
                "document_id": "M04",
                "chunk_id": "M04:ch1:o1:0001",
            }
        ],
        cognition_context=[
            {
                "context_id": "CTX001",
                "object_type": "judgment",
                "object_id": "judgment-1",
                "content_hash": "b" * 64,
                "title": "当前判断",
                "excerpt": "existing cognition",
            }
        ],
    )
    assert isinstance(req.cognition_context[0], CognitionContextItem)
    assert req.cognition_context[0].object_id == "judgment-1"


def test_taskpack_result_converts_to_conservative_cognition_proposal():
    chunk_id = "M04:ch1:o1:0001"
    payload, warnings = build_cognition_proposal_payload(_result(chunk_id=chunk_id), [_evidence(chunk_id)])

    assert any("TENSION_INSUFFICIENT_EVIDENCE_DIVERSITY" in warning for warning in warnings)
    assert payload["origin_type"] == "external_llm"
    assert payload["origin_ref"] == "task_001"
    assert len(payload["items"]) == 4

    claim = payload["items"][0]
    assert claim["candidate_type"] == "new_judgment"
    # `supported` is deliberately NOT promoted to verified_fact.
    assert claim["epistemic_state"] == "inference"
    assert chunk_id in claim["sections"]["支持证据"]

    tension = payload["items"][1]
    assert tension["candidate_type"] == "new_tension"
    assert tension["epistemic_state"] == "unknown"

    question = payload["items"][2]
    assert question["candidate_type"] == "new_question"
    assert question["epistemic_state"] == "open_question"


def test_missing_evidence_snapshot_returns_warning_not_fake_source():
    result = ResultEnvelope(
        task_id="task_002",
        task_type="summary",
        query="test",
        claims=[
            Claim(
                id="claim_001",
                text="claim",
                epistemic_state="inference",
                evidence_refs=["missing-chunk"],
            )
        ],
        worker=WorkerInfo(tool="worker"),
        generated_at="2026-09-01T12:00:00+08:00",
    )
    payload, warnings = build_cognition_proposal_payload(result, [])
    assert warnings
    assert "未找到快照" in payload["items"][0]["sections"]["支持证据"]


def test_proposal_candidate_endpoint_is_read_only_and_postable_shape(tmp_path, monkeypatch):
    pack = Path(tmp_path) / "task_001"
    result_dir = pack / "result"
    result_dir.mkdir(parents=True)
    result_dir.joinpath("result.json").write_text(
        _result().model_dump_json(),
        encoding="utf-8",
    )
    pack.joinpath("evidence.jsonl").write_text(
        _evidence().model_dump_json() + "\n",
        encoding="utf-8",
    )

    importer = SimpleNamespace(
        _make_task_info=lambda _pack: SimpleNamespace(status=COMPLETED)
    )
    monkeypatch.setattr(
        synthesis_api,
        "_require_task",
        lambda _request, _task_id: (pack, importer),
    )

    response = synthesis_api.get_proposal_candidates("task_001", SimpleNamespace())
    assert response["auto_apply"] is False
    assert response["source_status"] == COMPLETED
    assert response["proposal_payload"]["origin_ref"] == "task_001"
    assert response["proposal_payload"]["items"]


def test_runtime_env_overrides_keep_backend_paths_aligned(monkeypatch, tmp_path):
    taskpack = tmp_path / "taskpacks"
    cognition = tmp_path / "cognition"
    kb = tmp_path / "reports"
    models = tmp_path / "models"

    monkeypatch.setenv("AIKE_TASKPACK_ROOT", str(taskpack))
    monkeypatch.setenv("COGNITION_DATA_ROOT", str(cognition))
    monkeypatch.setenv("AIKE_KB_ROOT", str(kb))
    monkeypatch.setenv("AIKE_MODEL_ROOT", str(models))
    monkeypatch.setenv("AIKE_KE_PORT", "9876")

    cfg = load_config(tmp_path / "does-not-exist.yaml")
    assert cfg.taskpack.root_dir == str(taskpack)
    assert cfg.cognition.root == str(cognition)
    assert cfg.knowledge_base.roots == [str(kb)]
    assert cfg.paths.model_dir == str(models)
    assert cfg.app.port == 9876
