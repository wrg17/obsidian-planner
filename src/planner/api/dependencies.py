"""Wiring. The controllers ask for a NoteService and never learn where notes live.

`PLANNER_VAULT` is read per request rather than captured at import, so tests can point
the app at a temporary vault without reimporting the module -- and so a running server
survives the vault being pointed somewhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..repository.markdown import MarkdownNoteRepository
from ..service.notes import NoteService


def get_repository() -> MarkdownNoteRepository:
    """The vault, with the Postgres audit log when PLANNER_DSN points at a reachable
    database and the file journal otherwise."""
    return MarkdownNoteRepository(
        Path(os.environ.get("PLANNER_VAULT", ".")),
        dsn=os.environ.get("PLANNER_DSN"),
    )


def get_service() -> NoteService:
    return NoteService(get_repository())
