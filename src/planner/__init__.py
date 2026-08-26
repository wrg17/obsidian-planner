"""Domain model, service layer and transports for the Obsidian planner vault.

Layered so that several front ends can share one set of rules:

    domain/      entities, vocabularies, validation   -- no IO, no framework
    repository/  persistence port + markdown adapter
    service/     business rules, transport-agnostic
    api/         FastAPI: middleware, controllers, DTOs
    mcp/         MCP tools over the same service

    from planner import open_vault
    service = open_vault(".")
    service.create(kind="task", title="Pick a type scale", parent="Design system")

`planner.api` and `planner.mcp` are optional imports; the core needs neither FastAPI
nor the MCP SDK.
"""

from .domain import (
    KINDS, TICKET_KINDS, Note, NoteExists, NoteNotFound, PlannerError, ValidationError,
)
from .repository.markdown import MarkdownNoteRepository
from .service.notes import NoteService


def open_vault(root) -> NoteService:
    """A service backed by the markdown vault at `root`."""
    return NoteService(MarkdownNoteRepository(root))


__all__ = [
    "open_vault", "NoteService", "MarkdownNoteRepository", "Note",
    "KINDS", "TICKET_KINDS",
    "PlannerError", "ValidationError", "NoteNotFound", "NoteExists",
]
