"""Request and response DTOs.

These are the wire contract, not the domain. The distinction earns its keep at the
enum boundary: `kind` here is `KindEnum`, generated from the domain's tuple, so the
OpenAPI document declares the ten legal values instead of `"type": "string"`. A bare
string validates identically at runtime -- the domain rejects "Epic" either way -- but
it publishes nothing, and a generated client or an MCP model reads the published schema
as the truth.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..domain import schema as S


class NoteIn(BaseModel):
    """A note to create. Fields not applicable to `kind` are rejected server-side;
    GET /schema publishes which apply where."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    kind: S.KindEnum = Field(..., description="Determines the folder and the legal fields.")
    title: str = Field(..., min_length=1, description=
                       "Unique vault-wide. Obsidian resolves links by name, so a doc "
                       "and a task may not share one.", examples=["Pick a type scale"])
    body: str = Field("", description="Markdown after the frontmatter.")

    status: S.StatusEnum | None = Field(None, description=
        "Legal values depend on kind: tickets use the backlog..cancelled vocabulary, "
        "containers use active/paused/done. See GET /schema.")
    type: S.IssueTypeEnum | None = Field(None, description="Issue type; tickets only.")
    priority: int | None = Field(None, ge=S.PRIORITY_RANGE[0], le=S.PRIORITY_RANGE[1],
                                 description="1 is highest.")
    done: bool | None = Field(None, description=
        "Additive with status == 'done': ticking either closes the ticket.")

    parent: str | None = Field(None, description=
        "Plain title, not [[wikilink]] syntax. Must exist, and must be a kind that may "
        "hold this one.", examples=["Design system"])
    project: str | None = Field(None, description=
        "Denormalised onto every ticket. Bases cannot walk a parent chain, so without "
        "it 'everything in this project' is not expressible.")
    area: str | None = None

    due: datetime.date | None = None
    scheduled: datetime.date | None = None
    closed: datetime.date | None = None
    last_done: datetime.date | None = Field(None, description="Routines: last completed.")
    recur: S.RecurEnum | None = Field(None, description="Routines only.")
    date: datetime.date | None = Field(None, description="Meetings and decisions.")
    week: str | None = Field(None, description="Reviews, ISO week.", examples=["2026-W35"])

    blocked_by: list[str] | None = Field(None, description="Plain titles.")
    supersedes: list[str] | None = None
    attendees: list[str] | None = None


class NotePatch(NoteIn):
    """Partial update. Only fields present in the body are touched; a field sent as
    `null` is removed from the note. `kind` cannot be changed."""

    kind: S.KindEnum | None = None
    title: str | None = Field(None, description="Read-only; ignored if sent.")
    body: str | None = None


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
    """Every deliberate 4xx from this API. FastAPI's own request-shape failures still
    use its list-of-errors form under `detail`."""

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
