"""Semantic Chunker 规则引擎（M3，spec §11 + Addendum §2-10）。

严格消费 M2 Parser 的 Section + Block，不重新解析 Markdown。

优先级：语义完整性 > Section 边界 > 特殊块完整性 > 长度。
- prose：按段落贪心打包（target 900 / soft_max 1400 / hard_max 2200，段落级 overlap）；
- 特殊块（table/formula/code/mermaid/ascii_diagram）：整体成 Chunk，超限标 oversized；
- formula：附带紧邻短解释段；
- 不跨 Section 合并。
"""

from __future__ import annotations

import re

from app.chunking.chunk_models import CHUNKER_VERSION, Chunk, build_chunk_id
from app.chunking.embedding_text import build_embedding_text
from app.chunking.plain_text import to_plain_text
from app.core.config import ChunkingConfig
from app.parser.evidence import extract_evidence_levels
from app.parser.models import Block, ParsedDocument, Section

SENT_SPLIT_RE = re.compile(r"(?<=[。；！？!?])")
FORMULA_ATTACH_MAX = 400  # 公式紧邻解释段的最大长度

# prose 内容类型由 section_type 决定
_PROSE_TYPE_MAP = {
    "summary": "summary",
    "reference": "reference",
    "audit": "audit",
    "monitoring": "monitoring",
    "decision_tree": "decision_tree",
    "comparison": "comparison",
    "causal_chain": "causal_chain",
}

# 特殊块的 content_type
def _special_content_type(block: Block, section: Section) -> str:
    if block.block_type in ("ascii_diagram", "mermaid"):
        return "causal_chain"
    if block.block_type == "code":
        return "code"
    if block.block_type == "formula":
        return "formula"
    if block.block_type == "table":
        if section.section_type == "monitoring":
            return "monitoring"
        if section.section_type == "comparison":
            return "comparison"
        return "table"
    return "prose"


def _split_long_paragraph(text: str, target: int, hard_max: int) -> list[str]:
    """超长段落按句子切分，每片 <= hard_max，目标 target。"""
    sentences = [s for s in SENT_SPLIT_RE.split(text) if s.strip()]
    pieces: list[str] = []
    cur = ""
    for sent in sentences:
        if len(cur) + len(sent) > target and cur:
            pieces.append(cur)
            cur = sent
        else:
            cur += sent
        while len(cur) > hard_max:  # 单句超长（罕见）：硬切
            pieces.append(cur[:hard_max])
            cur = cur[hard_max:]
    if cur.strip():
        pieces.append(cur)
    return pieces


class SemanticChunker:
    def __init__(self, cfg: ChunkingConfig, chunker_version: str = CHUNKER_VERSION) -> None:
        self.cfg = cfg
        self.chunker_version = chunker_version

    # ---- 主入口 ----
    def chunk_document(self, doc: ParsedDocument, document_id: str | None = None) -> list[Chunk]:
        document_id = document_id or doc.metadata.get("report_code") or "DOC"
        document_title = doc.metadata.get("title") or doc.title
        domain = doc.metadata.get("domain", "")

        # section_type 继承：body 子节继承 reference/audit 父节类型
        # （如"参考文献清单"下的"1. 学术期刊论文"子节仍属 reference 池，供检索侧排除）
        effective_types: dict[str, str] = {}
        for s in doc.sections:
            st = s.section_type
            if st == "body" and s.parent_id:
                parent_t = effective_types.get(s.parent_id)
                if parent_t in ("reference", "audit"):
                    st = parent_t
            effective_types[s.section_id] = st

        chunks: list[Chunk] = []
        for section in doc.sections:
            section.section_type = effective_types[section.section_id]
            if section.ordinal == 0:
                body_blocks = self._root_body_blocks(section)
            else:
                body_blocks = section.blocks
            if not body_blocks:
                continue
            for content in self._section_chunks(section, body_blocks):
                # content: (blocks, raw, content_type, oversized)
                blocks, raw, ctype, oversized = content
                chunks.append(
                    self._build_chunk(
                        document_id, document_title, domain, section,
                        blocks, raw, ctype, oversized, len(chunks) + 1,
                    )
                )
        return chunks

    def _root_body_blocks(self, section: Section) -> list[Block]:
        """根 section：跳过元数据 blockquote（已入 documents 表），保留其余（如因果拓扑图）。"""
        out = []
        for b in section.blocks:
            if b.block_type == "prose" and all(
                (not ln.strip()) or ln.lstrip().startswith(">") for ln in b.text.splitlines()
            ):
                continue
            out.append(b)
        return out

    # ---- Section 内分块 ----
    def _section_chunks(self, section: Section, blocks: list[Block]) -> list[tuple]:
        """返回 [(blocks, raw, content_type, oversized), ...]，不跨 Section。"""
        results: list[tuple] = []
        prose_buf: list[Block] = []
        prose_type = _PROSE_TYPE_MAP.get(section.section_type, "prose")

        def flush_prose() -> None:
            if prose_buf:
                results.extend(self._pack_prose(prose_buf, prose_type))
                prose_buf.clear()

        i = 0
        while i < len(blocks):
            b = blocks[i]
            if b.block_type == "prose":
                prose_buf.append(b)
                i += 1
                continue

            if b.block_type == "formula":
                # 公式 + 紧邻短解释：先从缓冲区取出（避免重复入 prose chunk）
                prev = prose_buf[-1] if prose_buf else None
                nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                if prev and len(prev.text) <= FORMULA_ATTACH_MAX:
                    prose_buf.pop()
                    flush_prose()
                    results.append(([prev, b], f"{prev.text}\n\n{b.text}", "formula",
                                    len(prev.text) + len(b.text) > self.cfg.hard_max_chars))
                else:
                    flush_prose()
                    if nxt and nxt.block_type == "prose" and len(nxt.text) <= FORMULA_ATTACH_MAX:
                        results.append(([b, nxt], f"{b.text}\n\n{nxt.text}", "formula",
                                        len(b.text) + len(nxt.text) > self.cfg.hard_max_chars))
                        i += 1  # 解释段已消费，跳过
                    else:
                        results.append(([b], b.text, "formula", len(b.text) > self.cfg.hard_max_chars))
                i += 1
                continue

            flush_prose()
            ctype = _special_content_type(b, section)
            oversized = len(b.text) > self.cfg.hard_max_chars
            results.append(([b], b.text, ctype, oversized))
            i += 1

        flush_prose()
        return results

    def _pack_prose(self, buffer: list[Block], content_type: str) -> list[tuple]:
        """段落贪心打包：target/soft_max/hard_max + 段落级 overlap。"""
        cfg = self.cfg
        # 先展开超长段落
        paras: list[Block] = []
        for b in buffer:
            if len(b.text) > cfg.hard_max_chars:
                # 超长段落按句子切分；行号继承原块区间（内容仍来自同一行范围）
                for piece in _split_long_paragraph(b.text, cfg.target_chars, cfg.hard_max_chars):
                    paras.append(Block("prose", b.start_line, b.end_line, piece))
            else:
                paras.append(b)

        results: list[tuple] = []
        cur: list[Block] = []
        cur_len = 0
        for p in paras:
            if cur and cur_len + len(p.text) > cfg.soft_max_chars and cur_len >= cfg.soft_min_chars:
                results.append((cur, "\n\n".join(x.text for x in cur), content_type, False))
                # overlap：上一段较短时整体滚入下一 chunk（段落级 overlap）
                last = cur[-1]
                cur = [last] if len(last.text) <= cfg.overlap_chars * 3 else []
                cur_len = sum(len(x.text) for x in cur)
            cur.append(p)
            cur_len += len(p.text)
        if cur:
            # 仅剩 overlap 段（无新内容）时并入前一 chunk
            if results and len(cur) == 1 and cur[0] is results[-1][0][-1]:
                pass
            else:
                results.append((cur, "\n\n".join(x.text for x in cur), content_type,
                                cur_len > cfg.hard_max_chars))
        return results

    # ---- Chunk 组装 ----
    def _build_chunk(
        self,
        document_id: str,
        document_title: str,
        domain: str,
        section: Section,
        blocks: list[Block],
        raw: str,
        content_type: str,
        oversized: bool,
        ordinal: int,
    ) -> Chunk:
        plain = to_plain_text(raw)
        levels = extract_evidence_levels(raw) or extract_evidence_levels(section.raw_text)
        heading_path = " > ".join(section.heading_path)
        chunk = Chunk(
            chunk_id=build_chunk_id(document_id, section.section_id, ordinal),
            document_id=document_id,
            section_id=section.section_id,
            ordinal=ordinal,
            heading_path=heading_path,
            content_type=content_type,
            raw_markdown=raw,
            plain_text=plain,
            embedding_text=build_embedding_text(
                document_title, domain, heading_path, content_type,
                min(levels) if levels else None, plain,
            ),
            start_line=min(b.start_line for b in blocks),
            end_line=max(b.end_line for b in blocks),
            evidence_level=min(levels) if levels else None,
            evidence_levels=levels,
            oversized=oversized,
        )
        return chunk
