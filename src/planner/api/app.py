"""FastAPI assembly: middleware, routers, OpenAPI metadata.

Assembly only. Anything that decides something belongs in the service; anything that
knows how to store a note belongs in the repository.

===============================================================================
SYSTEM INVARIANTS
===============================================================================

Properties that hold across every endpoint. Per-endpoint invariants are documented
on the routes themselves and are meant to be *instances* of these, not exceptions to
them; where an endpoint cannot honour one, it says so and gives the reason.

The vault is a folder of markdown that Obsidian edits too, at any moment, with no
locking. That splits the guarantees into two kinds, and conflating them is how an API
over a shared store ends up promising more than it can deliver:

    GUARANTEE   what this API will never itself do
    DETECTION   what it will tell you about when someone else has done it

S1. CLOSURE (guarantee, with one stated exception)
    No operation may produce a state that another operation would refuse to create.
    A write path that rejects a dangling `parent` while a delete path manufactures
    one is not a validated system, only a system with validation in it. This is why
    DELETE refuses to orphan children rather than silently succeeding.

    Links come in two kinds and are protected differently:

      STRUCTURAL   `parent`, `project`, `area` -- the hierarchy depends on them.
                   Protected on both sides: they cannot be created dangling, and a
                   note cannot be deleted out from under one. Closure is absolute.

      REFERENCE    `blocked_by`, `supersedes` -- one note mentioning another.
                   Protected on write only. Deleting a blocker is a legitimate act,
                   and both alternatives are worse: refusing to delete anything
                   mentioned anywhere would make the vault immovable, and silently
                   editing notes the caller never named would be a surprise write.
                   So a delete CAN leave a dangling reference, and GET /problems
                   reports it. This is the sole exception, and it is a deliberate
                   trade rather than an oversight.

S2. PURITY OF READS (guarantee)
    GET never changes the vault. No lazy migration, no touching mtimes -- mtime is
    load-bearing here, because Triage's "stale" view reads it and Iconize repaints on
    it.

S3. ATOMICITY OF WRITES (guarantee)
    A rejected write leaves the vault byte-identical. Validation completes before the
    first byte is written; there is no partially-applied note.

S4. ONE ERROR SHAPE (guarantee)
    Every deliberate 4xx is {"detail": str, "field": str | null}. Both validation
    layers -- the DTO enums and the domain -- normalise to it, because which of the
    two fired is an implementation detail no client should have to model.

S5. STORAGE IS NOT THE CONTRACT (guarantee)
    Wikilink syntax, folder placement and icon names never cross the wire. Links are
    plain titles in and out; `kind` decides the folder; `icon`/`iconColor` are derived
    and are not echoed, so a client cannot send one that disagrees.

S6. DECLARED IDEMPOTENCE (guarantee)
    An operation documented as idempotent is idempotent. PATCH, close and reopen are.
    POST is not, and says so. DELETE is deliberately NOT idempotent: the second call
    404s, matching GET and PATCH on a missing note, so "did that exist?" has one
    answer across the API rather than a special case.

S7. TRANSPORT PARITY (guarantee)
    REST and MCP call the same NoteService. A rule enforced on one is enforced on the
    other; neither holds business logic of its own.

S8. TRIAGE COMPLETENESS (detection)
    GET /problems reports every state the API would refuse to create -- bad
    vocabularies, unparseable frontmatter, and structural links that do not resolve.
    S1 keeps the API from creating them; S8 is how you find the ones that arrived by
    hand. A vault built solely through this API always has an empty /problems.

    Because of the S1 exception above, "empty by construction" holds for creates and
    updates but not across a delete: removing a note that something else references
    leaves a reported dangling reference. That is the one way a well-behaved client
    can put a row in /problems.

    Note that /notes and /problems OVERLAP rather than partition. A note that parses
    but fails validation appears in both, deliberately: excluding it from /notes would
    leave it repairable only by hand in Obsidian. Their union is every note on disk --
    that is the property worth having, not disjointness.

S9. ROUND-TRIP FIDELITY (guarantee)
    What POST returns is what a subsequent GET returns. Writing a note and reading it
    back is lossless, including the markdown body.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .dependencies import get_repository
from .middleware import correlation_id, install_error_handlers
from .routes import build_router

log = logging.getLogger("planner.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Recover any transaction a crash abandoned, before serving a single request.

    Serving first would let a client read a vault that is halfway through an operation
    nobody is going to finish. It costs one stat when there is nothing to recover.

    Conflicts are logged rather than raised: a file changed outside this process since
    the crash is left exactly as it is, and refusing to start over it would strand the
    user with an API they cannot use to fix their own notes.
    """
    report = get_repository().recover()
    if report:
        log.warning("recovered an interrupted transaction: %d restored, %d untouched",
                    len(report.restored), len(report.untouched))
        for conflict in report.conflicts:
            log.warning("left alone (%s): %s", conflict.reason, conflict.path)
    yield

DESCRIPTION = """
Jira-style tickets and Confluence-style docs over an Obsidian vault.

The vault is a folder of markdown files that Obsidian also edits, by hand, at any
moment. This API is one of several front ends over the same service layer -- there is
also an MCP server -- so a rule enforced here is enforced everywhere.

**Links are plain titles.** Send `"parent": "Design system"`; storage writes
`parent: "[[Design system]]"`. Callers should not need to know Obsidian's link syntax.

**Which fields apply depends on `kind`.** Sending one that does not belong is a 422.
`GET /schema` publishes the rules, generated from the same module that enforces them.

### System invariants

Properties that hold at every endpoint. Each operation documents its own, numbered and
referring back to these. Because the vault is shared with Obsidian, they divide into
what this API will never itself do, and what it will tell you about afterwards.

| | | |
|---|---|---|
| **S1** | CLOSURE | guarantee | No operation produces a state another would refuse. Structural links (`parent`, `project`, `area`) are protected on both sides; reference links (`blocked_by`, `supersedes`) on write only — deleting a blocker may leave a dangling reference, which `/problems` reports. |
| **S2** | PURITY OF READS | guarantee | `GET` never writes, and never touches mtime. |
| **S3** | ATOMICITY | guarantee | A rejected write leaves the vault byte-identical. |
| **S4** | ONE ERROR SHAPE | guarantee | Every deliberate 4xx is `{detail, field}`. |
| **S5** | STORAGE IS NOT THE CONTRACT | guarantee | No wikilinks, folders or icon names cross the wire. |
| **S6** | DECLARED IDEMPOTENCE | guarantee | `PATCH`, close and reopen are idempotent; `POST` is not; `DELETE` deliberately 404s on the second call. |
| **S7** | TRANSPORT PARITY | guarantee | REST and MCP share one service; neither holds rules of its own. |
| **S8** | TRIAGE COMPLETENESS | detection | `/problems` reports every state the API would refuse. `/notes` and `/problems` overlap; their union is the whole vault. |
| **S9** | ROUND-TRIP FIDELITY | guarantee | What `POST` returns is what `GET` returns. |
"""


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="Planner",
        version="0.2.0",
        summary="Typed tickets and docs over an Obsidian vault.",
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "notes", "description": "CRUD over every note kind."},
            {"name": "tickets", "description": "Operations only work items support."},
            {"name": "hierarchy", "description": "Walking parent/child relationships."},
            {"name": "meta", "description": "Schema, vault health, and triage."},
        ],
    )
    app.middleware("http")(correlation_id)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    install_error_handlers(app)
    # One call: every endpoint is declared in routes.py, which is the file to read to
    # learn what this API exposes.
    app.include_router(build_router())

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    return app


app = create_app()
