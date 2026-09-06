"""HTTP gateway to the verified local Cognition App contract.

The gateway separates staging from formal operations. Proposal creation and reads
are staging/observability operations. Formal Preview/Apply methods mirror the
real local Cognition API and are called only by the explicit DL-06 formal adapter;
KE never writes Cognition Markdown or SQLite directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class CognitionGatewayError(RuntimeError):
    """Raised when the local Cognition API is unreachable or returns a bad contract."""


@dataclass(frozen=True)
class PublishedProposal:
    proposal_id: str
    raw: dict[str, Any]


_OBJECT_PATHS = {
    "judgment": "judgments",
    "question": "questions",
    "topic": "topics",
}


class CognitionGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["json"] = json_body
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise CognitionGatewayError(f"Cognition API 不可达: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise CognitionGatewayError(
                f"Cognition API 返回非 JSON（HTTP {response.status_code}）"
            ) from exc

        if response.status_code >= 400:
            message = None
            if isinstance(body, dict):
                message = body.get("error") or body.get("message") or body.get("detail")
            raise CognitionGatewayError(
                f"Cognition API HTTP {response.status_code}: {message or body}"
            )
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise CognitionGatewayError(f"Cognition API 契约异常: {body}")
        return body

    def health(self) -> dict:
        """Read-only health probe using the stable settings endpoint."""
        return self._request("GET", "/settings")

    def create_proposal(self, payload: dict) -> PublishedProposal:
        """Create a Proposal candidate; creation alone performs no formal object write."""
        body = self._request("POST", "/proposals", json_body=payload)
        item = body.get("item")
        if not isinstance(item, dict) or not item.get("id"):
            raise CognitionGatewayError("Cognition Proposal 创建成功响应缺少 item.id")
        return PublishedProposal(proposal_id=str(item["id"]), raw=body)

    def get_proposal(self, proposal_id: str) -> dict:
        return self._request("GET", f"/proposals/{proposal_id}")

    def get_object(self, object_type: str, object_id: str) -> dict:
        """Read one formal Cognition object and preserve its `_hash` when exposed."""
        bucket = _OBJECT_PATHS.get(object_type)
        if bucket is None:
            raise CognitionGatewayError(f"不支持的 Cognition object_type: {object_type}")
        return self._request("GET", f"/{bucket}/{object_id}")

    def preview_proposal_item(self, proposal_id: str, item_id: str) -> dict:
        """Run Cognition's zero-write formal Preview for one Proposal item."""
        return self._request(
            "POST",
            f"/proposals/{proposal_id}/items/{item_id}/preview",
        )

    def apply_proposal_item(
        self,
        proposal_id: str,
        item_id: str,
        *,
        action: str | None = None,
        target_id: str | None = None,
        edit_summary: str | None = None,
        title: str | None = None,
    ) -> dict:
        """Call Cognition Human-Apply endpoint after the adapter's explicit gates."""
        body: dict[str, Any] = {}
        if action is not None:
            body["action"] = action
        if target_id is not None:
            body["targetId"] = target_id
        if edit_summary is not None:
            body["editSummary"] = edit_summary
        if title is not None:
            body["title"] = title
        return self._request(
            "POST",
            f"/proposals/{proposal_id}/items/{item_id}/apply",
            json_body=body,
        )

    def reject_proposal_item(self, proposal_id: str, item_id: str, *, reason: str) -> dict:
        """Record a formal proposal rejection in Cognition without changing the target."""
        return self._request(
            "POST",
            f"/proposals/{proposal_id}/items/{item_id}/reject",
            json_body={"reason": reason},
        )
