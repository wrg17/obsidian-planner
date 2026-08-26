"""The value sets a note's properties are checked against, and the enums generated
from them.

Kept apart from the kinds that use them because these are the things most likely to be
read by something other than this package -- the API publishes them at /schema, the MCP
tool schemas are built from them, and both need them without dragging in the note model.

Obsidian has no enum property type, so nothing in the app enforces any of this. A
misspelled status does not error; the ticket simply stops appearing where you expect.
These tuples are the only definition, which is why the Triage base and GET /problems
exist to catch what never came through the API.
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------------
#
# Generated from the tuples above rather than written out again. A hand-maintained
# second copy is how the OpenAPI document ends up promising something the validator
# does not enforce -- and for an MCP client that gap is worse than a missing check,
# because a model reads the tool schema as the truth and will confidently send
# "Epic" if nothing says otherwise.

IssueTypeEnum = StrEnum("IssueTypeEnum", {v.upper(): v for v in ISSUE_TYPE})
RecurEnum = StrEnum("RecurEnum", {v.upper(): v for v in RECUR})

#: Every status any kind may take. Which subset applies depends on the kind, and that
#: is enforced in the domain -- but declaring the union still beats a bare string.
ALL_STATUS = tuple(dict.fromkeys(
    TICKET_STATUS + CONTAINER_STATUS + ROUTINE_STATUS + DOC_STATUS + DECISION_STATUS))
StatusEnum = StrEnum("StatusEnum", {v.upper().replace("-", "_"): v for v in ALL_STATUS})

#: Statuses that close a ticket, as an enum for the close endpoint.
ClosingStatusEnum = StrEnum("ClosingStatusEnum", {v.upper(): v for v in CLOSED_STATUS})


