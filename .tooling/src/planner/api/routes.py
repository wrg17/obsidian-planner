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

from ..contracts.operations import OPERATIONS
from .handlers import meta, notes
from .schemas import ErrorOut, NoteOut, Problem, SchemaOut

#: Attached to every route that can fail validation, which is all of them: both the DTO
#: enums and the domain normalise to one error shape (S4).
VALIDATION = {422: {"model": ErrorOut, "description": "Validation failed"}}
NOT_FOUND = {404: {"model": ErrorOut, "description": "No such note"}}
CONFLICT = {409: {"model": ErrorOut, "description": "Conflicts with existing state"}}


@dataclass(frozen=True)
class Route:
    """One operation, and everything said about it.

    `summary` is the table cell. `guidance` is what someone meeting this operation for
    the first time needs -- when to reach for it, what to call first, what will bite.
    The handler's docstring carries the invariants.

    Guidance lives here rather than in either transport because both need it, and for
    the same reason: a developer new to the repo does not know to call /schema first
    any more than a model does. It used to exist only in the MCP tool descriptions,
    which meant the Swagger reader got the worse documentation of the two.
    """

    method: str
    path: str
    handler: object
    tags: tuple[str, ...]
    response_model: object = None
    status_code: int = 200
    responses: dict = field(default_factory=dict)

    @property
    def docs(self):
        """Everything said about this operation, from the shared table.

        A route with no entry is an error rather than a blank description: an endpoint
        nobody has written a sentence about is not ready to be served, and silently
        publishing an empty one is how it ships that way.
        """
        try:
            return OPERATIONS[(self.method, self.path)]
        except KeyError:
            raise KeyError(
                f"{self.method} {self.path} has no entry in "
                f"contracts/operations.py -- every route needs a summary and "
                f"guidance before it can be served"
            ) from None

    @property
    def summary(self) -> str:
        """The one-line label, from the shared operations table."""
        return self.docs.summary

    @property
    def description(self) -> str:
        """Guidance then invariants -- the same text OpenAPI and the MCP tool show."""
        return self.docs.description


#: Read top to bottom as the API's surface. Order here is the order in the OpenAPI
#: document and therefore in Swagger, so related operations sit together.
ROUTES: tuple[Route, ...] = (
    # --- notes --------------------------------------------------------------------
    Route(
        "GET",
        "/notes",
        notes.list_notes,
        ("notes",),
        list[NoteOut],
        responses=VALIDATION,
    ),
    Route(
        "POST",
        "/notes",
        notes.create_note,
        ("notes",),
        NoteOut,
        201,
        {**VALIDATION, **CONFLICT},
    ),
    Route(
        "POST",
        "/notes/bulk",
        notes.create_many,
        ("notes",),
        list[NoteOut],
        201,
        {**VALIDATION, **CONFLICT},
    ),
    Route(
        "GET",
        "/notes/{title}",
        notes.get_note,
        ("notes",),
        NoteOut,
        responses=NOT_FOUND,
    ),
    Route(
        "PATCH",
        "/notes/{title}",
        notes.update_note,
        ("notes",),
        NoteOut,
        # 409 as well as 404 and 422: a closed note is refused. The request is well
        # formed and the note exists, so neither of the others fits -- and a client
        # that retries on 422 would loop.
        responses={
            **VALIDATION,
            **NOT_FOUND,
            409: {"model": ErrorOut, "description": "The note is closed; reopen first"},
        },
    ),
    Route(
        "DELETE",
        "/notes/{title}",
        notes.delete_note,
        ("notes",),
        None,
        204,
        {
            **NOT_FOUND,
            409: {"model": ErrorOut, "description": "Would orphan child notes"},
        },
    ),
    # --- hierarchy ----------------------------------------------------------------
    Route(
        "GET",
        "/notes/{title}/children",
        notes.get_children,
        ("hierarchy",),
        list[NoteOut],
        responses=NOT_FOUND,
    ),
    # --- tickets ------------------------------------------------------------------
    Route(
        "POST",
        "/notes/{title}/close",
        notes.close_note,
        ("tickets",),
        NoteOut,
        responses={**VALIDATION, **NOT_FOUND},
    ),
    Route(
        "POST",
        "/notes/{title}/reopen",
        notes.reopen_note,
        ("tickets",),
        NoteOut,
        responses={**VALIDATION, **NOT_FOUND},
    ),
    # --- meta ---------------------------------------------------------------------
    Route("GET", "/schema", meta.get_schema, ("meta",), SchemaOut),
    Route("GET", "/problems", meta.get_problems, ("meta",), list[Problem]),
    Route("GET", "/health", meta.health, ("meta",)),
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
            # Guidance plus the handler's invariants. Set explicitly rather than left
            # to the docstring, so the same text reaches OpenAPI and the MCP tool.
            description=route.description,
            response_model=route.response_model,
            status_code=route.status_code,
            responses=route.responses,
        )
    return router
