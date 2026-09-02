"""Integrated Research OS bridge endpoints.

These endpoints connect validated TaskPack results to the local Cognition App
through its official Proposal API. The bridge can create Proposal *candidates*
only. It deliberately exposes no apply/merge/revision operation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.synthesis import _require_task, get_proposal_candidates
from app.integration.cognition_gateway import CognitionGateway, CognitionGatewayError

router = APIRouter(prefix="/api/research-os", tags=["research-os"])

_PUBLISH_MARKER = "result/proposal_publish.json"


class PublishProposalRequest(BaseModel):
    force: bool = False


def _gateway(request: Request) -> CognitionGateway:
    cfg = request.app.state.cfg
    return CognitionGateway(
        cfg.cognition.api_url,
        timeout_seconds=cfg.cognition.api_timeout_seconds,
    )


def _read_marker(pack: Path) -> dict | None:
    path = pack / _PUBLISH_MARKER
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_marker(pack: Path, payload: dict) -> None:
    target = pack / _PUBLISH_MARKER
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)


@router.get("/cognition/health")
def cognition_health(request: Request) -> dict:
    try:
        body = _gateway(request).health()
    except CognitionGatewayError as exc:
        return {
            "reachable": False,
            "api_url": request.app.state.cfg.cognition.api_url,
            "error": str(exc),
        }
    return {
        "reachable": True,
        "api_url": request.app.state.cfg.cognition.api_url,
        "settings": body.get("settings", {}),
    }


@router.get("/tasks/{task_id}/proposal-publication")
def proposal_publication(task_id: str, request: Request) -> dict:
    pack, _ = _require_task(request, task_id)
    marker = _read_marker(pack)
    return {
        "task_id": task_id,
        "published": marker is not None,
        "publication": marker,
    }


@router.post("/tasks/{task_id}/publish-proposal")
def publish_proposal(
    task_id: str,
    request: Request,
    body: PublishProposalRequest | None = None,
) -> dict:
    """Publish a validated TaskPack result into Cognition's Proposal staging area.

    This endpoint does NOT apply the proposal. Cognition remains the only formal
    cognition writer and still requires Preview + Human Apply for every item.
    """

    cfg = request.app.state.cfg
    if not cfg.cognition.proposal_publish_enabled:
        raise HTTPException(status_code=403, detail="Cognition Proposal 发布功能已禁用")

    pack, _ = _require_task(request, task_id)
    force = bool(body.force) if body is not None else False
    existing = _read_marker(pack)
    if existing is not None and not force:
        return {
            "task_id": task_id,
            "published": True,
            "reused": True,
            "publication": existing,
            "auto_apply": False,
        }

    candidates = get_proposal_candidates(task_id, request)
    payload = candidates["proposal_payload"]

    try:
        published = _gateway(request).create_proposal(payload)
    except CognitionGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    marker = {
        "schema_version": "1.0",
        "task_id": task_id,
        "proposal_id": published.proposal_id,
        "origin_ref": payload.get("origin_ref"),
        "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cognition_api_url": cfg.cognition.api_url,
        "auto_apply": False,
    }
    _write_marker(pack, marker)

    return {
        "task_id": task_id,
        "published": True,
        "reused": False,
        "publication": marker,
        "warnings": candidates.get("warnings", []),
        "auto_apply": False,
    }
