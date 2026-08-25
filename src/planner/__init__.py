"""Domain model and REST API for the Obsidian planner vault.

    from planner import Vault, Note
    vault = Vault(".")
    vault.create(kind="task", title="Pick a type scale", parent="Design system")

`planner.api` exposes the same operations over HTTP with OpenAPI docs; it is an
optional import so the core package does not require FastAPI.
"""

from .errors import NoteExists, NoteNotFound, PlannerError, ValidationError
from .note import Note
from .schema import KINDS, TICKET_KINDS
from .vault import Vault

__all__ = [
    "Vault", "Note", "KINDS", "TICKET_KINDS",
    "PlannerError", "ValidationError", "NoteNotFound", "NoteExists",
]
