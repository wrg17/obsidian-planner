"""Pure domain: entities, rules and vocabularies. No IO, no framework.

Nothing in here imports FastAPI, pydantic or the filesystem, which is what lets the
same rules back an HTTP API, an MCP server, and a CLI without any of them owning the
definition of what a task is.
"""

from .errors import (
    ChildrenExist, NoteExists, NoteNotFound, PlannerError, ValidationError,
)
from .note import Note, unwrap_link, wrap_link
from .schema import (
    ALL_STATUS, CLOSED_STATUS, ISSUE_TYPE, KIND_NAMES, KINDS, PRIORITY_RANGE, RECUR,
    TICKET_KINDS, TICKET_STATUS, ClosingStatusEnum, IssueTypeEnum, Kind, KindEnum,
    RecurEnum, StatusEnum, allowed_fields, folder_for,
)

__all__ = [
    "Note", "unwrap_link", "wrap_link",
    "PlannerError", "ValidationError", "NoteNotFound", "NoteExists", "ChildrenExist",
    "KINDS", "Kind", "KIND_NAMES", "TICKET_KINDS", "TICKET_STATUS", "ALL_STATUS",
    "ISSUE_TYPE", "RECUR", "PRIORITY_RANGE", "CLOSED_STATUS",
    "KindEnum", "StatusEnum", "IssueTypeEnum", "RecurEnum", "ClosingStatusEnum",
    "allowed_fields", "folder_for",
]
