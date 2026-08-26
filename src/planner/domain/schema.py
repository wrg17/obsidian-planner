"""The note types, their fields, and the vocabularies they are checked against.

This module is the single source of truth. The vault, the API and the demo generator
all read their rules from here, because the alternative -- the same field list written
out in a template, a base file and a generator -- is what let three copies of one
formula drift apart until a weekday routine reported itself missed every Sunday.

Obsidian has no note-type primitive and Bases has no enum property type. A "type" here
is therefore a convention with teeth only where something enforces it: this module,
plus the Triage base's "Invalid values" view, which catches by eye what never went
through the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# --- vocabularies -----------------------------------------------------------------

TICKET_STATUS = ("backlog", "todo", "doing", "blocked", "review", "done", "cancelled")
CONTAINER_STATUS = ("active", "paused", "done")
ROUTINE_STATUS = ("active", "paused")
DOC_STATUS = ("draft", "current", "stale")
DECISION_STATUS = ("proposed", "accepted", "rejected", "superseded")

ISSUE_TYPE = ("feature", "bug", "chore", "spike", "research")
RECUR = ("daily", "weekdays", "weekly", "monthly")
PRIORITY_RANGE = (1, 4)

#: Statuses that mean "no longer open". `done` is additive with the `done` checkbox --
#: ticking either one closes the ticket, which is what the board's `open` formula reads.
CLOSED_STATUS = ("done", "cancelled")

# --- field types ------------------------------------------------------------------

TEXT, DATE, NUMBER, CHECKBOX, LINK, LINK_LIST, TEXT_LIST = (
    "text", "date", "number", "checkbox", "link", "link_list", "text_list",
)

#: Property name -> Obsidian property type, mirroring .obsidian/types.json. Kept here
#: as well so the API can coerce and validate without reading app-owned config.
FIELD_TYPES = {
    "kind": TEXT, "status": TEXT, "type": TEXT, "recur": TEXT, "week": TEXT,
    "icon": TEXT, "iconColor": TEXT,
    "priority": NUMBER,
    "done": CHECKBOX,
    "due": DATE, "scheduled": DATE, "closed": DATE, "last_done": DATE,
    "created": DATE, "date": DATE,
    "parent": LINK, "project": LINK, "area": LINK,
    "blocked_by": LINK_LIST, "supersedes": LINK_LIST, "attendees": TEXT_LIST,
    "demo": CHECKBOX,
}

LINK_FIELDS = {k for k, v in FIELD_TYPES.items() if v == LINK}
LINK_LIST_FIELDS = {k for k, v in FIELD_TYPES.items() if v == LINK_LIST}
DATE_FIELDS = {k for k, v in FIELD_TYPES.items() if v == DATE}
LIST_FIELDS = LINK_LIST_FIELDS | {k for k, v in FIELD_TYPES.items() if v == TEXT_LIST}


@dataclass(frozen=True)
class Kind:
    name: str
    folder: str
    icon: str
    colour: str
    statuses: tuple[str, ...]
    default_status: str | None
    fields: tuple[str, ...]           # beyond the shared ones
    parent_kinds: tuple[str, ...] = ()   # what `parent` may point at
    has_done: bool = False


#: Shared by every note. `created` is set on write; icon/iconColor are derived.
SHARED = ("kind", "icon", "iconColor", "created")

KINDS: dict[str, Kind] = {
    k.name: k for k in [
        Kind("area", "Items", "LiLandPlot", "#8B5CF6",
             CONTAINER_STATUS, "active", ()),
        Kind("project", "Items", "LiFolderKanban", "#3B82F6",
             CONTAINER_STATUS, "active", ("area", "priority", "due", "closed")),
        Kind("epic", "Items", "LiLayers2", "#14B8A6",
             TICKET_STATUS, "backlog",
             ("type", "parent", "project", "priority", "due", "closed"),
             parent_kinds=("project",), has_done=True),
        Kind("task", "Items", "LiSquareCheck", "#D9A21B",
             TICKET_STATUS, "todo",
             ("type", "parent", "project", "priority", "due", "scheduled", "closed",
              "blocked_by"),
             parent_kinds=("epic", "project", "meeting"), has_done=True),
        Kind("subtask", "Items", "LiCornerDownRight", "#B4762A",
             TICKET_STATUS, "todo",
             ("type", "parent", "project", "priority", "due", "closed"),
             parent_kinds=("task",), has_done=True),
        Kind("routine", "Items", "LiRepeat1", "#10B981",
             ROUTINE_STATUS, "active", ("area", "recur", "last_done")),
        Kind("doc", "Docs", "LiFileText", "#64748B",
             DOC_STATUS, "draft", ("project", "area")),
        Kind("decision", "Docs", "LiGitBranch", "#EC4899",
             DECISION_STATUS, "proposed", ("project", "date", "supersedes")),
        Kind("meeting", "Meetings", "LiUsers2", "#06B6D4",
             (), None, ("project", "date", "attendees")),
        Kind("review", "Reviews", "LiCalendarCheck", "#6366F1",
             (), None, ("week",)),
    ]
}

KIND_NAMES = tuple(KINDS)
TICKET_KINDS = ("epic", "task", "subtask")

# --- enums ------------------------------------------------------------------------
#
# Generated from the tuples above rather than written out again. A hand-maintained
# second copy is how the OpenAPI document ends up promising something the validator
# does not enforce -- and for an MCP client that gap is worse than a missing check,
# because a model reads the tool schema as the truth and will confidently send
# "Epic" if nothing says otherwise.

KindEnum = StrEnum("KindEnum", {k.upper(): k for k in KIND_NAMES})
IssueTypeEnum = StrEnum("IssueTypeEnum", {v.upper(): v for v in ISSUE_TYPE})
RecurEnum = StrEnum("RecurEnum", {v.upper(): v for v in RECUR})

#: Every status any kind may take. Which subset applies depends on the kind, and that
#: is enforced in the domain -- but declaring the union still beats a bare string.
ALL_STATUS = tuple(dict.fromkeys(
    TICKET_STATUS + CONTAINER_STATUS + ROUTINE_STATUS + DOC_STATUS + DECISION_STATUS))
StatusEnum = StrEnum("StatusEnum", {v.upper().replace("-", "_"): v for v in ALL_STATUS})

#: Statuses that close a ticket, as an enum for the close endpoint.
ClosingStatusEnum = StrEnum("ClosingStatusEnum", {v.upper(): v for v in CLOSED_STATUS})


def allowed_fields(kind: str) -> tuple[str, ...]:
    """Every property that may appear on a note of this kind."""
    k = KINDS[kind]
    base = list(SHARED)
    if k.statuses:
        base.append("status")
    if k.has_done:
        base.append("done")
    return tuple(base + list(k.fields))


def folder_for(kind: str) -> str:
    return KINDS[kind].folder
