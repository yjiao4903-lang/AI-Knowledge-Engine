"""Research context snapshot support for dossier-backed TaskPacks (DL-03A).

The browser selects stable identities. KE re-resolves Cognition objects from the
read-only derived catalog and builds an immutable task snapshot. The snapshot is
research context only: factual claims still require `evidence.jsonl` grounding.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.contracts.cognition import CognitionContextItem
from app.storage.repositories.knowledge import ChunkRepository, DocumentRepository

RESEARCH_CONTEXT_SCHEMA_VERSION = "1.0"


def resolve_cognition_context(
    cfg,
    cognition_conn,
    object_ids: Iterable[str],
    *,
    legacy_items: Iterable[CognitionContextItem] = (),
) -> list[CognitionContextItem]:
    """Resolve selected stable IDs from the authoritative derived Cognition catalog.

    `legacy_items` exists only for request compatibility. Their object IDs/type
    hints may be reused, but client-supplied title/excerpt/hash are deliberately
    ignored and re-read from the catalog.
    """

    legacy_by_id = {item.object_id: item for item in legacy_items}
    ids: list[str] = []
    seen: set[str] = set()
    for raw in [*object_ids, *legacy_by_id]:
        value = (raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            ids.append(value)
    if not ids:
        return []
    if cognition_conn is None:
        raise ValueError("Cognition catalog unavailable; cannot resolve selected objects")

    docs = DocumentRepository(cognition_conn)
    chunks = ChunkRepository(cognition_conn)
    resolved: list[CognitionContextItem] = []
    for index, object_id in enumerate(ids, start=1):
        doc = docs.get(object_id)
        if doc is None:
            raise ValueError(f"cognition object not found: {object_id}")
        old = legacy_by_id.get(object_id)
        object_type = _infer_object_type(
            cfg.cognition.root,
            doc.get("source_path"),
            old.object_type if old is not None else None,
        )
        resolved.append(
            CognitionContextItem(
                context_id=f"CTX{index:03d}",
                object_type=object_type,
                object_id=object_id,
                content_hash=doc.get("sha256"),
                title=doc.get("title") or doc.get("file_name") or object_id,
                excerpt=_join_excerpt(chunks.list_for_document(object_id), 6000),
            )
        )
    return resolved


def build_research_context(
    dossier_detail: dict,
    *,
    task_type: str,
    query: str,
    evidence_context_mode: str,
    selected_cognition: list[CognitionContextItem],
    max_sources: int = 24,
    excerpt_chars: int = 1200,
) -> dict:
    """Create a bounded, explainable three-layer research-context snapshot."""

    definition = dossier_detail["dossier"]
    source_rows: list[dict] = []
    groups = (
        ("topic", "topic"),
        ("questions", "question"),
        ("judgments", "judgment"),
        ("other_cognition", "other_cognition"),
        ("evidence", "evidence"),
    )
    for bucket, role in groups:
        for source in dossier_detail.get("sources", {}).get(bucket, []):
            if role == "evidence":
                source_id = source.get("chunk_id")
                source_kind = "report_evidence"
            else:
                source_id = source.get("object_id")
                source_kind = "cognition"
            source_rows.append(
                {
                    "source_kind": source_kind,
                    "role": role,
                    "source_id": source_id,
                    "title": source.get("title"),
                    "content_hash": source.get("content_hash"),
                    "missing": bool(source.get("missing")),
                    "excerpt": (source.get("excerpt") or "")[:excerpt_chars],
                }
            )

    kept = source_rows[:max_sources]
    omitted = [row.get("source_id") for row in source_rows[max_sources:] if row.get("source_id")]
    warnings: list[str] = []
    if dossier_detail.get("needs_refresh"):
        warnings.append("DOSSIER_SOURCE_VERSION_CHANGED")
    if any(row["missing"] for row in kept):
        warnings.append("DOSSIER_SOURCE_MISSING")
    if omitted:
        warnings.append("DOSSIER_CONTEXT_BUDGET_OMITTED_SOURCES")

    return {
        "schema_version": RESEARCH_CONTEXT_SCHEMA_VERSION,
        "generated_at": _now(),
        "direction": {
            "dossier_id": definition["dossier_id"],
            "title": definition["title"],
            "direction": definition.get("direction") or "",
            "scope_include": definition.get("scope_include") or [],
            "scope_exclude": definition.get("scope_exclude") or [],
        },
        "topic_state": {
            "formal_topic_bound": dossier_detail.get("formal_topic_bound", False),
            "planning_only": dossier_detail.get("planning_only", True),
            "dossier_updated_at": definition.get("updated_at"),
            "needs_refresh": dossier_detail.get("needs_refresh", False),
            "source_changes": dossier_detail.get("source_changes") or [],
            "source_versions": dossier_detail.get("source_versions") or {},
            "sources": kept,
            "omitted_sources": omitted,
        },
        "task": {
            "task_id": None,
            "task_type": task_type,
            "query": query,
            "evidence_context_mode": evidence_context_mode,
            "selected_cognition_object_ids": [item.object_id for item in selected_cognition],
            "allow_network": False,
            "allow_external_sources": False,
        },
        "warnings": warnings,
    }


def render_research_brief(context: dict) -> str:
    """Render the human entry point without turning context into evidence."""

    direction = context["direction"]
    topic = context["topic_state"]
    task = context["task"]
    lines = [
        "# Research Brief",
        "",
        "> 本文件用于理解研究方向与任务边界，不是事实证据。事实性 claim 必须引用 `evidence.jsonl`。",
        "",
        "## 1. 长期研究方向",
        "",
        f"- Dossier: `{direction['dossier_id']}`",
        f"- 主题: {direction['title']}",
        f"- 方向: {direction.get('direction') or '未填写'}",
        f"- 纳入范围: {_list_text(direction.get('scope_include'))}",
        f"- 排除范围: {_list_text(direction.get('scope_exclude'))}",
        "",
        "## 2. 主题当前状态",
        "",
        f"- 正式 Topic 已绑定: {'是' if topic.get('formal_topic_bound') else '否'}",
        f"- Planning-only: {'是' if topic.get('planning_only') else '否'}",
        f"- Dossier 更新时间: {topic.get('dossier_updated_at') or '未知'}",
        f"- 来源需要复核: {'是' if topic.get('needs_refresh') else '否'}",
    ]
    warnings = context.get("warnings") or []
    if warnings:
        lines.append(f"- 警告: {', '.join(warnings)}")
    lines.extend(["", "### 当前来源投影（上下文，不是 Evidence）", ""])
    for row in topic.get("sources") or []:
        title = row.get("title") or row.get("source_id") or "未命名来源"
        status = "MISSING" if row.get("missing") else "available"
        lines.append(
            f"- [{row.get('role')}] {title} (`{row.get('source_id')}`; {status}; hash={row.get('content_hash') or 'unknown'})"
        )
        excerpt = (row.get("excerpt") or "").strip().replace("\n", " ")
        if excerpt:
            lines.append(f"  - 快照: {excerpt}")
    if topic.get("omitted_sources"):
        lines.append(f"- 因上下文预算未展开: {', '.join(topic['omitted_sources'])}")

    lines.extend(
        [
            "",
            "## 3. 本次任务",
            "",
            f"- Task ID: `{task.get('task_id') or 'pending'}`",
            f"- 类型: `{task['task_type']}`",
            f"- 目标: {task['query']}",
            f"- Evidence 扩展模式: `{task['evidence_context_mode']}`",
            f"- 已选择 Cognition 对象: {_list_text(task.get('selected_cognition_object_ids'))}",
            "- 外部联网: 禁止",
            "- TaskPack 外部来源: 禁止",
            "",
            "## 4. 证据纪律",
            "",
            "- `research_brief.md` / `research_context.json` 仅用于研究背景、范围与已有认识定位。",
            "- `cognition_context.jsonl`（如存在）是所选正式认知的只读快照，不自动成为事实证据。",
            "- 事实性结论只能由 `evidence.jsonl` 中的 chunk 支撑，并逐字引用其 `chunk_id`。",
            "- 如果上下文与 Evidence 冲突，必须报告冲突，不得用上下文覆盖 Evidence。",
            "",
        ]
    )
    return "\n".join(lines)


def _infer_object_type(root: str, source_path: str | None, fallback: str | None) -> str:
    bucket = None
    if source_path:
        try:
            rel = Path(source_path).resolve().relative_to(Path(root).resolve())
            bucket = rel.parts[0] if rel.parts else None
        except Exception:
            bucket = None
    mapping = {
        "03_问题池": "question",
        "04_判断台账": "judgment",
        "05_主题页": "topic",
        "06_研究项目": "project",
        "07_复盘": "review",
        "02_来源与阅读": "source_note",
    }
    return mapping.get(bucket) or fallback or "cognition_object"


def _join_excerpt(chunks: list[dict], limit: int) -> str:
    text = "\n\n".join((item.get("plain_text") or "").strip() for item in chunks).strip()
    return text[:limit]


def _list_text(values) -> str:
    values = values or []
    return "；".join(str(item) for item in values) if values else "未指定"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
