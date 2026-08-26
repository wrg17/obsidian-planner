"""HTTP-specific DTOs.

The note request models live in `contracts`, because the MCP server needs the same
shape and neither transport should import the other. What remains here is the part
that only makes sense over HTTP: how a note is rendered in a response, and the error
body every deliberate 4xx uses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.note import NoteIn, NotePatch  # noqa: F401 - re-exported for routes

class NoteOut(BaseModel):
    """A note as stored. Dates are ISO strings and links are bare titles; `icon` and
    `iconColor` are derived from kind and deliberately not echoed."""

    model_config = ConfigDict(extra="allow")

    kind: str
    title: str
    body: str = ""


class Problem(BaseModel):
    title: str
    message: str


class ErrorOut(BaseModel):
    """Every deliberate 4xx from this API. FastAPI's own request-shape failures are
    normalised into the same form by middleware, so a client models one error."""

    detail: str
    field: str | None = Field(None, description="The offending property, when known.")


class KindOut(BaseModel):
    name: str
    folder: str
    statuses: list[str]
    default_status: str | None
    fields: list[str]
    parent_kinds: list[str]
    has_done: bool


class SchemaOut(BaseModel):
    kinds: list[KindOut]
    vocabularies: dict[str, list]
