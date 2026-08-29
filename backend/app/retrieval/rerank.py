"""Reranker 服务层（M7，Addendum §6-9/21）。

- 输入模板：Instruct + Query + Document(Title/Section/Content Type/Evidence/正文)；
- 长文档截断：保留 Heading Path + 查询词邻域 + 开头（不是简单截前 N tokens）；
- 通过 InferenceManager 在独立 worker 进程内推理；
- 输出 reranker_score / pre_rerank_rank / final_rank。
"""

from __future__ import annotations

import logging

from app.core.config import Config
from app.inference.manager import InferenceManager

logger = logging.getLogger(__name__)

_WINDOW = 400  # 查询词邻域窗口长度
_HEAD = 500    # 正文开头保留长度


def build_rerank_document(
    query: str,
    *,
    title: str,
    heading_path: str,
    content_type: str,
    evidence_level: int | None,
    plain_text: str,
    max_chars: int = 1400,
) -> str:
    """按 Addendum §7/§9 构造 reranker 输入（不含 chunk_id 等无关 metadata）。"""
    body = plain_text
    if len(body) > max_chars:
        # 查询词邻域：找到首个查询词出现位置，取其窗口
        from app.lexical.normalizer import extract_identifiers

        terms = extract_identifiers(query) + [t for t in query.split() if len(t) >= 2]
        window = ""
        for t in terms:
            pos = body.find(t)
            if pos > 0:
                start = max(0, pos - _WINDOW // 2)
                window = "……\n" + body[start : start + _WINDOW] + "\n……"
                break
        body = body[:_HEAD] + ("\n" + window if window else "") + "\n……（截断）"
    return (
        f"Title: {title}\n"
        f"Section: {heading_path}\n"
        f"Content Type: {content_type}\n"
        f"Evidence: L{evidence_level if evidence_level else 'unmarked'}\n\n"
        f"{body}"
    )


class RerankerService:
    def __init__(self, cfg: Config, manager: InferenceManager) -> None:
        self.cfg = cfg
        self.manager = manager

    @property
    def enabled(self) -> bool:
        return self.cfg.reranker.enabled and self.manager.is_alive()

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """candidates: [{chunk_id, title, heading_path, content_type, evidence_level, plain_text}]。

        返回 [{chunk_id, reranker_score}]（按分数降序）。
        """
        if not candidates:
            return []
        max_c = self.cfg.reranker.candidate_k
        if self.manager.device_kind == "cpu":
            max_c = min(max_c, self.cfg.reranker.cpu_max_candidates)
        candidates = candidates[:max_c]

        docs = [
            build_rerank_document(
                query,
                title=c.get("title") or "",
                heading_path=c.get("heading_path") or "",
                content_type=c.get("content_type") or "",
                evidence_level=c.get("evidence_level"),
                plain_text=c.get("plain_text") or "",
            )
            for c in candidates
        ]
        scores = self.manager.call("rerank", {
            "query": query,
            "documents": docs,
            "instruction": self.cfg.reranker.instruction,
            "batch_size": self.cfg.reranker.batch_size,
        })
        out = [
            {"chunk_id": c["chunk_id"], "reranker_score": float(s)}
            for c, s in zip(candidates, scores)
        ]
        out.sort(key=lambda x: x["reranker_score"], reverse=True)
        return out
