"""TaskPack V1 Schema 单测（V3.0 方案 §7/§9/§11/§13/§17/§23/§66）。"""

from __future__ import annotations

import yaml
import pytest
from pydantic import ValidationError

from app.taskpack.schemas import (
    Manifest,
    ResultEnvelope,
    RunMeta,
    TaskPackEvidence,
    TaskPackV1,
    TaskYaml,
)

SHA = "a" * 64
SHA2 = "b" * 64

SPEC_TASK_YAML = """
schema_version: "1.0"
task_id: "20260830_143500_ai_capex"
task_type: "causal_synthesis"
query: >
  AI Capex 的边际回报是否正在下降？
created_at: "2026-08-30T14:35:00+08:00"
taskpack_version: "1.0"
prompt_version: "taskpack-synthesis-v1"
permissions:
  read_only_inputs: true
  allow_network: false
  allow_external_sources: false
  allow_write_paths:
    - result/
constraints:
  evidence_only: true
  max_claims: 12
  language: "zh-CN"
expected_output:
  schema: "SynthesisDraftV1"
  path: "result/result.json"
"""

SPEC_EVIDENCE_LINE = {
    "evidence_id": "EV001",
    "source_type": "report",
    "document_id": "M04",
    "section_id": "ch3-2",
    "chunk_id": "M04:ch3-2:0004",
    "content_hash": SHA,
    "title": "t",
    "heading_path": ["a", "b"],
    "start_line": 420,
    "end_line": 468,
    "excerpt": "……",
}


def _task_yaml(**overrides):
    data = yaml.safe_load(SPEC_TASK_YAML)
    data.update(overrides)
    return TaskYaml(**data)


def _manifest(**overrides):
    payload = {
        "taskpack_version": "1.0",
        "task_id": "20260830_143500_ai_capex",
        "created_at": "2026-08-30T14:35:00+08:00",
        "files": {"task.yaml": SHA},
        "evidence_count": 1,
        "cognition_context_count": 0,
    }
    payload.update(overrides)
    return Manifest(**payload)


def _result(**overrides):
    payload = {
        "schema_version": "1.0",
        "task_id": "20260830_143500_ai_capex",
        "task_type": "summary",
        "query": "AI Capex 的边际回报是否正在下降？",
        "summary": "……",
        "claims": [
            {
                "id": "claim_001",
                "text": "……",
                "epistemic_state": "supported",
                "evidence_refs": ["M04:ch3-2:0004"],
            }
        ],
        "tensions": [],
        "uncertainties": ["……"],
        "open_questions": [],
        "additional_evidence_needed": [
            {"question": "缺少……", "reason": "当前 Evidence 无法确认……"}
        ],
        "worker": {"tool": "trae", "model": "qwen3.8-flash"},
        "generated_at": "2026-08-30T15:00:18+08:00",
    }
    payload.update(overrides)
    return ResultEnvelope(**payload)


def _pack(evidence_count=1, manifest_task_id="20260830_143500_ai_capex"):
    evidence = [dict(SPEC_EVIDENCE_LINE)] if evidence_count else []
    manifest = _manifest(
        task_id=manifest_task_id,
        files={"task.yaml": SHA, "evidence.jsonl": SHA2},
        evidence_count=evidence_count,
    )
    return TaskPackV1(task=_task_yaml(), evidence=evidence, manifest=manifest)


def test_task_yaml_parses_spec_sample():
    task = _task_yaml()
    assert task.task_id == "20260830_143500_ai_capex"
    assert task.task_type == "causal_synthesis"
    assert task.permissions.allow_network is False
    assert task.permissions.allow_write_paths == ["result/"]
    assert task.constraints.evidence_only is True
    assert task.constraints.max_claims == 12
    assert task.constraints.language == "zh-CN"
    assert task.expected_output.schema_name == "SynthesisDraftV1"
    assert task.expected_output.path == "result/result.json"


def test_task_yaml_round_trip_uses_schema_alias():
    dumped = _task_yaml().model_dump(by_alias=True)
    assert dumped["expected_output"]["schema"] == "SynthesisDraftV1"
    assert "schema_name" not in dumped["expected_output"]


@pytest.mark.parametrize(
    "bad",
    ["../evil", "a b", "", "20260830_143500_ai_capex/extra", "..", ".hidden"],
)
def test_task_yaml_rejects_bad_task_id(bad):
    with pytest.raises(ValidationError):
        _task_yaml(task_id=bad)


def test_task_yaml_rejects_bad_created_at():
    with pytest.raises(ValidationError):
        _task_yaml(created_at="2026/08/30 14:35:00")


def test_task_yaml_rejects_unknown_task_type():
    with pytest.raises(ValidationError):
        _task_yaml(task_type="freeform")


def test_manifest_normalizes_hash_case():
    m = _manifest(files={"task.yaml": SHA.upper()})
    assert m.files["task.yaml"] == SHA


def test_manifest_rejects_bad_hash():
    with pytest.raises(ValidationError):
        _manifest(files={"task.yaml": "sha256:abcdef"})


def test_manifest_allows_extra_fields():
    m = _manifest(note="x")
    assert m.model_extra["note"] == "x"


def test_run_meta_accepts_null_tokens_and_dates():
    rm = RunMeta(
        worker_tool="trae",
        provider="qwen",
        model="qwen3.8-flash",
        model_version=None,
        started_at=None,
        completed_at=None,
        prompt_version="taskpack-synthesis-v1",
        prompt_sha256=SHA,
        task_manifest_sha256=SHA2,
        input_tokens=None,
        output_tokens=None,
    )
    assert rm.input_tokens is None
    assert rm.completed_at is None


def test_run_meta_rejects_bad_prompt_sha():
    with pytest.raises(ValidationError):
        RunMeta(worker_tool="trae", prompt_sha256="xyz", task_manifest_sha256=SHA)


def test_result_envelope_minimal_valid():
    r = _result()
    assert r.claims[0].evidence_refs == ["M04:ch3-2:0004"]
    assert r.additional_evidence_needed[0].question == "缺少……"
    assert r.worker.tool == "trae"


def test_result_envelope_tolerates_extra_fields():
    r = _result(notes_meta={"elapsed_s": 18})
    assert r.model_extra["notes_meta"] == {"elapsed_s": 18}


def test_result_envelope_rejects_bad_epistemic_state():
    with pytest.raises(ValidationError):
        _result(
            claims=[
                {"id": "c1", "text": "x", "epistemic_state": "guess", "evidence_refs": []}
            ]
        )


def test_result_envelope_rejects_bad_task_id():
    with pytest.raises(ValidationError):
        _result(task_id="bad id")


def test_taskpack_evidence_tolerates_missing_optional_fields():
    item = TaskPackEvidence(
        evidence_id="EV001",
        source_type="report",
        document_id="M04",
        chunk_id="M04:ch1:0001",
    )
    assert item.excerpt is None
    assert item.content_hash is None
    assert item.heading_path == []


def test_taskpack_v1_aggregate_valid():
    pack = _pack()
    assert pack.evidence[0].chunk_id == "M04:ch3-2:0004"
    assert pack.manifest.evidence_count == 1


def test_taskpack_v1_rejects_count_mismatch():
    with pytest.raises(ValidationError):
        _pack(evidence_count=2)


def test_taskpack_v1_rejects_task_id_mismatch():
    with pytest.raises(ValidationError):
        _pack(manifest_task_id="20260830_999999_other")


def test_taskpack_v1_accepts_empty_evidence():
    pack = _pack(evidence_count=0)
    assert pack.evidence == []
    assert pack.manifest.evidence_count == 0
