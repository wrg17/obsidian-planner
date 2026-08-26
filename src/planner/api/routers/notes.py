"""Note CRUD. Controllers stay thin: translate, delegate, translate back.

No business rules here. Domain errors propagate to the handlers installed in
middleware.py, which is why there is not a try/except in sight.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query, Response

from ...domain import schema as S
from ...domain.note import Note
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import ErrorOut, NoteIn, NoteOut, NotePatch

router = APIRouter(prefix="/notes", tags=["notes"],
                   responses={422: {"model": ErrorOut, "description": "Validation failed"}})


@router.get("", response_model=list[NoteOut], summary="List notes")
def list_notes(
    kind: S.KindEnum | None = Query(None, description="Filter to one kind."),
    project: str | None = Query(None, description="Plain title."),
    parent: str | None = Query(None, description="Direct children of this note."),
    status: S.StatusEnum | None = None,
    open_only: bool = Query(False, alias="open", description="Exclude closed work."),
    service: NoteService = Depends(get_service),
):
    where = {k: v for k, v in
             {"project": project, "parent": parent, "status": status}.items()
             if v is not None}
    notes = service.list(kind=kind, open_only=open_only, **where)
    return [n.to_dict() for n in notes]


@router.post("", response_model=NoteOut, status_code=201, summary="Create a note",
             responses={409: {"model": ErrorOut, "description": "Title already used"}})
def create_note(payload: NoteIn, service: NoteService = Depends(get_service)):
    """Folder is derived from `kind`. `created`, `status` and `done` are defaulted."""
    return service.create(Note.from_dict(payload.model_dump(exclude_none=True))).to_dict()


@router.get("/{title}", response_model=NoteOut, summary="Fetch one note",
            responses={404: {"model": ErrorOut}})
def get_note(title: str, service: NoteService = Depends(get_service)):
    return service.get(title).to_dict()


@router.patch("/{title}", response_model=NoteOut, summary="Update a note",
              responses={404: {"model": ErrorOut}})
def update_note(title: str, payload: NotePatch,
                service: NoteService = Depends(get_service)):
    """Only fields present in the body are touched; `null` removes one."""
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("title", None)
    return service.update(title, **changes).to_dict()


@router.delete("/{title}", status_code=204, summary="Delete a note",
               responses={404: {"model": ErrorOut}})
def delete_note(title: str, service: NoteService = Depends(get_service)):
    service.delete(title)
    return Response(status_code=204)


@router.get("/{title}/children", response_model=list[NoteOut], tags=["hierarchy"],
            summary="Direct children", responses={404: {"model": ErrorOut}})
def get_children(title: str, recursive: bool = Query(False, description=
                 "Include the whole subtree rather than one level."),
                 service: NoteService = Depends(get_service)):
    service.get(title)          # 404 rather than an empty list for a missing parent
    found = service.descendants_of(title) if recursive else service.children_of(title)
    return [n.to_dict() for n in found]


@router.post("/{title}/close", response_model=NoteOut, tags=["tickets"],
             summary="Close a ticket", responses={404: {"model": ErrorOut}})
def close_note(
    title: str,
    status: S.ClosingStatusEnum = Query(S.ClosingStatusEnum.DONE),
    on: datetime.date | None = Query(None, description="Defaults to today."),
    service: NoteService = Depends(get_service),
):
    """Sets status, ticks `done` and stamps `closed` in one call -- the three fields
    that must move together and routinely don't."""
    return service.close(title, status=status, on=on).to_dict()


@router.post("/{title}/reopen", response_model=NoteOut, tags=["tickets"],
             summary="Reopen a ticket", responses={404: {"model": ErrorOut}})
def reopen_note(title: str, status: S.StatusEnum = Query(S.StatusEnum.TODO),
                service: NoteService = Depends(get_service)):
    """Clears `closed`, unticks `done`, and puts the ticket back in the given status."""
    return service.reopen(title, status=status).to_dict()
