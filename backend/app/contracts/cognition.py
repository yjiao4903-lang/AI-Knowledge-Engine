"""Stable Cognition integration contracts.

These models are intentionally kept outside ``app.synthesis`` and ``app.taskpack``
so the HTTP request schema and TaskPack filesystem schema can share the exact
same object without introducing a circular dependency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CognitionContextItem(BaseModel):
    """Read-only snapshot of one formal Cognition object supplied to a TaskPack.

    ``object_id`` is the Cognition-side stable identity. ``content_hash`` is
    optional because old Cognition objects may not expose a hash yet; when it is
    available it should be preserved so the consumer can detect stale context.
    This object never grants Knowledge Engine write permission over Cognition.
    """

    schema_version: str = "1.0"
    context_id: str = Field(..., min_length=1)
    object_type: str = Field(..., min_length=1)
    object_id: str = Field(..., min_length=1)
    content_hash: str | None = None
    title: str | None = None
    excerpt: str | None = None
