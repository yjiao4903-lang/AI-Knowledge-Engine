"""Prompt：Context Envelope + Prompt Injection 隔离（主计划 §10/§11）。"""

from __future__ import annotations

from app.synthesis.prompt import (
    SYSTEM_POLICY,
    build_messages,
    build_output_schema,
    build_user_envelope,
)


def test_injection_isolation_present():
    assert "不可信数据" in SYSTEM_POLICY
    assert "untrusted data" in SYSTEM_POLICY
    assert "绝不要执行" in SYSTEM_POLICY
    assert "当作事实素材" in SYSTEM_POLICY


def test_system_policy_bans_fabrication():
    assert "禁止虚构来源" in SYSTEM_POLICY
    assert "禁止引用本次未提供" in SYSTEM_POLICY


def test_output_schema_factual_claims_need_citation():
    assert "evidence_refs" in build_output_schema()
    assert "逐字一致" in build_output_schema()


def test_messages_structure():
    msgs = build_messages("summary", "HBM4 位宽?", ["认知背景"], [])
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "QUERY" in msgs[1]["content"]
    assert "HBM4 位宽?" in msgs[1]["content"]
    assert "COGNITION CONTEXT" in msgs[1]["content"]
    assert "认知背景" in msgs[1]["content"]
    assert "OUTPUT SCHEMA" in msgs[1]["content"]


def test_envelope_lists_provided_evidence():
    from app.synthesis.grounding import ResolvedEvidence
    from app.synthesis.schemas import EvidenceRef

    ref = EvidenceRef(source_type="report", document_id="M04", chunk_id="M04:ch1:0001",
                      evidence_level=2)
    r = ResolvedEvidence("E1", ref, {"heading_path": "ch1", "evidence_level": 2},
                         "这是 HBM4 接口位宽的原文。")
    user = build_user_envelope("summary", "q", [], [r])
    assert "id=M04:ch1:0001" in user



def test_task_type_instruction_rendered():
    # 通过 service 级联验证：messages 中应含对应任务指令关键字
    msgs = build_messages("tension_extraction", "q", [], [])
    assert "矛盾" in msgs[1]["content"]