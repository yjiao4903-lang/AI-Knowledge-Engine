"""Explicit Formal Cognition handoff for reviewed research-return candidates.

The handoff is deliberately three-stage:
1. formalize -> create exactly one Cognition Proposal item (no formal target write),
2. preview -> call Cognition's zero-write Preview and snapshot official `_hash`,
3. apply -> explicit human-confirmed Apply only if the official hash still matches.

KE never writes Cognition Markdown/SQLite directly. Generic `relation_change` is
not formalizable because the verified Cognition App has no formal relation model.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.integration.cognition_gateway import CognitionGateway, CognitionGatewayError
from app.research.return_candidates import ResearchReturnCandidateRecord
from app.taskpack.schemas import ResultEnvelope, TaskPackEvidence

FORMAL_HANDOFF_SCHEMA_VERSION = "1.0"
EvidenceRole = Literal["supporting", "counter"]


class FormalHandoffStateError(RuntimeError):
    """Raised when a reviewed candidate cannot safely advance to the next stage."""


class FormalizeInput(BaseModel):
    """Human-supplied formalization choices that must not be guessed by the Worker."""

    evidence_role: EvidenceRole | None = None


class FormalApplyInput(BaseModel):
    confirm: Literal[True]
    action: str | None = Field(default=None, max_length=100)
    target_id: str | None = Field(default=None, max_length=200)
    edit_summary: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=500)


def build_formal_proposal_payload(
    candidate: ResearchReturnCandidateRecord,
    result: ResultEnvelope,
    evidence: list[TaskPackEvidence],
    *,
    evidence_role: EvidenceRole | None = None,
) -> dict[str, Any]:
    """Map one reviewed KE candidate to one verified Cognition Proposal item."""
    if candidate.status != "accepted":
        raise FormalHandoffStateError("return candidate must be accepted before formalization")
    if candidate.has_version_conflict:
        raise FormalHandoffStateError("target version conflict must be resolved before formalization")
    if candidate.version_check_incomplete:
        raise FormalHandoffStateError("target version check is incomplete")
    if candidate.intent == "relation_change":
        raise FormalHandoffStateError(
            "formal relation write is unsupported: Cognition has no formal relation contract"
        )

    existing_target_intents = {
        "add_evidence",
        "revise_judgment",
        "suggest_retract",
        "advance_question",
    }
    if candidate.intent in existing_target_intents and len(candidate.target_cognition_object_ids) != 1:
        raise FormalHandoffStateError(
            f"{candidate.intent} requires exactly one formal target per Proposal item"
        )
    if candidate.intent == "new_judgment" and candidate.target_cognition_object_ids:
        raise FormalHandoffStateError("new_judgment must not carry an existing target")
    if candidate.intent != "add_evidence" and evidence_role is not None:
        raise FormalHandoffStateError("evidence_role is only valid for add_evidence")

    evidence_md = _evidence_markdown(candidate.evidence_chunk_ids, evidence)
    source_md = _source_markdown(candidate, result)
    common_sections = {
        "内容": candidate.proposed_text,
        "支持证据": evidence_md,
        "反方证据": "",
        "什么会证明它错": "需在 Cognition Preview / Human Apply 前复核目标版本与反证。",
        "来源定位": source_md,
    }

    item: dict[str, Any]
    if candidate.intent == "new_judgment":
        item = {
            "title": _truncate(candidate.proposed_text),
            "candidate_type": "new_judgment",
            "epistemic_state": _candidate_epistemic_state(candidate, result),
            "suggested_action": "create",
            "confidence": _candidate_confidence(candidate, result),
            "sections": common_sections,
        }
    elif candidate.intent == "revise_judgment":
        _require_target_type(candidate, "judgment")
        item = {
            "title": _truncate(candidate.proposed_text),
            "candidate_type": "judgment_update",
            "target_ref": candidate.target_cognition_object_ids[0],
            "epistemic_state": _candidate_epistemic_state(candidate, result),
            "suggested_action": "update",
            "confidence": _candidate_confidence(candidate, result),
            # Verified Cognition Apply overwrites 当前判断; 内容 must never be omitted.
            "sections": common_sections,
        }
    elif candidate.intent == "add_evidence":
        _require_target_type(candidate, "judgment")
        if evidence_role not in {"supporting", "counter"}:
            raise FormalHandoffStateError(
                "add_evidence requires explicit evidence_role=supporting|counter before formalization"
            )
        sections = dict(common_sections)
        if evidence_role == "counter":
            sections["支持证据"] = ""
            sections["反方证据"] = evidence_md
        item = {
            "title": _truncate(candidate.proposed_text),
            "candidate_type": (
                "add_supporting_evidence"
                if evidence_role == "supporting"
                else "add_counter_evidence"
            ),
            "target_ref": candidate.target_cognition_object_ids[0],
            "epistemic_state": _candidate_epistemic_state(candidate, result),
            "suggested_action": "update",
            "confidence": _candidate_confidence(candidate, result),
            "sections": sections,
        }
    elif candidate.intent == "suggest_retract":
        _require_target_type(candidate, "judgment")
        sections = dict(common_sections)
        sections["反方证据"] = evidence_md
        sections["支持证据"] = ""
        item = {
            "title": _truncate(candidate.proposed_text),
            "candidate_type": "archive_or_reject",
            "target_ref": candidate.target_cognition_object_ids[0],
            "epistemic_state": "counterexample",
            "confidence": _candidate_confidence(candidate, result),
            "sections": sections,
        }
    elif candidate.intent == "advance_question":
        _require_target_type(candidate, "question")
        item = {
            "title": _truncate(candidate.proposed_text),
            "candidate_type": "question_update",
            "target_ref": candidate.target_cognition_object_ids[0],
            "epistemic_state": "open_question",
            "suggested_action": "update",
            "confidence": "low",
            "sections": {
                "内容": candidate.proposed_text,
                "支持证据": evidence_md,
                "反方证据": "",
                "什么会证明它错": "",
                "来源定位": source_md,
            },
        }
    else:  # pragma: no cover - Literal + relation guard above make this defensive.
        raise FormalHandoffStateError(f"unsupported formal intent: {candidate.intent}")

    return {
        "title": f"Research Return：{_truncate(candidate.proposed_text, 48)}",
        "origin_type": "external_llm",
        "origin_ref": f"{candidate.task_id}:{candidate.candidate_id}",
        "origin_title": result.query,
        "generator": "AI-Knowledge-Engine/return-formal-v1",
        "description": candidate.reason,
        "topics": [],
        "items": [item],
    }


class FormalHandoffStore:
    """TaskPack-local durable record of Proposal/Preview/Apply lifecycle."""

    def __init__(self, pack: Path) -> None:
        self.pack = pack
        self.root = pack / "result" / "formal_handoffs"

    def path(self, candidate_id: str) -> Path:
        return self.root / f"{candidate_id}.json"

    def read(self, candidate_id: str) -> dict[str, Any] | None:
        path = self.path(candidate_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise FormalHandoffStateError(f"formal handoff marker is unreadable: {exc}") from exc
        if not isinstance(data, dict):
            raise FormalHandoffStateError("formal handoff marker must be an object")
        return data

    def write(self, candidate_id: str, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path(candidate_id)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)


class FormalCognitionHandoffService:
    def __init__(self, gateway: CognitionGateway) -> None:
        self.gateway = gateway

    def formalize(
        self,
        *,
        pack: Path,
        candidate: ResearchReturnCandidateRecord,
        result: ResultEnvelope,
        evidence: list[TaskPackEvidence],
        evidence_role: EvidenceRole | None = None,
    ) -> tuple[dict[str, Any], bool]:
        store = FormalHandoffStore(pack)
        existing = store.read(candidate.candidate_id)
        if existing is not None:
            if existing.get("evidence_role") != evidence_role:
                raise FormalHandoffStateError(
                    "candidate was already formalized with a different evidence_role"
                )
            return existing, True

        payload = build_formal_proposal_payload(
            candidate,
            result,
            evidence,
            evidence_role=evidence_role,
        )
        official_hashes = self._official_target_hashes(candidate)
        published = self.gateway.create_proposal(payload)
        proposal_item_id = self._proposal_item_id(published.proposal_id, published.raw)
        marker = {
            "schema_version": FORMAL_HANDOFF_SCHEMA_VERSION,
            "task_id": candidate.task_id,
            "candidate_id": candidate.candidate_id,
            "intent": candidate.intent,
            "evidence_role": evidence_role,
            "proposal_id": published.proposal_id,
            "proposal_item_id": proposal_item_id,
            "published_at": _now(),
            "published_target_hashes": official_hashes,
            "preview": None,
            "apply": None,
            "writer": "cognition_app",
            "formal_write_performed": False,
        }
        store.write(candidate.candidate_id, marker)
        return marker, False

    def preview(
        self,
        *,
        pack: Path,
        candidate: ResearchReturnCandidateRecord,
    ) -> dict[str, Any]:
        store = FormalHandoffStore(pack)
        marker = store.read(candidate.candidate_id)
        if marker is None:
            raise FormalHandoffStateError("candidate must be formalized before Cognition Preview")
        if marker.get("apply") is not None:
            raise FormalHandoffStateError("candidate has already been formally applied")

        current_hashes = self._official_target_hashes(candidate)
        if current_hashes != (marker.get("published_target_hashes") or {}):
            raise FormalHandoffStateError(
                "Cognition target changed after Proposal publication; re-review and create a new candidate"
            )
        preview = self.gateway.preview_proposal_item(
            str(marker["proposal_id"]), str(marker["proposal_item_id"])
        )
        marker["preview"] = {
            "previewed_at": _now(),
            "target_hashes": current_hashes,
            "response": preview,
        }
        marker["formal_write_performed"] = False
        store.write(candidate.candidate_id, marker)
        return marker

    def apply(
        self,
        *,
        pack: Path,
        candidate: ResearchReturnCandidateRecord,
        body: FormalApplyInput,
    ) -> dict[str, Any]:
        store = FormalHandoffStore(pack)
        marker = store.read(candidate.candidate_id)
        if marker is None or marker.get("preview") is None:
            raise FormalHandoffStateError("Cognition Preview is required before Apply")
        if marker.get("apply") is not None:
            raise FormalHandoffStateError("candidate has already been formally applied")

        self._validate_apply_overrides(candidate, body)
        current_hashes = self._official_target_hashes(candidate)
        preview_hashes = marker["preview"].get("target_hashes") or {}
        if current_hashes != preview_hashes:
            raise FormalHandoffStateError(
                "Cognition target changed after Preview; Apply is blocked"
            )
        applied = self.gateway.apply_proposal_item(
            str(marker["proposal_id"]),
            str(marker["proposal_item_id"]),
            action=body.action,
            target_id=body.target_id,
            edit_summary=body.edit_summary,
            title=body.title,
        )
        readback = self._readback(applied, candidate)
        marker["apply"] = {
            "applied_at": _now(),
            "response": applied,
            "readback": readback,
        }
        marker["formal_write_performed"] = True
        marker["writer"] = "cognition_app"
        store.write(candidate.candidate_id, marker)
        return marker

    @staticmethod
    def _validate_apply_overrides(
        candidate: ResearchReturnCandidateRecord,
        body: FormalApplyInput,
    ) -> None:
        targets = candidate.target_cognition_object_ids
        if body.target_id is not None:
            if len(targets) != 1 or body.target_id != targets[0]:
                raise FormalHandoffStateError(
                    "Apply target_id must match the reviewed candidate target exactly"
                )

        expected_actions = {
            "new_judgment": "create",
            "add_evidence": "update",
            "revise_judgment": "update",
            "advance_question": "update",
        }
        expected = expected_actions.get(candidate.intent)
        if body.action is not None and expected is not None and body.action != expected:
            raise FormalHandoffStateError(
                f"Apply action must remain {expected!r} for {candidate.intent}"
            )
        # suggest_retract intentionally leaves action selection to Cognition's
        # verified archive_or_reject Proposal semantics; target identity is still fixed.

    def _official_target_hashes(self, candidate: ResearchReturnCandidateRecord) -> dict[str, str | None]:
        hashes: dict[str, str | None] = {}
        snapshots = {row.object_id: row for row in candidate.target_snapshots}
        for object_id in candidate.target_cognition_object_ids:
            snap = snapshots.get(object_id)
            if snap is None:
                raise FormalHandoffStateError(f"missing target snapshot: {object_id}")
            body = self.gateway.get_object(snap.object_type, object_id)
            item = body.get("item")
            if not isinstance(item, dict):
                raise CognitionGatewayError(f"Cognition object response missing item: {object_id}")
            hashes[object_id] = item.get("_hash")
        return hashes

    def _proposal_item_id(self, proposal_id: str, create_response: dict[str, Any]) -> str:
        item_id = _single_proposal_item_id(create_response)
        if item_id is not None:
            return item_id
        return_body = self.gateway.get_proposal(proposal_id)
        item_id = _single_proposal_item_id(return_body)
        if item_id is None:
            raise CognitionGatewayError("Cognition Proposal response does not expose a single item id")
        return item_id

    def _readback(
        self,
        applied: dict[str, Any],
        candidate: ResearchReturnCandidateRecord,
    ) -> dict[str, Any] | None:
        # Verified Cognition builds have returned both top-level apply fields and
        # an `item` wrapper. Accept both without weakening semantic validation.
        wrapped = applied.get("item")
        payload = wrapped if isinstance(wrapped, dict) else applied
        created = payload.get("created")
        if isinstance(created, dict) and created.get("id") and created.get("type"):
            return self.gateway.get_object(str(created["type"]), str(created["id"]))
        updated_id = payload.get("updatedId")
        if updated_id and candidate.target_snapshots:
            return self.gateway.get_object(candidate.target_snapshots[0].object_type, str(updated_id))
        return None


def _single_proposal_item_id(body: dict[str, Any]) -> str | None:
    proposal = body.get("item")
    if not isinstance(proposal, dict):
        return None
    items = proposal.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return None
    item_id = items[0].get("id")
    return str(item_id) if item_id else None


def _require_target_type(candidate: ResearchReturnCandidateRecord, expected: str) -> None:
    if len(candidate.target_snapshots) != 1:
        raise FormalHandoffStateError(f"formal {candidate.intent} requires one target snapshot")
    actual = candidate.target_snapshots[0].object_type
    if actual != expected:
        raise FormalHandoffStateError(
            f"{candidate.intent} requires target object_type={expected}, got {actual}"
        )


def _candidate_epistemic_state(candidate: ResearchReturnCandidateRecord, result: ResultEnvelope) -> str:
    claims = {claim.id: claim for claim in result.claims}
    states = [claims[item].epistemic_state for item in candidate.source_claim_ids if item in claims]
    if not states:
        return "hypothesis"
    priority = ["uncertain", "hypothesis", "inference", "contradicted", "supported"]
    state = min(states, key=lambda value: priority.index(value) if value in priority else 0)
    mapping = {
        "supported": "inference",
        "inference": "inference",
        "hypothesis": "hypothesis",
        "uncertain": "unknown",
        "contradicted": "counterexample",
    }
    return mapping[state]


def _candidate_confidence(candidate: ResearchReturnCandidateRecord, result: ResultEnvelope) -> str:
    claims = {claim.id: claim for claim in result.claims}
    states = [claims[item].epistemic_state for item in candidate.source_claim_ids if item in claims]
    if not states:
        return "low"
    if any(state in {"uncertain", "hypothesis"} for state in states):
        return "low"
    return "medium"


def _evidence_markdown(chunk_ids: list[str], evidence: list[TaskPackEvidence]) -> str:
    by_id = {item.chunk_id: item for item in evidence}
    lines: list[str] = []
    for chunk_id in chunk_ids:
        item = by_id.get(chunk_id)
        if item is None:
            raise FormalHandoffStateError(f"candidate evidence is missing from TaskPack: {chunk_id}")
        heading = " > ".join(item.heading_path) if item.heading_path else (item.title or item.document_id)
        line_range = ""
        if item.start_line is not None or item.end_line is not None:
            line_range = f" · L{item.start_line or '?'}-L{item.end_line or '?'}"
        lines.append(f"- `{item.chunk_id}` · {item.document_id} · {heading}{line_range}")
        if item.excerpt:
            lines.append(f"  - 摘要：{item.excerpt}")
    return "\n".join(lines) if lines else "（无直接 Evidence 引用）"


def _source_markdown(candidate: ResearchReturnCandidateRecord, result: ResultEnvelope) -> str:
    return (
        f"- TaskPack：`{candidate.task_id}`\n"
        f"- Return candidate：`{candidate.candidate_id}`\n"
        f"- Intent：`{candidate.intent}`\n"
        f"- Result generated_at：{result.generated_at}\n"
        f"- 差异理由：{candidate.reason}"
    )


def _truncate(text: str, limit: int = 72) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
