"""Facade over the domain's rules, so callers have one import rather than three.

Split by what changes together: `vocabularies` holds the value sets and is what the API
and MCP publish, `fields` holds property types and is downstream of Obsidian's own
config, `kinds` composes both into the ten note types. This module re-exports all of
it, because "the schema" is one idea to everything outside the domain and the split is
an internal concern.
"""

from __future__ import annotations

from .fields import (  # noqa: F401
    CHECKBOX, DATE, DATE_FIELDS, FIELD_TYPES, LINK, LINK_FIELDS, LINK_LIST,
    LINK_LIST_FIELDS, LIST_FIELDS, NUMBER, TEXT, TEXT_LIST,
)
from .kinds import (  # noqa: F401
    KIND_NAMES, KINDS, SHARED, TICKET_KINDS, Kind, KindEnum, allowed_fields,
    folder_for,
)
from .vocabularies import (  # noqa: F401
    ALL_STATUS, CLOSED_STATUS, CONTAINER_STATUS, DECISION_STATUS, DOC_STATUS,
    ISSUE_TYPE, PRIORITY_RANGE, RECUR, ROUTINE_STATUS, TICKET_STATUS,
    ClosingStatusEnum, IssueTypeEnum, RecurEnum, StatusEnum,
)
