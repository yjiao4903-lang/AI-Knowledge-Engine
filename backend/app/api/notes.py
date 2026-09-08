"""Personal notes API. KE-owned; never writes Cognition."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.notes.store import STANCES, NoteStore

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _store(request: Request) -> NoteStore:
    store = getattr(request.app.state, "note_store", None)
    if store is None:
        store = NoteStore(request.app.state.conn)
        request.app.state.note_store = store
    return store


class NoteCreate(BaseModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)
    stance: str = "note"
    heading_path: str | None = None
    task_id: str | None = None


class NoteUpdate(BaseModel):
    body: str | None = Field(default=None, max_length=4000)
    stance: str | None = None


@router.post("/")
def create_note(body: NoteCreate, request: Request) -> dict:
    if body.stance not in STANCES:
        raise HTTPException(status_code=400, detail=f"stance 必须是 {list(STANCES)}")
    row = request.app.state.conn.execute(
        "SELECT id FROM chunks WHERE id = ?", (body.chunk_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"chunk 不存在: {body.chunk_id}")
    try:
        return _store(request).create(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/")
def list_notes(
    request: Request,
    chunk_id: str | None = None,
    document_id: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> dict:
    notes = _store(request).list(
        chunk_id=chunk_id, document_id=document_id, q=q, limit=min(limit, 200)
    )
    return {"notes": notes, "count": len(notes)}


@router.get("/{note_id}")
def get_note(note_id: str, request: Request) -> dict:
    note = _store(request).get(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.patch("/{note_id}")
def update_note(note_id: str, body: NoteUpdate, request: Request) -> dict:
    try:
        note = _store(request).update(note_id, body=body.body, stance=body.stance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.delete("/{note_id}")
def delete_note(note_id: str, request: Request) -> dict:
    if not _store(request).delete(note_id):
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"deleted": True, "id": note_id}
