"""lexical_text 生成（M4，Addendum §8-10）。

流水线：NFKC -> Identifier 保护 -> jieba 中文分词（tech_terms 预注册）->
轻量停用词 -> 标识符原样回填 -> 空格连接。

输出供 FTS5 unicode61 索引使用。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import jieba

from app.lexical.normalizer import IDENT_RE, extract_identifiers, is_identifier, normalize

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
TECH_TERMS_PATH = _PROJECT_ROOT / "config" / "tech_terms.txt"

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "对", "为", "及", "等", "或", "一个", "这",
    "那", "有", "会", "能", "可", "将", "从", "把", "被", "以", "其", "之", "并",
    "但", "而", "因此", "由于", "通过", "对于", "以及", "可以", "同时", "并且",
}


@lru_cache(maxsize=1)
def load_tech_terms(path: str | Path = TECH_TERMS_PATH) -> tuple[list[str], list[str]]:
    """返回 (ascii_terms, chinese_terms)。"""
    ascii_terms: list[str] = []
    chinese_terms: list[str] = []
    if not Path(path).exists():
        return ascii_terms, chinese_terms
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        if re.fullmatch(r"[A-Za-z0-9\u00b5\u03bc\u00b0\u00b2\u00b1\u00d7$%][-:/_.+\u00d7\u00b7A-Za-z0-9\u00b5\u03bc\u00b0\u00b2\u00b1\u00d7$%]*", term):
            ascii_terms.append(term)
        else:
            chinese_terms.append(term)
    return ascii_terms, chinese_terms


@lru_cache(maxsize=1)
def _setup_jieba(path: str | Path = TECH_TERMS_PATH) -> None:
    _, chinese_terms = load_tech_terms(path)
    for t in chinese_terms:
        jieba.add_word(t, freq=1000)
    # 常见领域词兜底
    for w in ("晶圆代工", "半导体制程", "电源管理", "算力基础设施", "数据中心", "推理算力",
              "电网瓶颈", "半导体周期", "资本开支", "资产定价", "蛋白质结构"):
        jieba.add_word(w, freq=500)


def tokenize(text: str) -> list[str]:
    """生成词项序列（不含标识符保护回填前的中文/英文词）。"""
    _setup_jieba()
    toks: list[str] = []
    for t in jieba.cut(text):
        t = t.strip()
        if not t or t in STOPWORDS:
            continue
        if IDENT_RE.fullmatch(t) and not is_identifier(t) and re.fullmatch(r"[A-Za-z]+", t):
            toks.append(t.lower())  # 普通英文词归一化小写
            continue
        toks.append(t)
    return toks


def build_lexical_text(text: str) -> str:
    """Chunk.plain_text -> lexical_text。"""
    text = normalize(text)
    identifiers = extract_identifiers(text)
    # 用占位符保护标识符，避免 jieba 拆坏（CoWoS-L -> CoWoS / L）
    protected = IDENT_RE.sub(lambda m: "\x00" if is_identifier(m.group(0)) else m.group(0), text)
    toks = tokenize(protected.replace("\x00", " "))
    # 回填标识符（原样，大小写保留）
    return " ".join(identifiers + toks)
