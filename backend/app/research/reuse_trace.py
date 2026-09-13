"""Read-only Cognition research-history / reuse trace derived from durable artifacts.

DL-08K1 deliberately reconstructs history at read time.  It never mutates a
TaskPack, Cognition Markdown/SQLite, or invokes a Worker/model/Cognition API.
Exact KE ``cog:<relpath>`` identity is the reverse-index key; a Cognition UUID is
reported only when an existing formal-handoff marker already records that bridge.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml

from app.contracts.cognition import CognitionContextItem
from app.research.return_candidates import ResearchReturnBatchRecord
from app.storage.repositories.knowledge import DocumentRepository
from app.taskpack.schemas import ResultEnvelope, TaskYaml

_TASKPACK_DIRS = ("outbox", "processing", "completed", "failed", "archive")
_RETURN_CANDIDATES = Path("result") / "return_candidates.json"
_FORMAL_HANDOFFS = Path("result") / "formal_handoffs"
_RESULT = Path("result") / "result.json"
_IMPORTED = Path("result") / "IMPORTED"
_INVALID = Path("result") / "INVALID"
_FORMAL_HANDOFF_SCHEMA_VERSION = "1.0"

_COGNITION_DIR_TYPES = {
    "02_来源与阅读": "source",
    "03_问题池": "question",
    "04_判断台账": "judgment",
    "05_主题页": "topic",
    "06_研究项目": "research_project",
    "07_复盘": "review",
}


class ReuseTraceReadService:
    """Reconstruct one exact Cognition object's durable research history."""

    def __init__(self, cfg, cognition_conn=None) -> None:
        self.cfg = cfg
        self.root = Path(cfg.taskpack.root_dir)
        self.cognition_docs = (
            DocumentRepository(cognition_conn) if cognition_conn is not None else None
        )

    def build(self, object_id: str) -> dict[str, Any]:
        if not isinstance(object_id, str) or object_id == "":
            raise ValueError("object_id must be a non-empty exact KE Cognition id")

        quality: list[dict[str, Any]] = []
        task_uses: list[dict[str, Any]] = []
        return_events: list[dict[str, Any]] = []
        linked_packs: dict[str, Path] = {}
        task_meta_cache: dict[Path, tuple[TaskYaml | None, list[dict[str, Any]]]] = {}

        for pack in self._iter_packs():
            task_id = pack.name
            context_rows, context_issues, context_exists = self._read_context(pack)
            matching_context = [row for row in context_rows if row.object_id == object_id]

            batch, candidate_issues, candidate_exists = self._read_candidates(pack)
            matching_candidates = (
                [
                    row
                    for row in batch.candidates
                    if object_id in row.target_cognition_object_ids
                ]
                if batch is not None
                else []
            )

            if not matching_context and not matching_candidates:
                continue

            linked_packs[task_id] = pack
            task, task_issues = self._read_task(pack)
            task_meta_cache[pack] = (task, task_issues)
            quality.extend(self._bind_issues(task_id, None, task_issues))
            quality.extend(self._bind_issues(task_id, None, context_issues))
            quality.extend(self._bind_issues(task_id, None, candidate_issues))
            quality.extend(self._invalid_marker_issues(pack))

            if matching_candidates and not context_exists:
                quality.append(
                    self._quality(
                        "cognition_context_missing",
                        "candidate targets the object but cognition_context.jsonl is missing",
                        task_id=task_id,
                        artifact="cognition_context.jsonl",
                    )
                )

            for context in matching_context:
                task_uses.append(
                    {
                        "task_id": task_id,
                        "task_type": task.task_type if task is not None else None,
                        "created_at": task.created_at if task is not None else None,
                        "query": task.query if task is not None else None,
                        "context_id": context.context_id,
                        "context_object_type": context.object_type,
                        "context_snapshot_hash": context.content_hash,
                        "context_schema_version": context.schema_version,
                        "role": "cognition_context",
                    }
                )

            for candidate in matching_candidates:
                event, marker_issues = self._return_event(pack, candidate, object_id)
                return_events.append(event)
                quality.extend(
                    self._bind_issues(task_id, candidate.candidate_id, marker_issues)
                )

        unresolved_questions: list[dict[str, Any]] = []
        for task_id, pack in linked_packs.items():
            task, task_issues = task_meta_cache.get(pack, self._read_task(pack))
            if task_issues and pack not in task_meta_cache:
                quality.extend(self._bind_issues(task_id, None, task_issues))

            gate_proven = self._durable_gate_proven(pack)
            result_path = pack / _RESULT
            if not gate_proven:
                if result_path.exists():
                    quality.append(
                        self._quality(
                            "result_gate_unproven",
                            "local result exists but no durable artifact proves it passed the Importer Gate; unresolved questions omitted",
                            task_id=task_id,
                            artifact="result/result.json",
                        )
                    )
                continue

            result, result_issue = self._read_result(pack)
            if result_issue is not None:
                quality.append(self._bind_issue(task_id, None, result_issue))
                continue
            assert result is not None
            created_at = task.created_at if task is not None else result.generated_at
            for index, question in enumerate(result.open_questions):
                unresolved_questions.append(
                    {
                        "task_id": task_id,
                        "created_at": created_at,
                        "kind": "open_question",
                        "index": index,
                        "question": question,
                        "reason": None,
                    }
                )
            for index, item in enumerate(result.additional_evidence_needed):
                unresolved_questions.append(
                    {
                        "task_id": task_id,
                        "created_at": created_at,
                        "kind": "additional_evidence_needed",
                        "index": index,
                        "question": item.question,
                        "reason": item.reason,
                    }
                )

        current_object = self._current_object(object_id, quality)
        task_uses.sort(
            key=lambda row: (
                row.get("created_at") or "",
                row["task_id"],
                row.get("context_id") or "",
            )
        )
        return_events.sort(
            key=lambda row: (
                row.get("created_at") or "",
                row["task_id"],
                row["candidate_id"],
            )
        )
        unresolved_questions.sort(
            key=lambda row: (
                row.get("created_at") or "",
                row["task_id"],
                row["kind"],
                row["index"],
            )
        )
        quality = self._stable_quality(quality)

        return {
            "object": current_object,
            "task_uses": task_uses,
            "return_events": return_events,
            "unresolved_questions": unresolved_questions,
            "quality": {
                "issue_count": len(quality),
                "issues": quality,
            },
        }

    def _iter_packs(self):
        for subdir in _TASKPACK_DIRS:
            base = self.root / subdir
            if not base.is_dir():
                continue
            for pack in sorted(base.iterdir(), key=lambda path: path.name):
                if pack.is_dir():
                    yield pack

    @staticmethod
    def _read_task(pack: Path) -> tuple[TaskYaml | None, list[dict[str, Any]]]:
        path = pack / "task.yaml"
        if not path.exists():
            return None, [
                ReuseTraceReadService._quality(
                    "task_metadata_missing",
                    "task.yaml is missing",
                    artifact="task.yaml",
                )
            ]
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            task = TaskYaml.model_validate(raw)
        except Exception as exc:
            return None, [
                ReuseTraceReadService._quality(
                    "task_metadata_unreadable",
                    f"task.yaml cannot be parsed: {type(exc).__name__}: {exc}",
                    artifact="task.yaml",
                )
            ]
        issues: list[dict[str, Any]] = []
        if task.task_id != pack.name:
            issues.append(
                ReuseTraceReadService._quality(
                    "task_id_mismatch",
                    f"task.yaml task_id={task.task_id!r} differs from directory {pack.name!r}",
                    artifact="task.yaml",
                )
            )
        return task, issues

    @staticmethod
    def _read_context(
        pack: Path,
    ) -> tuple[list[CognitionContextItem], list[dict[str, Any]], bool]:
        path = pack / "cognition_context.jsonl"
        if not path.exists():
            return [], [], False
        rows: list[CognitionContextItem] = []
        issues: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            return [], [
                ReuseTraceReadService._quality(
                    "cognition_context_unreadable",
                    f"cognition_context.jsonl cannot be read: {type(exc).__name__}: {exc}",
                    artifact="cognition_context.jsonl",
                )
            ], True
        for lineno, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                rows.append(CognitionContextItem.model_validate_json(line))
            except Exception as exc:
                issues.append(
                    ReuseTraceReadService._quality(
                        "cognition_context_unreadable",
                        f"line {lineno} is invalid: {type(exc).__name__}: {exc}",
                        artifact="cognition_context.jsonl",
                    )
                )
        return rows, issues, True

    @staticmethod
    def _read_candidates(
        pack: Path,
    ) -> tuple[ResearchReturnBatchRecord | None, list[dict[str, Any]], bool]:
        path = pack / _RETURN_CANDIDATES
        if not path.exists():
            return None, [], False
        try:
            batch = ResearchReturnBatchRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            return None, [
                ReuseTraceReadService._quality(
                    "return_candidates_unreadable",
                    f"return_candidates.json cannot be parsed: {type(exc).__name__}: {exc}",
                    artifact="result/return_candidates.json",
                )
            ], True
        issues: list[dict[str, Any]] = []
        if batch.task_id != pack.name:
            issues.append(
                ReuseTraceReadService._quality(
                    "return_candidates_task_id_mismatch",
                    f"return-candidate task_id={batch.task_id!r} differs from directory {pack.name!r}",
                    artifact="result/return_candidates.json",
                )
            )
        return batch, issues, True

    def _return_event(self, pack: Path, candidate, object_id: str):
        issues: list[dict[str, Any]] = []
        snapshot = next(
            (row for row in candidate.target_snapshots if row.object_id == object_id),
            None,
        )
        if snapshot is None:
            issues.append(
                self._quality(
                    "target_snapshot_missing",
                    "candidate targets the object but has no exact durable target snapshot",
                    artifact="result/return_candidates.json",
                )
            )

        marker_path = pack / _FORMAL_HANDOFFS / f"{candidate.candidate_id}.json"
        marker_state = "missing"
        marker: dict[str, Any] | None = None
        if marker_path.exists():
            try:
                parsed = json.loads(marker_path.read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("marker root must be an object")
                marker = parsed
                marker_state = "present"
            except Exception as exc:
                marker_state = "unreadable"
                issues.append(
                    self._quality(
                        "formal_handoff_unreadable",
                        f"formal handoff marker cannot be parsed: {type(exc).__name__}: {exc}",
                        artifact=f"result/formal_handoffs/{candidate.candidate_id}.json",
                    )
                )
        else:
            issues.append(
                self._quality(
                    "formal_handoff_missing",
                    "return candidate has no formal-handoff marker; staging event remains visible",
                    artifact=f"result/formal_handoffs/{candidate.candidate_id}.json",
                )
            )

        trusted_fields = {
            "proposal_id": None,
            "proposal_item_id": None,
            "cognition_uuid": None,
            "marker_source_path": None,
            "previewed_at": None,
            "applied_at": None,
            "formal_write_performed": False,
        }
        if marker is not None:
            trusted_fields, marker_issues = self._trusted_formal_marker_fields(
                pack,
                candidate,
                object_id,
                marker,
            )
            issues.extend(marker_issues)
            if marker_issues:
                marker_state = "invalid"

        return {
            "task_id": pack.name,
            "candidate_id": candidate.candidate_id,
            "created_at": candidate.created_at,
            "result_generated_at": candidate.result_generated_at,
            "intent": candidate.intent,
            "review_status": candidate.status,
            "target_object_id": object_id,
            "target_object_ids": list(candidate.target_cognition_object_ids),
            "target_version_state": snapshot.version_state if snapshot is not None else None,
            "has_version_conflict": bool(candidate.has_version_conflict),
            "version_check_incomplete": bool(candidate.version_check_incomplete),
            "evidence_chunk_ids": list(candidate.evidence_chunk_ids),
            "source_refs": {
                "claim_ids": list(candidate.source_claim_ids),
                "tension_ids": list(candidate.source_tension_ids),
                "open_question_indexes": list(candidate.source_open_question_indexes),
                "additional_evidence_indexes": list(
                    candidate.source_additional_evidence_indexes
                ),
            },
            "formal_handoff": {
                "state": marker_state,
                **trusted_fields,
            },
        }, issues

    def _trusted_formal_marker_fields(
        self,
        pack: Path,
        candidate,
        object_id: str,
        marker: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        artifact = f"result/formal_handoffs/{candidate.candidate_id}.json"
        issues: list[dict[str, Any]] = []

        def add(code: str, detail: str) -> None:
            issues.append(self._quality(code, detail, artifact=artifact))

        if marker.get("schema_version") != _FORMAL_HANDOFF_SCHEMA_VERSION:
            add(
                "formal_handoff_schema_invalid",
                "formal marker schema_version is missing or unsupported",
            )
        if marker.get("task_id") != pack.name:
            add(
                "formal_handoff_task_id_mismatch",
                "formal marker task_id does not match TaskPack directory",
            )
        if marker.get("candidate_id") != candidate.candidate_id:
            add(
                "formal_handoff_candidate_id_mismatch",
                "formal marker candidate_id does not match staging record",
            )

        proposal_id = marker.get("proposal_id")
        proposal_item_id = marker.get("proposal_item_id")
        if not self._nonempty_string(proposal_id) or not self._nonempty_string(
            proposal_item_id
        ):
            add(
                "formal_handoff_proposal_invalid",
                "formal marker must contain non-empty proposal_id and proposal_item_id",
            )

        formal_write_performed = marker.get("formal_write_performed")
        if type(formal_write_performed) is not bool:
            add(
                "formal_write_flag_invalid",
                "formal_write_performed must be a literal boolean",
            )

        preview = marker.get("preview")
        preview_valid = preview is None or self._valid_preview(preview)
        if not preview_valid:
            add(
                "formal_handoff_preview_invalid",
                "formal marker preview is not a valid durable Preview record",
            )

        apply = marker.get("apply")
        apply_valid = apply is None or self._valid_apply(apply)
        if not apply_valid:
            add(
                "formal_handoff_apply_invalid",
                "formal marker apply is not a valid durable Apply record",
            )
        if apply is not None and preview is None:
            add(
                "formal_handoff_apply_without_preview",
                "formal marker records Apply without a prior Preview",
            )
        if formal_write_performed is True and not (
            isinstance(apply, dict) and self._valid_apply(apply)
        ):
            add(
                "formal_handoff_apply_required",
                "formal_write_performed=true requires a valid Apply record",
            )
        if formal_write_performed is False and apply is not None:
            add(
                "formal_handoff_apply_flag_mismatch",
                "an Apply record cannot coexist with formal_write_performed=false",
            )

        identity = self._trusted_identity_mapping(
            candidate,
            object_id,
            marker.get("target_identities"),
            artifact,
            issues,
        )

        if issues:
            return {
                "proposal_id": None,
                "proposal_item_id": None,
                "cognition_uuid": None,
                "marker_source_path": None,
                "previewed_at": None,
                "applied_at": None,
                "formal_write_performed": False,
            }, issues

        assert isinstance(preview, (dict, type(None)))
        assert isinstance(apply, (dict, type(None)))
        assert type(formal_write_performed) is bool
        assert identity is not None
        return {
            "proposal_id": proposal_id,
            "proposal_item_id": proposal_item_id,
            "cognition_uuid": identity["cognition_target_id"],
            "marker_source_path": identity["source_path"],
            "previewed_at": preview.get("previewed_at") if preview is not None else None,
            "applied_at": apply.get("applied_at") if apply is not None else None,
            "formal_write_performed": formal_write_performed,
        }, []

    def _trusted_identity_mapping(
        self,
        candidate,
        object_id: str,
        identities: Any,
        artifact: str,
        issues: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        if not isinstance(identities, list):
            issues.append(
                self._quality(
                    "formal_identity_mapping_unreadable",
                    "formal marker target_identities is not a list",
                    artifact=artifact,
                )
            )
            return None

        valid_rows: list[dict[str, str]] = []
        malformed = False
        for row in identities:
            if not isinstance(row, dict):
                malformed = True
                continue
            ke_target_id = row.get("ke_target_id")
            cognition_target_id = row.get("cognition_target_id")
            object_type = row.get("object_type")
            source_path = row.get("source_path")
            if not all(
                self._nonempty_string(value)
                for value in (
                    ke_target_id,
                    cognition_target_id,
                    object_type,
                    source_path,
                )
            ):
                malformed = True
                continue
            try:
                uuid.UUID(cognition_target_id)
            except (ValueError, AttributeError, TypeError):
                malformed = True
                continue
            valid_rows.append(
                {
                    "ke_target_id": ke_target_id,
                    "cognition_target_id": cognition_target_id,
                    "object_type": object_type,
                    "source_path": source_path,
                }
            )

        if malformed:
            issues.append(
                self._quality(
                    "formal_identity_mapping_unreadable",
                    "formal marker contains malformed target identity rows",
                    artifact=artifact,
                )
            )

        row_ids = [row["ke_target_id"] for row in valid_rows]
        if len(row_ids) != len(set(row_ids)):
            issues.append(
                self._quality(
                    "formal_identity_mapping_ambiguous",
                    "formal marker contains duplicate exact KE identity mappings",
                    artifact=artifact,
                )
            )

        expected_ids = list(candidate.target_cognition_object_ids)
        if sorted(row_ids) != sorted(expected_ids):
            issues.append(
                self._quality(
                    "formal_identity_mapping_mismatch",
                    "formal marker target identities do not exactly match the reviewed candidate targets",
                    artifact=artifact,
                )
            )

        matches = [row for row in valid_rows if row["ke_target_id"] == object_id]
        if len(matches) != 1:
            issues.append(
                self._quality(
                    "formal_identity_mapping_missing"
                    if not matches
                    else "formal_identity_mapping_ambiguous",
                    "formal marker must contain exactly one mapping for the queried exact KE identity",
                    artifact=artifact,
                )
            )
            return None
        return matches[0]

    @staticmethod
    def _nonempty_string(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @classmethod
    def _valid_preview(cls, preview: Any) -> bool:
        return (
            isinstance(preview, dict)
            and cls._nonempty_string(preview.get("previewed_at"))
            and isinstance(preview.get("target_hashes"), dict)
            and isinstance(preview.get("response"), dict)
        )

    @classmethod
    def _valid_apply(cls, apply: Any) -> bool:
        return (
            isinstance(apply, dict)
            and cls._nonempty_string(apply.get("applied_at"))
            and isinstance(apply.get("response"), dict)
            and "readback" in apply
            and (apply.get("readback") is None or isinstance(apply.get("readback"), dict))
        )

    @staticmethod
    def _read_result(pack: Path):
        path = pack / _RESULT
        if not path.exists():
            return None, ReuseTraceReadService._quality(
                "result_missing",
                "Gate-proven task has no result/result.json",
                artifact="result/result.json",
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            result = ResultEnvelope.model_validate(raw)
        except Exception as exc:
            return None, ReuseTraceReadService._quality(
                "result_unreadable",
                f"Gate-proven result cannot be parsed: {type(exc).__name__}: {exc}",
                artifact="result/result.json",
            )
        if result.task_id != pack.name:
            return None, ReuseTraceReadService._quality(
                "result_task_id_mismatch",
                f"result task_id={result.task_id!r} differs from directory {pack.name!r}",
                artifact="result/result.json",
            )
        return result, None

    @staticmethod
    def _durable_gate_proven(pack: Path) -> bool:
        if (pack / _INVALID).exists():
            return False
        return (pack / _IMPORTED).exists()

    def _current_object(
        self,
        object_id: str,
        quality: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.cognition_docs is None:
            quality.append(
                self._quality(
                    "current_catalog_unavailable",
                    "derived Cognition catalog is unavailable; history is still reconstructed from TaskPacks",
                    artifact="cognition_catalog",
                )
            )
            return {
                "object_id": object_id,
                "resolved": False,
                "object_type": None,
                "title": None,
                "content_hash": None,
            }

        row = self.cognition_docs.get(object_id)
        if row is None:
            quality.append(
                self._quality(
                    "current_object_unresolved",
                    "exact KE Cognition id is not present in the current derived catalog",
                    artifact="cognition_catalog",
                )
            )
            return {
                "object_id": object_id,
                "resolved": False,
                "object_type": None,
                "title": None,
                "content_hash": None,
            }

        return {
            "object_id": object_id,
            "resolved": True,
            "object_type": self._object_type_from_source_path(row.get("source_path")),
            "title": row.get("title"),
            "content_hash": row.get("sha256"),
        }

    def _object_type_from_source_path(self, source_path: Any) -> str | None:
        if not isinstance(source_path, str) or not source_path:
            return None
        try:
            rel = Path(source_path).relative_to(Path(self.cfg.cognition.root))
        except (ValueError, TypeError):
            return None
        if not rel.parts:
            return None
        return _COGNITION_DIR_TYPES.get(rel.parts[0])

    @staticmethod
    def _invalid_marker_issues(pack: Path) -> list[dict[str, Any]]:
        path = pack / _INVALID
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [
                ReuseTraceReadService._quality(
                    "invalid_marker_unreadable",
                    f"result/INVALID cannot be parsed: {type(exc).__name__}: {exc}",
                    task_id=pack.name,
                    artifact="result/INVALID",
                )
            ]
        stale = bool(raw.get("stale")) if isinstance(raw, dict) else False
        reason = raw.get("reason") if isinstance(raw, dict) else None
        return [
            ReuseTraceReadService._quality(
                "task_stale_result" if stale else "task_invalid_result",
                str(reason or "TaskPack carries result/INVALID"),
                task_id=pack.name,
                artifact="result/INVALID",
            )
        ]

    @staticmethod
    def _quality(
        code: str,
        detail: str,
        *,
        task_id: str | None = None,
        candidate_id: str | None = None,
        artifact: str | None = None,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "task_id": task_id,
            "candidate_id": candidate_id,
            "artifact": artifact,
            "detail": detail,
        }

    @staticmethod
    def _bind_issue(
        task_id: str,
        candidate_id: str | None,
        issue: dict[str, Any],
    ) -> dict[str, Any]:
        bound = dict(issue)
        bound["task_id"] = bound.get("task_id") or task_id
        bound["candidate_id"] = bound.get("candidate_id") or candidate_id
        return bound

    @classmethod
    def _bind_issues(
        cls,
        task_id: str,
        candidate_id: str | None,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [cls._bind_issue(task_id, candidate_id, issue) for issue in issues]

    @staticmethod
    def _stable_quality(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for issue in issues:
            key = json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            unique[key] = issue
        return sorted(
            unique.values(),
            key=lambda row: (
                row.get("task_id") or "",
                row.get("candidate_id") or "",
                row.get("code") or "",
                row.get("artifact") or "",
                row.get("detail") or "",
            ),
        )
