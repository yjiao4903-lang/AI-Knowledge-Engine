"""TaskPack Builder 单测（V3.0 方案 §5/§6/§7/§9/§11/§31/§67）。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest
import yaml
from pydantic import ValidationError

from app.core.errors import EvidenceNotFoundError, EvidenceStaleError
from app.synthesis.schemas import EvidenceRef
from app.taskpack.builder import PACK_INPUT_FILES, ROOT_SUBDIRS, TEMPLATE_FILES
from app.taskpack.schemas import TaskPackV1

NOW = datetime(2026, 8, 30, 14, 35, 0)


def _create(env, *, refs=None, now=NOW, **kw):
    return env["builder"].create_task(
        task_type=kw.pop("task_type", "summary"),
        query=kw.pop("query", "HBM4 对先进封装的价值量影响"),
        evidence_refs=refs if refs is not None else env["refs"],
        now=now,
        **kw,
    )


def test_creates_pack_in_outbox(tk_env):
    ct = _create(tk_env)
    assert ct.status == "READY"
    assert ct.task_path == tk_env["root"] / "outbox" / ct.task_id
    assert ct.evidence_count == 2
    assert ct.task_id.startswith("20260830_143500_")
    for name in ("task.yaml", "AGENT_INSTRUCTION.md", "evidence.jsonl",
                 "output_schema.json", "README.md", "manifest.json"):
        assert (ct.task_path / name).is_file(), name
    assert (ct.task_path / "result" / ".gitkeep").is_file()


def test_root_tree_and_template_sync(tk_env):
    _create(tk_env)
    for sub in ROOT_SUBDIRS:
        assert (tk_env["root"] / sub).is_dir(), sub
    for name in TEMPLATE_FILES:
        assert (tk_env["root"] / "templates" / name).is_file(), name
    canonical = (tk_env["builder"].template_dir / "AGENT_INSTRUCTION_V1.md").read_text(
        encoding="utf-8"
    )
    synced = (tk_env["root"] / "templates" / "AGENT_INSTRUCTION_V1.md").read_text(
        encoding="utf-8"
    )
    assert synced == canonical
    assert "TASKPACK WORKER — STANDARD INSTRUCTION V1" in canonical
    for rule in ("2026E", "2027E", "不得标为 `supported`", "没有直接因果证据"):
        assert rule in canonical
        assert rule in synced


def test_task_yaml_contract(tk_env):
    ct = _create(tk_env)
    data = yaml.safe_load((ct.task_path / "task.yaml").read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["task_id"] == ct.task_id
    assert data["task_type"] == "summary"
    assert data["created_at"] == NOW.isoformat(timespec="seconds")
    assert data["taskpack_version"] == "1.0"
    assert data["prompt_version"] == "taskpack-synthesis-v1"
    assert data["expected_output"]["schema"] == "SynthesisDraftV1"
    assert data["expected_output"]["path"] == "result/result.json"
    assert data["permissions"]["allow_write_paths"] == ["result/"]
    assert data["permissions"]["allow_network"] is False
    assert data["permissions"]["allow_external_sources"] is False
    assert data["constraints"]["evidence_only"] is True
    assert data["constraints"]["max_claims"] == 12
    assert data["constraints"]["language"] == "zh-CN"
    assert "task_specific_instruction" not in data


def test_task_specific_instruction_roundtrip(tk_env):
    ct = _create(tk_env, task_specific_instruction="聚焦 HBM4 与 CoWoS 的联动。")
    data = yaml.safe_load((ct.task_path / "task.yaml").read_text(encoding="utf-8"))
    assert data["task_specific_instruction"] == "聚焦 HBM4 与 CoWoS 的联动。"


def test_evidence_jsonl_snapshot(tk_env):
    ct = _create(tk_env)
    rows = [
        json.loads(line)
        for line in (ct.task_path / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    first = rows[0]
    assert first["evidence_id"] == "EV001"
    assert first["source_type"] == "report"
    assert first["document_id"] == "M04"
    assert first["section_id"] == "M04:ch1"
    assert first["chunk_id"] == "M04:ch1:0001"
    assert first["content_hash"] == tk_env["hashes"][0]
    assert first["title"] == "HBM4 接口"
    assert first["heading_path"] == ["HBM4 接口"]
    assert first["start_line"] == 1
    assert first["end_line"] == 20
    assert first["excerpt"].startswith("HBM4")
    assert rows[1]["evidence_id"] == "EV002"


def test_manifest_hashes_and_counts(tk_env):
    ct = _create(tk_env)
    manifest = json.loads((ct.task_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["taskpack_version"] == "1.0"
    assert manifest["task_id"] == ct.task_id
    assert manifest["evidence_count"] == 2
    assert manifest["cognition_context_count"] == 0
    assert set(manifest["files"]) == set(PACK_INPUT_FILES)
    assert "manifest.json" not in manifest["files"]
    for name, digest in manifest["files"].items():
        actual = hashlib.sha256((ct.task_path / name).read_bytes()).hexdigest()
        assert digest == actual, name


def test_task_id_collision_suffix(tk_env):
    a = _create(tk_env)
    b = _create(tk_env)
    assert a.task_id != b.task_id
    assert b.task_id == f"{a.task_id}-2"
    assert b.task_path.is_dir()


def test_create_task_failure_cleans_visible_ready_pack(tk_env, monkeypatch):
    """Evidence resolution failure must not leave a directory discoverable as READY."""
    builder = tk_env["builder"]

    def fail(_refs):
        raise RuntimeError("simulated evidence failure")

    monkeypatch.setattr(builder, "_resolve_evidence", fail)
    with pytest.raises(RuntimeError, match="simulated evidence failure"):
        builder.create_task(
            task_type="summary", query="cleanup check", evidence_refs=tk_env["refs"],
            now=NOW,
        )
    assert list((tk_env["root"] / "outbox").iterdir()) == []


def test_unknown_chunk_raises_not_found(tk_env):
    bad = [EvidenceRef(source_type="report", document_id="M04", chunk_id="M04:ch1:9999")]
    with pytest.raises(EvidenceNotFoundError):
        _create(tk_env, refs=bad)


def test_stale_chunk_raises_conflict(tk_env):
    bad = [EvidenceRef(source_type="report", document_id="M04",
                       chunk_id="M04:ch1:0001", content_hash="f" * 64)]
    with pytest.raises(EvidenceStaleError):
        _create(tk_env, refs=bad)


def test_max_evidence_exceeded(tk_env):
    tk_env["cfg"].taskpack.max_evidence = 1
    with pytest.raises(ValueError, match="max_evidence"):
        _create(tk_env)


def test_empty_evidence_rejected(tk_env):
    with pytest.raises(ValueError, match="证据"):
        _create(tk_env, refs=[])


def test_empty_query_rejected(tk_env):
    with pytest.raises(ValueError, match="query"):
        _create(tk_env, query="   ")


def test_invalid_task_type_rejected(tk_env):
    with pytest.raises(ValidationError):
        _create(tk_env, task_type="translation")


def test_cognition_context_written(tk_env):
    ctx = [{"context_id": "CTX001", "object_type": "judgment",
            "object_id": "J-HBM4-001", "title": "HBM4 判断", "excerpt": "……"}]
    ct = _create(tk_env, cognition_context=ctx)
    assert ct.cognition_context_count == 1
    row = json.loads(
        (ct.task_path / "cognition_context.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert row["context_id"] == "CTX001"
    assert row["object_type"] == "judgment"
    manifest = json.loads((ct.task_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["cognition_context.jsonl"]
    assert manifest["cognition_context_count"] == 1


def test_pack_validates_against_taskpack_v1(tk_env):
    """构建产物按 §66 聚合 Schema 读回必须自洽（Task 5 Importer 的输入前提）。"""
    ct = _create(tk_env, cognition_context=[
        {"context_id": "CTX001", "object_type": "judgment", "object_id": "J1"}
    ])
    pack = ct.task_path
    task = yaml.safe_load((pack / "task.yaml").read_text(encoding="utf-8"))
    evidence = [
        json.loads(x)
        for x in (pack / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    cog = [
        json.loads(x)
        for x in (pack / "cognition_context.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    aggregate = TaskPackV1.model_validate(
        {"task": task, "evidence": evidence, "cognition_context": cog, "manifest": manifest}
    )
    assert aggregate.task.task_id == ct.task_id
    assert len(aggregate.evidence) == 2
    assert len(aggregate.cognition_context) == 1


def test_agent_instruction_is_canonical_copy(tk_env):
    ct = _create(tk_env)
    src = (tk_env["builder"].template_dir / "AGENT_INSTRUCTION_V1.md").read_text(
        encoding="utf-8"
    )
    assert (ct.task_path / "AGENT_INSTRUCTION.md").read_text(encoding="utf-8") == src


def test_output_schema_matches_envelope_contract(tk_env):
    ct = _create(tk_env)
    schema = json.loads((ct.task_path / "output_schema.json").read_text(encoding="utf-8"))
    for key in ("schema_version", "task_id", "task_type", "query", "claims",
                "tensions", "uncertainties", "open_questions",
                "additional_evidence_needed", "worker", "generated_at"):
        assert key in schema["required"], key
    states = schema["properties"]["claims"]["items"]["properties"]["epistemic_state"]["enum"]
    assert set(states) == {"supported", "inference", "hypothesis", "uncertain", "contradicted"}
    addl = schema["properties"]["additional_evidence_needed"]["items"]
    assert set(addl["required"]) == {"question", "reason"}
