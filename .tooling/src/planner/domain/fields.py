"""Property names, their storage types, and the groupings derived from them.

Mirrors .obsidian/types.json, which is what gives date pickers, numeric sort on
priority and link-list behaviour on blocked_by. Duplicated here deliberately: that file
is app-owned state Obsidian rewrites, and the API must be able to coerce and validate
without reading configuration it does not control.

The groupings at the bottom are computed rather than listed, so adding a field to
FIELD_TYPES puts it in the right set automatically. A field with no entry gets no
coercion -- a date would stay a string and compare wrongly -- which is why
domain/kinds.py has a test asserting every allowed field appears here.
"""

from __future__ import annotations

# --- field types ------------------------------------------------------------------

TEXT, DATE, NUMBER, CHECKBOX, LINK, LINK_LIST, TEXT_LIST = (
    "text",
    "date",
    "number",
    "checkbox",
    "link",
    "link_list",
    "text_list",
)

#: Property name -> Obsidian property type, mirroring .obsidian/types.json. Kept here
#: as well so the API can coerce and validate without reading app-owned config.
FIELD_TYPES = {
    "kind": TEXT,
    "status": TEXT,
    "type": TEXT,
    "recur": TEXT,
    "week": TEXT,
    "icon": TEXT,
    "iconColor": TEXT,
    "priority": NUMBER,
    "done": CHECKBOX,
    "due": DATE,
    "scheduled": DATE,
    "closed": DATE,
    "last_done": DATE,
    "created": DATE,
    "date": DATE,
    "parent": LINK,
    "project": LINK,
    "area": LINK,
    "blocked_by": LINK_LIST,
    "supersedes": LINK_LIST,
    "attendees": TEXT_LIST,
    "demo": CHECKBOX,
}

LINK_FIELDS = {k for k, v in FIELD_TYPES.items() if v == LINK}
LINK_LIST_FIELDS = {k for k, v in FIELD_TYPES.items() if v == LINK_LIST}
DATE_FIELDS = {k for k, v in FIELD_TYPES.items() if v == DATE}
LIST_FIELDS = LINK_LIST_FIELDS | {k for k, v in FIELD_TYPES.items() if v == TEXT_LIST}
