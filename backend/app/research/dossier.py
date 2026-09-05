"""Model-free Topic Research Dossier projection (DL-02A).

A dossier is KE-owned research-planning metadata, not formal cognition. It stores
user-authored direction/scope plus stable references to formal Cognition objects
and report Evidence. Formal text is re-resolved from the read-only catalogs on
every read. A saved source-version snapshot makes later changes explainable.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.synthesis.grounding import EvidenceResolver
from app.synthesis.schemas import EvidenceRef
from app.storage.repositories.knowledge import ChunkRepository, DocumentRepository

DOSSIER_SCHEMA_VERSION = "1.0"
_DOSSIER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class DossierDefinition(BaseModel):
    schema_version: str = DOSSIER_SCHEMA_VERSION
    dossier_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    direction: str = Field(default="", max_length=4000)
    scope_include: list[str] = Field(default_factory=list)
    scope_exclude: list[str] = Field(default_factory=list)
    topic_object_id: str | None = None
    question_ids: list[str] = Field(default_factory=list)
    judgment_ids: list[str] = Field(default_factory=list)
    other_cognition_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    updated_at: str


class DossierUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    direction: str = Field(default="", max_length=4000)
    scope_include: list[str] = Field(default_factory=list, max_length=50)
    scope_exclude: list[str] = Field(default_factory=list, max_length=50)
    topic_object_id: str | None = None
    question_ids: list[str] = Field(default_factory=list, max_length=100)
    judgment_ids: list[str] = Field(default_factory=list, max_length=100)
    other_cognition_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)


class DossierStore:
    """Small durable file store for KE-owned planning metadata."""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir) / "research_dossiers"

    def _dir(self, dossier_id: str) -> Path:
        if not _DOSSIER_ID_RE.fullmatch(dossier_id):
            raise ValueError("invalid dossier_id; use letters, numbers, '.', '_' or '-'")
        return self.root / dossier_id

    def load_definition(self, dossier_id: str) -> DossierDefinition | None:
        path = self._dir(dossier_id) / "definition.json"
        if not path.exists():
            return None
        return DossierDefinition.model_validate_json(path.read_text(encoding="utf-8"))

    def load_saved_snapshot(self, dossier_id: str) -> dict | None:
        path = self._dir(dossier_id) / "snapshot.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_definitions(self) -> list[DossierDefinition]:
        if not self.root.exists():
            return []
        result: list[DossierDefinition] = []
        for path in sorted(self.root.glob("*/definition.json")):
            try:
                result.append(
                    DossierDefinition.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        return sorted(result, key=lambda item: item.updated_at, reverse=True)

    def save(self, definition: DossierDefinition, snapshot: dict) -> None:
        directory = self._dir(definition.dossier_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_json(directory / "definition.json", definition.model_dump(mode="json"))
        self._atomic_json(directory / "snapshot.json", snapshot)

    @staticmethod
    def _atomic_json(path: Path, payload: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(path)


class TopicDossierService:
    """Resolve dossiers from authoritative report/Cognition catalogs."""

    def __init__(self, cfg, report_conn, cognition_conn) -> None:
        self.cfg = cfg
        self.store = DossierStore(cfg.paths.data_dir)
        self._report_docs = DocumentRepository(report_conn)
        self._cognition_docs = (
            DocumentRepository(cognition_conn) if cognition_conn is not None else None
        )
        self._cognition_chunks = (
            ChunkRepository(cognition_conn) if cognition_conn is not None else None
        )
        self._evidence = EvidenceResolver(cfg, report_conn, cognition_conn)

    def list_dossiers(self) -> list[dict]:
        return [
            {
                "dossier_id": item.dossier_id,
                "title": item.title,
                "direction": item.direction,
                "formal_topic_bound": bool(item.topic_object_id),
                "updated_at": item.updated_at,
            }
            for item in self.store.list_definitions()
        ]

    def upsert(self, dossier_id: str, body: DossierUpsert) -> dict:
        self.store._dir(dossier_id)
        definition = DossierDefinition(
            dossier_id=dossier_id,
            title=body.title.strip(),
            direction=body.direction.strip(),
            scope_include=_dedupe(body.scope_include),
            scope_exclude=_dedupe(body.scope_exclude),
            topic_object_id=_optional_text(body.topic_object_id),
            question_ids=_dedupe(body.question_ids),
            judgment_ids=_dedupe(body.judgment_ids),
            other_cognition_ids=_dedupe(body.other_cognition_ids),
            evidence_refs=_dedupe_evidence(body.evidence_refs),
            updated_at=_now(),
        )
        # Explicit save is strict: stale or absent references are rejected before
        # any planning metadata is persisted.
        current = self._project(definition, strict=True)
        saved_snapshot = {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "dossier_id": dossier_id,
            "saved_at": _now(),
            "source_versions": current["source_versions"],
            "sources": current["sources"],
        }
        self.store.save(definition, saved_snapshot)
        return self.get(dossier_id)

    def get(self, dossier_id: str) -> dict:
        definition = self.store.load_definition(dossier_id)
        if definition is None:
            raise KeyError(dossier_id)
        current = self._project(definition, strict=False)
        saved = self.store.load_saved_snapshot(dossier_id)
        saved_versions = (saved or {}).get("source_versions", {})
        changes = _compare_versions(saved_versions, current["source_versions"])
        return {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "dossier": definition.model_dump(mode="json"),
            "formal_topic_bound": bool(definition.topic_object_id),
            "planning_only": not bool(definition.topic_object_id),
            "generated_at": _now(),
            "semantic_required": False,
            "needs_refresh": bool(changes),
            "source_changes": changes,
            "sources": current["sources"],
            "source_versions": current["source_versions"],
            "last_saved_snapshot": saved,
        }

    def _project(self, definition: DossierDefinition, *, strict: bool) -> dict:
        sources = {
            "topic": [],
            "questions": [],
            "judgments": [],
            "other_cognition": [],
            "evidence": [],
        }
        versions: dict[str, str | None] = {}

        cognition_refs: list[tuple[str, str, str]] = []
        if definition.topic_object_id:
            cognition_refs.append(("topic", "topic", definition.topic_object_id))
        cognition_refs.extend(("questions", "question", item) for item in definition.question_ids)
        cognition_refs.extend(("judgments", "judgment", item) for item in definition.judgment_ids)
        cognition_refs.extend(
            ("other_cognition", "other", item) for item in definition.other_cognition_ids
        )

        for bucket, role, object_id in cognition_refs:
            item = self._resolve_cognition(object_id, role)
            key = f"cognition:{object_id}"
            if item is None:
                if strict:
                    raise ValueError(f"cognition object not found: {object_id}")
                sources[bucket].append(
                    {"object_id": object_id, "role": role, "missing": True}
                )
                versions[key] = None
            else:
                sources[bucket].append(item)
                versions[key] = item["content_hash"]

        for ref in definition.evidence_refs:
            item = self._resolve_evidence(ref, verify_hash=strict)
            key = f"evidence:{ref.chunk_id}"
            if item is None:
                if strict:
                    raise ValueError(f"evidence chunk not found or stale: {ref.chunk_id}")
                sources["evidence"].append({"chunk_id": ref.chunk_id, "missing": True})
                versions[key] = None
            else:
                sources["evidence"].append(item)
                versions[key] = item["content_hash"]

        return {"sources": sources, "source_versions": versions}

    def _resolve_cognition(self, object_id: str, role: str) -> dict | None:
        if self._cognition_docs is None or self._cognition_chunks is None:
            return None
        doc = self._cognition_docs.get(object_id)
        if doc is None:
            return None
        chunks = self._cognition_chunks.list_for_document(object_id)
        return {
            "object_id": object_id,
            "role": role,
            "title": doc.get("title") or doc.get("file_name") or object_id,
            "content_hash": doc.get("sha256"),
            "indexed_at": doc.get("indexed_at"),
            "source_bucket": _source_bucket(
                self.cfg.cognition.root, doc.get("source_path")
            ),
            "excerpt": _join_excerpt(chunks, 6000),
            "missing": False,
        }

    def _resolve_evidence(self, ref: EvidenceRef, *, verify_hash: bool) -> dict | None:
        # At save time the caller's hash is checked. On later reads, stable
        # chunk_id resolves the current authoritative version so a changed hash is
        # reported as `changed`, not incorrectly collapsed into `missing`.
        try:
            chunk = self._evidence.load_chunk(
                ref.chunk_id, ref.content_hash if verify_hash else None
            )
        except Exception:
            return None
        doc = self._report_docs.get(chunk.get("document_id") or ref.document_id) or {}
        return {
            "source_type": ref.source_type,
            "document_id": chunk.get("document_id") or ref.document_id,
            "section_id": chunk.get("section_id"),
            "chunk_id": ref.chunk_id,
            "content_hash": chunk.get("content_hash"),
            "title": doc.get("title") or ref.title or ref.document_id,
            "heading_path": chunk.get("heading_path") or ref.heading_path,
            "start_line": chunk.get("start_line"),
            "end_line": chunk.get("end_line"),
            "excerpt": (
                chunk.get("plain_text") or chunk.get("raw_markdown") or ""
            )[:4000],
            "missing": False,
        }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_evidence(values: list[EvidenceRef]) -> list[EvidenceRef]:
    result: list[EvidenceRef] = []
    seen: set[str] = set()
    for value in values:
        if value.chunk_id not in seen:
            seen.add(value.chunk_id)
            result.append(value)
    return result


def _join_excerpt(chunks: list[dict], limit: int) -> str:
    text = "\n\n".join(
        (item.get("plain_text") or "").strip() for item in chunks
    ).strip()
    return text[:limit]


def _source_bucket(root: str, source_path: str | None) -> str | None:
    if not source_path:
        return None
    try:
        rel = Path(source_path).resolve().relative_to(Path(root).resolve())
    except Exception:
        return None
    return rel.parts[0] if rel.parts else None


def _compare_versions(
    saved: dict[str, str | None], current: dict[str, str | None]
) -> list[dict]:
    changes: list[dict] = []
    for key in sorted(set(saved) | set(current)):
        before = saved.get(key)
        after = current.get(key)
        if before == after:
            continue
        if key not in current or after is None:
            kind: Literal["missing", "changed", "new"] = "missing"
        elif key not in saved:
            kind = "new"
        else:
            kind = "changed"
        changes.append(
            {"source": key, "change": kind, "saved": before, "current": after}
        )
    return changes
