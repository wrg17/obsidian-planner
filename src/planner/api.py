"""REST API over the vault, with OpenAPI at /openapi.json and Swagger UI at /docs.

    uvicorn planner.api:app --reload          # PLANNER_VAULT=. by default

The API speaks plain titles, not Obsidian link syntax: send `"parent": "Design system"`
and the storage layer writes `parent: "[[Design system]]"`. Callers should not need to
know how Obsidian resolves links in order to file a ticket.

One schema quirk is worth stating up front, because it shows in the docs. Every note
kind shares one request model with all fields optional, rather than ten models in a
discriminated union. Obsidian itself has no note-type primitive -- a "kind" is a
convention -- and mirroring that honestly keeps the generated docs readable. Which
fields apply to which kind is enforced server-side and published at GET /schema.
"""

from __future__ import annotations

import os
import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import schema
from .errors import NoteExists, NoteNotFound, ValidationError
from .note import Note
from .vault import Vault

app = FastAPI(
    title="Planner",
    version="0.1.0",
    summary="Jira-style tickets and Confluence-style docs over an Obsidian vault.",
    description=__doc__,
    openapi_tags=[
        {"name": "notes", "description": "CRUD over every note kind."},
        {"name": "tickets", "description": "Operations that only make sense for work items."},
        {"name": "meta", "description": "Vocabularies, kinds, and vault health."},
    ],
)


def get_vault():
    return Vault(Path(os.environ.get("PLANNER_VAULT", ".")))


# --- models -------------------------------------------------------------------------

class NoteIn(BaseModel):
    kind: str = Field(..., description=f"One of {list(schema.KIND_NAMES)}",
                      examples=["task"])
    title: str = Field(..., description="Unique vault-wide; Obsidian links by name.",
                       examples=["Pick a type scale"])
    body: str = Field("", description="Markdown after the frontmatter.")
    status: str | None = Field(None, description="Vocabulary depends on kind; see /schema.")
    type: str | None = Field(None, description=f"Issue type, one of {list(schema.ISSUE_TYPE)}")
    priority: int | None = Field(None, ge=1, le=4, description="1 is highest.")
    done: bool | None = Field(None, description="Additive with status == 'done'.")
    parent: str | None = Field(None, description="Plain title, not [[link]] syntax.",
                               examples=["Design system"])
    project: str | None = Field(
        None, description="Denormalised onto every ticket: Bases cannot walk a parent "
                          "chain, so project-wide queries need it on the note itself.")
    area: str | None = None
    due: datetime.date | None = None
    scheduled: datetime.date | None = None
    closed: datetime.date | None = None
    last_done: datetime.date | None = Field(None, description="Routines: when it was last done.")
    recur: str | None = Field(None, description=f"One of {list(schema.RECUR)}")
    date: datetime.date | None = Field(None, description="Meetings and decisions.")
    week: str | None = Field(None, description="Reviews, ISO form.", examples=["2026-W35"])
    blocked_by: list[str] | None = None
    supersedes: list[str] | None = None
    attendees: list[str] | None = None

    model_config = {"extra": "forbid"}


class NotePatch(NoteIn):
    kind: str | None = None
    title: str | None = None
    body: str | None = None


class NoteOut(BaseModel):
    kind: str
    title: str
    body: str = ""
    model_config = {"extra": "allow"}


class Problem(BaseModel):
    title: str
    message: str


class KindOut(BaseModel):
    name: str
    folder: str
    statuses: list[str]
    default_status: str | None
    fields: list[str]
    parent_kinds: list[str]


# --- error mapping ------------------------------------------------------------------

@app.exception_handler(ValidationError)
def _invalid(_request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422,
                        content={"detail": str(exc), "field": exc.field})


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NoteNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except NoteExists as exc:
        raise HTTPException(409, str(exc)) from exc


# --- routes -------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/schema", tags=["meta"], summary="Kinds, fields and vocabularies")
def get_schema() -> dict:
    """The rules the server enforces. Generated from the same module the vault
    validates against, so it cannot drift from actual behaviour."""
    return {
        "kinds": [
            KindOut(name=k.name, folder=k.folder, statuses=list(k.statuses),
                    default_status=k.default_status,
                    fields=list(schema.allowed_fields(k.name)),
                    parent_kinds=list(k.parent_kinds)).model_dump()
            for k in schema.KINDS.values()
        ],
        "vocabularies": {
            "ticket_status": list(schema.TICKET_STATUS),
            "container_status": list(schema.CONTAINER_STATUS),
            "issue_type": list(schema.ISSUE_TYPE),
            "recur": list(schema.RECUR),
            "priority_range": list(schema.PRIORITY_RANGE),
        },
    }


@app.get("/notes", tags=["notes"], response_model=list[NoteOut])
def list_notes(
    kind: str | None = Query(None, description="Filter to one kind."),
    project: str | None = Query(None, description="Plain title."),
    parent: str | None = None,
    status: str | None = None,
    open_only: bool = Query(False, alias="open",
                            description="Exclude done and cancelled work."),
    vault: Vault = Depends(get_vault),
):
    if kind is not None and kind not in schema.KINDS:
        raise HTTPException(422, f"unknown kind {kind!r}")
    where = {k: v for k, v in
             {"project": project, "parent": parent, "status": status}.items()
             if v is not None}
    notes = vault.list(kind=kind, **where)
    if open_only:
        notes = [n for n in notes if n.is_open]
    return [n.to_dict() for n in notes]


@app.get("/notes/{title}", tags=["notes"], response_model=NoteOut)
def get_note(title: str, vault: Vault = Depends(get_vault)):
    return _guard(vault.get, title).to_dict()


@app.post("/notes", tags=["notes"], response_model=NoteOut, status_code=201)
def create_note(payload: NoteIn, vault: Vault = Depends(get_vault)):
    """Create a note. Folder is derived from `kind`; `created`, `status` and `done`
    are defaulted when omitted."""
    data = payload.model_dump(exclude_none=True)
    return _guard(vault.create, Note.from_dict(data)).to_dict()


@app.patch("/notes/{title}", tags=["notes"], response_model=NoteOut)
def update_note(title: str, payload: NotePatch, vault: Vault = Depends(get_vault)):
    """Partial update. A field sent as `null` is removed from the note."""
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("kind", None)
    changes.pop("title", None)
    return _guard(vault.update, title, **changes).to_dict()


@app.delete("/notes/{title}", tags=["notes"], status_code=204)
def delete_note(title: str, vault: Vault = Depends(get_vault)):
    _guard(vault.delete, title)


@app.post("/notes/{title}/close", tags=["tickets"], response_model=NoteOut)
def close_note(
    title: str,
    status: str = Query("done", description="`done` or `cancelled`."),
    on: datetime.date | None = Query(None, description="Defaults to today."),
    vault: Vault = Depends(get_vault),
):
    """Set status, tick `done`, and stamp `closed` in one call -- the three fields
    that must move together, and the one people forget when closing by hand."""
    return _guard(vault.close, title, status=status, on=on).to_dict()


@app.get("/problems", tags=["meta"], response_model=list[Problem])
def get_problems(vault: Vault = Depends(get_vault)):
    """Notes that fail to parse or validate -- the API's equivalent of the Triage
    base. Bases has no enum property type, so a misspelled status hides work
    silently instead of erroring."""
    return [{"title": t, "message": m} for t, m in vault.problems()]
