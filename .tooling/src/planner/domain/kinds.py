"""The ten note types: what fields each carries, where it lives, how it looks.

Obsidian has no note-type primitive. A "kind" here is a convention with teeth only
where something enforces it -- this module, plus the Triage base for anything that
never came through the API. The `kind` property is retained on every note precisely
because it is what makes the types visible to Bases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .vocabularies import (
    CONTAINER_STATUS,
    DECISION_STATUS,
    DOC_STATUS,
    ROUTINE_STATUS,
    TICKET_STATUS,
)


@dataclass(frozen=True)
class Kind:
    """One note type: where it lives, what it may carry, how it looks."""

    name: str
    folder: str
    icon: str
    colour: str
    statuses: tuple[str, ...]
    default_status: str | None
    fields: tuple[str, ...]  # beyond the shared ones
    parent_kinds: tuple[str, ...] = ()  # what `parent` may point at
    has_done: bool = False


#: Shared by every note. `created` is set on write; icon/iconColor are derived.
SHARED = ("kind", "icon", "iconColor", "created")

KINDS: dict[str, Kind] = {
    k.name: k
    for k in [
        Kind("area", "Items", "LiLandPlot", "#8B5CF6", CONTAINER_STATUS, "active", ()),
        Kind(
            "project",
            "Items",
            "LiFolderKanban",
            "#3B82F6",
            CONTAINER_STATUS,
            "active",
            ("area", "priority", "due", "closed"),
        ),
        Kind(
            "epic",
            "Items",
            "LiLayers2",
            "#14B8A6",
            TICKET_STATUS,
            "backlog",
            ("type", "parent", "project", "priority", "due", "closed"),
            parent_kinds=("project",),
            has_done=True,
        ),
        Kind(
            "task",
            "Items",
            "LiSquareCheck",
            "#D9A21B",
            TICKET_STATUS,
            "todo",
            (
                "type",
                "parent",
                "project",
                "priority",
                "due",
                "scheduled",
                "closed",
                "blocked_by",
            ),
            parent_kinds=("epic", "project", "meeting"),
            has_done=True,
        ),
        Kind(
            "subtask",
            "Items",
            "LiCornerDownRight",
            "#B4762A",
            TICKET_STATUS,
            "todo",
            ("type", "parent", "project", "priority", "due", "closed"),
            parent_kinds=("task",),
            has_done=True,
        ),
        Kind(
            "routine",
            "Items",
            "LiRepeat1",
            "#10B981",
            ROUTINE_STATUS,
            "active",
            ("area", "recur", "last_done"),
        ),
        Kind(
            "doc",
            "Docs",
            "LiFileText",
            "#64748B",
            DOC_STATUS,
            "draft",
            ("project", "area"),
        ),
        Kind(
            "decision",
            "Docs",
            "LiGitBranch",
            "#EC4899",
            DECISION_STATUS,
            "proposed",
            ("project", "date", "supersedes"),
        ),
        Kind(
            "meeting",
            "Meetings",
            "LiUsers2",
            "#06B6D4",
            (),
            None,
            ("project", "date", "attendees"),
        ),
        Kind("review", "Reviews", "LiCalendarCheck", "#6366F1", (), None, ("week",)),
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

#: Generated from the registry above rather than written out again, so a new kind
#: reaches the DTOs, the OpenAPI document and the MCP tool schemas without anyone
#: remembering to update three places.
KindEnum = StrEnum("KindEnum", {k.upper(): k for k in KIND_NAMES})


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
    """The folder a note of this kind belongs in."""
    return KINDS[kind].folder
