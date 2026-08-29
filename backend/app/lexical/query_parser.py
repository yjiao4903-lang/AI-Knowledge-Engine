"""统一 Lexical Query Parser（M4，Addendum §12）。

禁止调用层直接把用户查询塞进 FTS MATCH。
流程：识别 Identifier -> 中文分词 -> 安全转义（双引号包裹）-> FTS5 Expression。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.lexical.normalizer import extract_identifiers, normalize
from app.lexical.tokenizer import tokenize


@dataclass
class ParsedQuery:
    raw: str
    identifiers: list[str] = field(default_factory=list)   # 原样（大小写保留）
    tokens: list[str] = field(default_factory=list)        # 中文/英文词项


def parse_query(query: str) -> ParsedQuery:
    q = normalize(query)
    identifiers = extract_identifiers(q)
    # 去掉标识符后分词，避免 jieba 拆坏
    stripped = q
    for ident in identifiers:
        stripped = stripped.replace(ident, " ")
    tokens = [t for t in tokenize(stripped) if t.strip()]
    return ParsedQuery(raw=query, identifiers=identifiers, tokens=tokens)


def _quote(term: str) -> str:
    """FTS5 字符串安全包裹：内部双引号翻倍。"""
    return '"' + term.replace('"', '""') + '"'


def build_terms_expression(query: str) -> str:
    """FTS Terms（unicode61）查询表达式。词项间 OR（召回优先，bm25 排序兜底）。"""
    pq = parse_query(query)
    terms = [_quote(t) for t in pq.identifiers + pq.tokens]
    if not terms:
        return _quote(query.strip()) if query.strip() else ""
    return " OR ".join(terms)


def build_trigram_expression(query: str) -> str:
    """FTS Trigram 查询表达式：仅保留 >=3 字符的精确子串（标识符 + 中文长词）。"""
    pq = parse_query(query)
    parts: list[str] = []
    for ident in pq.identifiers:
        if len(ident) >= 3:
            parts.append(_quote(ident))
    for tok in pq.tokens:
        if len(tok) >= 3:
            parts.append(_quote(tok))
    # 查询本身整体太短时（如 2 字中文），trigram 无法命中，返回空串由调用方跳过
    if not parts:
        raw = query.strip()
        if len(raw) >= 3:
            parts.append(_quote(raw))
    return " OR ".join(parts)
