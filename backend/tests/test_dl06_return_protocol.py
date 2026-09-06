from __future__ import annotations

import json
from pathlib import Path

from app.taskpack.schemas import ResultEnvelope


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "app" / "taskpack" / "templates"


def _base_result() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task-1",
        "task_type": "summary",
        "query": "test",
        "summary": "",
        "claims": [],
        "tensions": [],
        "uncertainties": [],
        "open_questions": [],
        "additional_evidence_needed": [],
        "worker": {"tool": "codex", "model": "test"},
        "generated_at": "2026-09-06T02:00:00+08:00",
    }


def test_return_suggestions_are_optional_backward_compatible_result_extra():
    old = ResultEnvelope.model_validate(_base_result())
    assert old.task_id == "task-1"
    assert "research_return_candidates" not in old.model_dump(exclude_none=True)

    raw = _base_result()
    raw["research_return_candidates"] = [
        {
            "intent": "revise_judgment",
            "target_cognition_object_ids": ["cog:j-1"],
            "proposed_text": "new text",
            "reason": "new Evidence changes the old assumption",
            "evidence_chunk_ids": ["M01:s1:c1"],
            "source_claim_ids": ["claim_001"],
        }
    ]
    parsed = ResultEnvelope.model_validate(raw)
    assert parsed.model_extra is not None
    assert parsed.model_extra["research_return_candidates"][0]["intent"] == "revise_judgment"


def test_output_schema_and_worker_instruction_define_staging_not_apply():
    schema = json.loads((TEMPLATE_DIR / "OUTPUT_SCHEMA_V1.json").read_text(encoding="utf-8"))
    prop = schema["properties"]["research_return_candidates"]
    assert "research_return_candidates" not in schema["required"]
    assert prop["type"] == "array"
    intents = prop["items"]["properties"]["intent"]["enum"]
    assert set(intents) == {
        "new_judgment",
        "add_evidence",
        "revise_judgment",
        "suggest_retract",
        "advance_question",
        "relation_change",
    }

    instruction = (TEMPLATE_DIR / "AGENT_INSTRUCTION_V1.md").read_text(encoding="utf-8")
    assert "research_return_candidates" in instruction
    assert "cognition_context.jsonl" in instruction
    assert "不是正式修改" in instruction
    assert "不会自动 Preview / Apply" in instruction
    assert "不得声称候选已经被用户接受" in instruction
