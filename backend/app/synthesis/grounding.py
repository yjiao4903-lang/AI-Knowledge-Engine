"""证据接地（Grounding）：将 EvidenceRef 解析为可注入 Context Envelope 的正文。

L1A 硬约束：LLM 只能引用本次 Context Envelope 中显式提供的 Evidence（主计划 §9），
因此解析必须权威——正文一律按 chunk_id 从 KE catalog（SQLite）读取，不信任客户端
传入的 excerpt 快照。这样既保证 LLM 看到的是真实证据文本，也避免信任用户可控内容。

`ResolvedEvidence` 内每个条目带 `ref_id`（E1..En）。Context Envelope 中用
`id=chunk_id` 呈现；模型须逐字引用 chunk_id（Citation Rules，§9）。
"""

from __future__ import annotations

import sqlite3

from app.core.config import Config
from app.core.errors import EvidenceNotFoundError, EvidenceStaleError
from app.storage.repositories.knowledge import ChunkRepository
from app.synthesis.schemas import EvidenceRef

# 单条证据正文注入上下文的上限（config evidence_max_chars 兜底）
_DEFAULT_MAX_CHARS = 1200


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