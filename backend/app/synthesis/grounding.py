"""证据接地（Grounding）：将 EvidenceRef 解析为可注入 Context Envelope 的正文。

L1A 硬约束：LLM 只能引用本次 Context Envelope 中显式提供的 Evidence（主计划 §9），
因此解析必须权威——正文一律按 chunk_id 从 KE catalog（SQLite）读取，不信任客户端
传入的 excerpt 快照。这样既保证 LLM 看到的是真实证据文本，也避免信任用户可控内容。

Evidence Context Expansion 同样遵守这一边界：只在 anchor chunk 的邻接 chunk 或同
section 内做 deterministic catalog expansion，并把每个扩展结果继续保留为独立
chunk_id；不会把多段正文拼成失去 Citation Identity 的匿名上下文。

`ResolvedEvidence` 内每个条目带 `ref_id`（E1..En）。Context Envelope 中用
`id=chunk_id` 呈现；模型须逐字引用 chunk_id（Citation Rules，§9）。
"""

from __future__ import annotations

import sqlite3

from app.core.config import Config
from app.core.errors import EvidenceNotFoundError, EvidenceStaleError
from app.storage.repositories.knowledge import ChunkRepository
from app.synthesis.schemas import EvidenceContextMode, EvidenceRef

# 单条证据正文注入上下文的上限（config evidence_max_chars 兜底）
_DEFAULT_MAX_CHARS = 1200


def _reading_order(chunk: dict) -> tuple[int, int, int, str]:
    """Stable document reading order independent of chunk-id naming conventions."""

    start = chunk.get("start_line")
    end = chunk.get("end_line")
    ordinal = chunk.get("ordinal")
    return (
        start if isinstance(start, int) else 10**12,
        end if isinstance(end, int) else 10**12,
        ordinal if isinstance(ordinal, int) else 10**12,
        str(chunk.get("id") or ""),
    )


class ResolvedEvidence:
    """一条已解析（带正文）的证据，供 prompt 组装。"""

    __slots__ = ("ref_id", "evidence_ref", "title", "heading_path",
                 "excerpt", "evidence_level", "content_hash")

    def __init__(
        self,
        ref_id: str,
        evidence_ref: EvidenceRef,
        chunk: dict,
        excerpt: str,
    ) -> None:
        self.ref_id = ref_id
        self.evidence_ref = evidence_ref
        self.title = chunk.get("heading_path") or evidence_ref.title or evidence_ref.document_id
        self.heading_path = chunk.get("heading_path") or ""
        self.excerpt = excerpt
        self.evidence_level = chunk.get("evidence_level") or evidence_ref.evidence_level
        self.content_hash = chunk.get("content_hash")

    @property
    def chunk_id(self) -> str:
        return self.evidence_ref.chunk_id

    @property
    def ref_label(self) -> str:
        return f"[{self.ref_id}]"


class EvidenceResolver:
    """按 chunk_id 从对应 catalog 解析证据正文（report / cognition 双库）。"""

    def __init__(
        self,
        cfg: Config,
        report_conn: sqlite3.Connection | None,
        cognition_conn: sqlite3.Connection | None,
    ) -> None:
        self.cfg = cfg
        self.report_repo = ChunkRepository(report_conn) if report_conn is not None else None
        self.cog_repo = ChunkRepository(cognition_conn) if cognition_conn is not None else None

    def _target_repo(self, chunk_id: str) -> ChunkRepository | None:
        prefix = self.cfg.cognition.docid_prefix  # I6: "cog"
        if chunk_id.startswith(prefix + ":"):
            return self.cog_repo
        return self.report_repo

    def load_chunk(self, chunk_id: str, content_hash: str | None) -> dict:
        repo = self._target_repo(chunk_id)
        if repo is None:
            raise EvidenceNotFoundError(f"chunk 无法解析：{chunk_id}")
        chunk = repo.get(chunk_id)
        if chunk is None:
            raise EvidenceNotFoundError(f"证据 chunk 不存在：{chunk_id}")
        if content_hash and chunk.get("content_hash") and chunk["content_hash"] != content_hash:
            raise EvidenceStaleError(
                f"证据已更新（EVIDENCE_STALE）：{chunk_id}",
                detail={"chunk_id": chunk_id},
            )
        return chunk

    @staticmethod
    def _canonical_ref(anchor: EvidenceRef, chunk: dict) -> EvidenceRef:
        """Build a catalog-authoritative ref while preserving the anchor source namespace."""

        return EvidenceRef(
            source_type=anchor.source_type,
            document_id=chunk.get("document_id") or anchor.document_id,
            section_id=chunk.get("section_id"),
            chunk_id=str(chunk.get("id") or anchor.chunk_id),
            content_hash=chunk.get("content_hash"),
            title=chunk.get("heading_path") or anchor.title,
            heading_path=chunk.get("heading_path"),
            start_line=chunk.get("start_line"),
            end_line=chunk.get("end_line"),
            evidence_level=chunk.get("evidence_level"),
        )

    def expand_refs(
        self,
        evidence_refs: list[EvidenceRef],
        mode: EvidenceContextMode = "none",
    ) -> list[EvidenceRef]:
        """Expand anchor evidence without losing chunk-level citation identity.

        ``none`` keeps only selected anchors. ``neighbor_1`` adds the immediately
        preceding/following chunk in document reading order. ``section`` adds every
        chunk with the same section_id as each anchor. Results are de-duplicated by
        chunk_id while preserving deterministic anchor traversal order.
        """

        if mode not in {"none", "neighbor_1", "section"}:
            raise ValueError(f"unsupported evidence_context_mode: {mode}")

        expanded: list[EvidenceRef] = []
        seen: set[str] = set()

        for raw in evidence_refs:
            anchor = raw if isinstance(raw, EvidenceRef) else EvidenceRef.model_validate(raw)
            anchor_chunk = self.load_chunk(anchor.chunk_id, anchor.content_hash)
            repo = self._target_repo(anchor.chunk_id)
            if repo is None:  # load_chunk already guards this; retained for type narrowing.
                raise EvidenceNotFoundError(f"chunk 无法解析：{anchor.chunk_id}")

            candidates: list[dict]
            if mode == "none":
                candidates = [anchor_chunk]
            else:
                document_id = anchor_chunk.get("document_id") or anchor.document_id
                ordered = sorted(repo.list_for_document(document_id), key=_reading_order)
                if mode == "section":
                    section_id = anchor_chunk.get("section_id")
                    candidates = (
                        [chunk for chunk in ordered if chunk.get("section_id") == section_id]
                        if section_id is not None
                        else [anchor_chunk]
                    )
                else:
                    anchor_index = next(
                        (i for i, chunk in enumerate(ordered) if chunk.get("id") == anchor.chunk_id),
                        None,
                    )
                    if anchor_index is None:
                        candidates = [anchor_chunk]
                    else:
                        start = max(0, anchor_index - 1)
                        stop = min(len(ordered), anchor_index + 2)
                        candidates = ordered[start:stop]

            for chunk in candidates:
                chunk_id = str(chunk.get("id") or "")
                if not chunk_id or chunk_id in seen:
                    continue
                expanded.append(self._canonical_ref(anchor, chunk))
                seen.add(chunk_id)

        return expanded

    def resolve(
        self,
        evidence_refs: list[EvidenceRef],
        *,
        max_evidence: int = 20,
        evidence_max_chars: int = _DEFAULT_MAX_CHARS,
    ) -> list[ResolvedEvidence]:
        resolved: list[ResolvedEvidence] = []
        for i, ref in enumerate(evidence_refs[:max_evidence], start=1):
            chunk = self.load_chunk(ref.chunk_id, ref.content_hash)
            text = chunk.get("plain_text") or chunk.get("raw_markdown") or ""
            excerpt = text[:evidence_max_chars]
            resolved.append(
                ResolvedEvidence(ref_id=f"E{i}", evidence_ref=ref, chunk=chunk, excerpt=excerpt)
            )
        return resolved


def provided_chunk_ids(resolved: list[ResolvedEvidence]) -> set[str]:
    """Context Envelope 中显式提供的、合法可引用的 chunk_id 集合。"""
    return {r.chunk_id for r in resolved}
