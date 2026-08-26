"""FastAPI assembly: middleware, routers, OpenAPI metadata.

Assembly only. Anything that decides something belongs in the service; anything that
knows how to store a note belongs in the repository.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .middleware import correlation_id, install_error_handlers
from .routers import meta, notes

DESCRIPTION = """
Jira-style tickets and Confluence-style docs over an Obsidian vault.

The vault is a folder of markdown files that Obsidian also edits, by hand, at any
moment. This API is one of several front ends over the same service layer -- there is
also an MCP server -- so a rule enforced here is enforced everywhere.

**Links are plain titles.** Send `"parent": "Design system"`; storage writes
`parent: "[[Design system]]"`. Callers should not need to know Obsidian's link syntax.

**Which fields apply depends on `kind`.** Sending one that does not belong is a 422.
`GET /schema` publishes the rules, generated from the same module that enforces them.
"""


def create_app() -> FastAPI:
    app = FastAPI(
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
    app.include_router(notes.router)
    app.include_router(meta.router)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    return app


app = create_app()
