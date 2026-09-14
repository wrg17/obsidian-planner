"""Wiring. The controllers ask for a NoteService and never learn where notes live.

`PLANNER_VAULT` is read per request rather than captured at import, so tests can point
the app at a temporary vault without reimporting the module -- and so a running server
survives the vault being pointed somewhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request

from ..repository.markdown import MarkdownNoteRepository
from ..service.notes import NoteService


def get_repository() -> MarkdownNoteRepository:
    """The vault, with whichever journal is reachable.

    Postgres when PLANNER_DSN points at a live database, the file journal otherwise.
    """
    return MarkdownNoteRepository(
        Path(os.environ.get("PLANNER_VAULT", ".")),
        dsn=os.environ.get("PLANNER_DSN"),
    )


def build_service(request=None) -> NoteService:
    """A service whose writes are labelled for the audit log.

    Done here rather than in each controller so no route can forget. The request id is
    the one the middleware already generated, which makes an audit row traceable back
    to the HTTP call that caused it -- and, through the access log, to everything else
    that happened in the same request.

    `request` is optional so the same factory serves callers with no HTTP request to
    speak of -- tests, and anything wiring the service up directly. Those writes are
    unlabelled rather than needing a fake request invented for them.
    """
    repository = get_repository()
    if request is not None:
        repository.describe(
            summary=f"{request.method} {request.url.path}",
            actor="rest",
            request_id=getattr(request.state, "request_id", ""),
        )
    return NoteService(repository)


def get_service(request: Request) -> NoteService:
    """The FastAPI dependency.

    A thin wrapper because FastAPI cannot inject an optional Request: annotating the
    factory `Request | None` makes it try to build a Pydantic field out of it. Keeping
    the two separate leaves `build_service` usable from anywhere.
    """
    return build_service(request)
