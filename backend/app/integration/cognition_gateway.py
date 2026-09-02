"""HTTP gateway to the local Cognition App.

The gateway intentionally exposes only the staging operations needed by the
integrated Research OS. It may create a Proposal candidate in Cognition, but it
must never call Proposal apply/merge/revision endpoints. Formal cognition writes
remain owned by Cognition Preview + Human Apply.
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


class CognitionGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, json=json_body)
        except httpx.HTTPError as exc:
            raise CognitionGatewayError(f"Cognition API 不可达: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise CognitionGatewayError(
                f"Cognition API 返回非 JSON（HTTP {response.status_code}）"
            ) from exc

        if response.status_code >= 400:
            message = body.get("error") if isinstance(body, dict) else None
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
        """Create a Proposal candidate only; this does not apply any cognition change."""
        body = self._request("POST", "/proposals", json_body=payload)
        item = body.get("item")
        if not isinstance(item, dict) or not item.get("id"):
            raise CognitionGatewayError("Cognition Proposal 创建成功响应缺少 item.id")
        return PublishedProposal(proposal_id=str(item["id"]), raw=body)

    def get_proposal(self, proposal_id: str) -> dict:
        """Read a proposal for observability/debugging; no apply capability is exposed."""
        return self._request("GET", f"/proposals/{proposal_id}")
