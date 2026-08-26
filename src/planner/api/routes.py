"""The routing table: every endpoint this API exposes, in one place.

Declared as data rather than scattered decorators so the whole surface is readable at
once. Handlers live in `handlers/`, keep their signatures and their invariant
docstrings -- FastAPI still reads both -- and know nothing about paths or status codes.

The split earns itself twice. Adding an endpoint means adding a row here, so nobody has
to grep for decorators to learn what exists; and a handler stops being coupled to its
URL, which is what made the earlier `notes.py` file 277 lines of routing metadata
wrapped around fifty lines of delegation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter

from .handlers import meta, notes
from .schemas import ErrorOut, NoteOut, Problem, SchemaOut

#: Attached to every route that can fail validation, which is all of them: both the DTO
#: enums and the domain normalise to one error shape (S4).
VALIDATION = {422: {"model": ErrorOut, "description": "Validation failed"}}
NOT_FOUND = {404: {"model": ErrorOut, "description": "No such note"}}
CONFLICT = {409: {"model": ErrorOut, "description": "Conflicts with existing state"}}


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: object
    tags: tuple[str, ...]
    summary: str
    response_model: object = None
    status_code: int = 200
    responses: dict = field(default_factory=dict)


#: Read top to bottom as the API's surface. Order here is the order in the OpenAPI
#: document and therefore in Swagger, so related operations sit together.
ROUTES: tuple[Route, ...] = (
    # --- notes --------------------------------------------------------------------
    Route("GET", "/notes", notes.list_notes, ("notes",),
          "List notes", list[NoteOut], responses=VALIDATION),
    Route("POST", "/notes", notes.create_note, ("notes",),
          "Create a note", NoteOut, 201, {**VALIDATION, **CONFLICT}),
    Route("POST", "/notes/bulk", notes.create_many, ("notes",),
          "Create several notes as one transaction", list[NoteOut], 201,
          {**VALIDATION, **CONFLICT}),
    Route("GET", "/notes/{title}", notes.get_note, ("notes",),
          "Fetch one note", NoteOut, responses=NOT_FOUND),
    Route("PATCH", "/notes/{title}", notes.update_note, ("notes",),
          "Update a note", NoteOut, responses={**VALIDATION, **NOT_FOUND}),
    Route("DELETE", "/notes/{title}", notes.delete_note, ("notes",),
          "Delete a note", None, 204,
          {**NOT_FOUND,
           409: {"model": ErrorOut, "description": "Would orphan child notes"}}),

    # --- hierarchy ----------------------------------------------------------------
    Route("GET", "/notes/{title}/children", notes.get_children, ("hierarchy",),
          "Direct children", list[NoteOut], responses=NOT_FOUND),

    # --- tickets ------------------------------------------------------------------
    Route("POST", "/notes/{title}/close", notes.close_note, ("tickets",),
          "Close a ticket", NoteOut, responses={**VALIDATION, **NOT_FOUND}),
    Route("POST", "/notes/{title}/reopen", notes.reopen_note, ("tickets",),
          "Reopen a ticket", NoteOut, responses={**VALIDATION, **NOT_FOUND}),

    # --- meta ---------------------------------------------------------------------
    Route("GET", "/schema", meta.get_schema, ("meta",),
          "Kinds, fields, vocabularies", SchemaOut),
    Route("GET", "/problems", meta.get_problems, ("meta",),
          "Notes that fail to validate", list[Problem]),
    Route("GET", "/health", meta.health, ("meta",),
          "Liveness and vault reachability"),
)


def build_router() -> APIRouter:
    """Turn the table into a router.

    `add_api_route` rather than the decorators, because the decorator form has to wrap
    a function at definition time -- which is exactly the coupling this file exists to
    remove.
    """
    router = APIRouter()
    for route in ROUTES:
        router.add_api_route(
            route.path,
            route.handler,
            methods=[route.method],
            tags=list(route.tags),
            summary=route.summary,
            response_model=route.response_model,
            status_code=route.status_code,
            responses=route.responses,
        )
    return router
