"""embedding_text 构造（M3-06，spec §14）。

禁止直接 embedding plain_text；必须携带文档级上下文提高跨报告可辨识度。
"""

from __future__ import annotations

EMBEDDING_TEMPLATE = """Document: {document_title}
Domain: {domain}
Section: {heading_path}
Content Type: {content_type}
Evidence: {evidence}

{plain_text}"""


def build_embedding_text(
    document_title: str,
    domain: str,
    heading_path: str,
    content_type: str,
    evidence_level: int | None,
    plain_text: str,
) -> str:
    return EMBEDDING_TEMPLATE.format(
        document_title=document_title,
        domain=domain or "unknown",
        heading_path=heading_path or "(root)",
        content_type=content_type,
        evidence=f"L{evidence_level}" if evidence_level else "unmarked",
        plain_text=plain_text,
    )
