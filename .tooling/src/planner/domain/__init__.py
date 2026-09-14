"""Pure domain: entities, rules and vocabularies. No IO, no framework.

Nothing in here imports FastAPI, pydantic or the filesystem, which is what lets the
same rules back an HTTP API, an MCP server, and a CLI without any of them owning the
definition of what a task is.
"""

from .errors import (
    ChildrenExistError,
    NoteExistsError,
    NoteNotFoundError,
    PlannerError,
    ValidationError,
)
from .note import Note, unwrap_link, wrap_link
from .schema import (
    ALL_STATUS,
    CLOSED_STATUS,
    ISSUE_TYPE,
    KIND_NAMES,
    KINDS,
    PRIORITY_RANGE,
    RECUR,
    TICKET_KINDS,
    TICKET_STATUS,
    ClosingStatusEnum,
    IssueTypeEnum,
    Kind,
    KindEnum,
    RecurEnum,
    StatusEnum,
    allowed_fields,
    folder_for,
)

__all__ = [
    "ALL_STATUS",
    "CLOSED_STATUS",
    "ISSUE_TYPE",
    "KINDS",
    "KIND_NAMES",
    "PRIORITY_RANGE",
    "RECUR",
    "TICKET_KINDS",
    "TICKET_STATUS",
    "ChildrenExistError",
    "ClosingStatusEnum",
    "IssueTypeEnum",
    "Kind",
    "KindEnum",
    "Note",
    "NoteExistsError",
    "NoteNotFoundError",
    "PlannerError",
    "RecurEnum",
    "StatusEnum",
    "ValidationError",
    "allowed_fields",
    "folder_for",
    "unwrap_link",
    "wrap_link",
]
