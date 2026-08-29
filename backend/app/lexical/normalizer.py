"""Unicode 规范化与 Technical Identifier 保护（M4，Addendum §8-9）。

- normalize: NFKC + 空白折叠；
- Identifier Protector：含 - : / + . _ 的混合 token 整体保留，
  禁止 CoWoS-L -> CoWoS / L、MR-MUF -> MR / MUF 这类破坏。
"""

from __future__ import annotations

import re
import unicodedata

# Identifier 形态：字母/数字（含 µ μ ² ° × ± $ % +）组成的连续段，
# 段内可由 - : / _ . + × · 连接（CoWoS-L / EXE:5000 / 60mV/dec / 2048-bit）。
IDENT_RE = re.compile(
    r"[A-Za-z0-9\u00b5\u03bc\u00b0\u00b2\u00b1\u00d7\u2032\u2033$%+]+"
    r"(?:[-:/_.+\u00d7\u00b7][A-Za-z0-9\u00b5\u03bc\u00b0\u00b2\u00b1\u00d7\u2032\u2033$%+]+)*"
)
# 至少要"像标识符"才保护：含连接符，或字母+数字混合（避免把普通英文单词固化）
def is_identifier(token: str) -> bool:
    if not IDENT_RE.fullmatch(token):
        return False
    if any(c in token for c in "-:/_.+"):
        return True
    return bool(re.search(r"[A-Za-z]", token) and re.search(r"[0-9]", token))


def normalize(text: str) -> str:
    """NFKC 规范化 + 空白折叠（保留大小写，标识符区分大小写）。"""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_identifiers(text: str) -> list[str]:
    """按出现顺序提取标识符（去重保序）。"""
    seen: list[str] = []
    for m in IDENT_RE.finditer(text):
        tok = m.group(0)
        if is_identifier(tok) and tok not in seen:
            seen.append(tok)
    return seen
