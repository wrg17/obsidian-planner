"""FastAPI assembly: middleware, routes, OpenAPI metadata.

Assembly only. Anything that decides something belongs in the service; anything that
knows how to store a note belongs in the repository; every endpoint is declared in
routes.py.

The system invariants -- the properties that hold at every endpoint -- are defined in
`invariants.py` as data, and both the prose form and the table published in the OpenAPI
description are generated from it. They used to be written twice in this file, which is
how nine rules become nine rules and nine slightly different rules.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .dependencies import get_repository
from .docs import swagger_ui
from .invariants import as_markdown_table
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

DESCRIPTION = f"""
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

{as_markdown_table()}
"""


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        # Swagger UI is served by hand below so it can carry a theme; FastAPI would
        # otherwise register its own /docs first and win.
        docs_url=None,
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

    @app.get("/docs", include_in_schema=False)
    def docs():
        return swagger_ui(openapi_url=app.openapi_url, title=f"{app.title} — API")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    return app


app = create_app()
