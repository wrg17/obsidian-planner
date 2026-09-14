"""Note CRUD, closing, and hierarchy.

Controllers stay thin: translate, delegate, translate back. No business rules here --
domain errors propagate to the handlers installed in middleware.py, which is why there
is not a try/except in sight.

What each operation promises -- its summary, the guidance a newcomer needs, and the
numbered invariants it upholds -- lives in `contracts/operations.py`, because the MCP
server documents the same operations and neither transport should import the other.
Read it alongside this file.
"""

from __future__ import annotations

import datetime

from fastapi import Depends, Path, Query, Response

from ...contracts.operations import DEMO
from ...domain import schema as S
from ...domain.note import Note
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import NoteIn, NotePatch


def list_notes(
    kind: S.KindEnum | None = Query(None, description="Restrict to one kind."),
    project: str | None = Query(
        None, description="Plain title.", examples=[DEMO["project"]]
    ),
    parent: str | None = Query(
        None, description="Direct children of this note.", examples=[DEMO["parent"]]
    ),
    status: S.StatusEnum | None = None,
    open_only: bool = Query(False, alias="open", description="Exclude closed work."),
    service: NoteService = Depends(get_service),
):
    """List notes, optionally filtered.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    where = {
        k: v
        for k, v in {"project": project, "parent": parent, "status": status}.items()
        if v is not None
    }
    return [n.to_dict() for n in service.list(kind=kind, open_only=open_only, **where)]


def create_note(payload: NoteIn, service: NoteService = Depends(get_service)):
    """Create a note.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    return service.create(
        Note.from_dict(payload.model_dump(exclude_none=True))
    ).to_dict()


def create_many(payload: list[NoteIn], service: NoteService = Depends(get_service)):
    """Create several notes as one transaction.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    notes = [Note.from_dict(item.model_dump(exclude_none=True)) for item in payload]
    return [n.to_dict() for n in service.create_many(notes)]


def get_note(
    title: str = Path(..., examples=[DEMO["task"]]),
    service: NoteService = Depends(get_service),
):
    """Fetch one note by title.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    return service.get(title).to_dict()


def update_note(
    payload: NotePatch,
    title: str = Path(..., examples=[DEMO["task"]]),
    service: NoteService = Depends(get_service),
):
    """Partially update a note.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("title", None)
    return service.update(title, **changes).to_dict()


def delete_note(
    title: str = Path(..., examples=[DEMO["leaf"]]),
    cascade: bool = Query(
        False,
        description="Also delete every descendant. Without it, a note with "
        "children is refused.",
    ),
    service: NoteService = Depends(get_service),
):
    """Delete a note.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    service.delete(title, cascade=cascade)
    return Response(status_code=204)


def get_children(
    title: str = Path(..., examples=[DEMO["parent"]]),
    recursive: bool = Query(False, description="Whole subtree instead of one level."),
    service: NoteService = Depends(get_service),
):
    """Children of a note.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    service.get(title)  # 404 rather than an empty list for a missing parent
    found = service.descendants_of(title) if recursive else service.children_of(title)
    return [n.to_dict() for n in found]


def close_note(
    title: str = Path(..., examples=[DEMO["task"]]),
    status: S.ClosingStatusEnum = Query(S.ClosingStatusEnum.DONE),
    on: datetime.date | None = Query(None, description="Defaults to today."),
    service: NoteService = Depends(get_service),
):
    """Close a ticket.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    return service.close(title, status=status, on=on).to_dict()


def reopen_note(
    title: str = Path(..., examples=[DEMO["task"]]),
    status: S.StatusEnum = Query(S.StatusEnum.TODO),
    service: NoteService = Depends(get_service),
):
    """Reopen a closed ticket.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    return service.reopen(title, status=status).to_dict()
