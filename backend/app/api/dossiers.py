"""Topic Research Dossier API (DL-02A).

These endpoints manage KE research-planning metadata and read-only projections.
They do not create or modify formal Cognition objects.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.research.dossier import DossierUpsert, TopicDossierService

router = APIRouter(prefix="/api/research-os/dossiers", tags=["research-os-dossiers"])


def _service(request: Request) -> TopicDossierService:
    app = request.app
    cog = getattr(app.state, "cognition", None) or {}
    cognition_conn = cog.get("conn") if cog.get("enabled") else None
    return TopicDossierService(app.state.cfg, app.state.conn, cognition_conn)


@router.get("")
def list_dossiers(request: Request) -> dict:
    return {"dossiers": _service(request).list_dossiers()}


@router.get("/{dossier_id}")
def get_dossier(dossier_id: str, request: Request) -> dict:
    try:
        return _service(request).get(dossier_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"dossier not found: {dossier_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{dossier_id}")
def upsert_dossier(dossier_id: str, body: DossierUpsert, request: Request) -> dict:
    """Persist planning metadata after resolving every supplied stable reference.

    Formal cognition remains read-only. A dossier with no ``topic_object_id`` is
    explicitly returned as ``planning_only=true`` rather than pretending a formal
    Cognition Topic already exists.
    """

    try:
        return _service(request).upsert(dossier_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
