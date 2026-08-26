"""A note: markdown on disk, an object in Python, plain JSON over the wire.

The three representations differ in one important way. On disk a link is
`parent: "[[Design system]]"`, because that is what Obsidian resolves and what Bases
compares with `parent == this`. Over the API it is just `"Design system"` -- callers
should not have to know Obsidian's link syntax to file a ticket. The wrapping and
unwrapping happens here, at the boundary, and nowhere else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date

import yaml

from . import schema
from .errors import ValidationError

LINK_RE = re.compile(r"^\[\[(?P<target>[^\]|]+)(?:\|[^\]]*)?\]\]$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n?(?P<body>.*)\Z", re.S)


def unwrap_link(value):
    """`[[Design system]]` -> `Design system`; anything else passes through."""
    if not isinstance(value, str):
        return value
    m = LINK_RE.match(value.strip())
    return m.group("target").strip() if m else value


def wrap_link(value):
    """`Design system` -> `[[Design system]]`, idempotently."""
    if not isinstance(value, str) or not value:
        return value
    return value if LINK_RE.match(value.strip()) else f"[[{value}]]"


def _as_date(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"{field}: {value!r} is not a YYYY-MM-DD date", field) from exc


@dataclass
class Note:
    kind: str
    title: str
    fields: dict = dc_field(default_factory=dict)
    body: str = ""

    # --- construction -------------------------------------------------------------

    def __post_init__(self):
        if self.kind not in schema.KINDS:
            raise ValidationError(f"unknown kind {self.kind!r}", "kind")
        if not self.title or "/" in self.title:
            raise ValidationError(f"invalid title {self.title!r}", "title")
        self.fields = {k: v for k, v in self.fields.items() if v not in (None, "")}
        self._coerce()

    def _coerce(self):
        for key, value in list(self.fields.items()):
            if key in schema.DATE_FIELDS:
                self.fields[key] = _as_date(value, key)
            elif key in schema.LINK_FIELDS:
                self.fields[key] = unwrap_link(value)
            elif key in schema.LIST_FIELDS:
                if isinstance(value, str):
                    value = [value]
                self.fields[key] = [unwrap_link(v) for v in value]
            elif key == "priority" and value is not None:
                try:
                    self.fields[key] = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValidationError(f"priority: {value!r} is not a number",
                                          "priority") from exc

    # --- validation ---------------------------------------------------------------

    def validate(self, strict_fields=True):
        """Raise ValidationError on the first problem found.

        `strict_fields=False` tolerates extra properties, which is what reading an
        existing vault needs -- a note someone hand-edited should be reportable as
        invalid rather than unreadable.
        """
        spec = schema.KINDS[self.kind]
        allowed = set(schema.allowed_fields(self.kind)) | {"demo"}

        if strict_fields:
            for key in self.fields:
                if key not in allowed:
                    raise ValidationError(
                        f"{key!r} is not a field of kind {self.kind!r}", key)

        status = self.fields.get("status")
        if spec.statuses:
            if status is not None and status not in spec.statuses:
                raise ValidationError(
                    f"status {status!r} not one of {list(spec.statuses)}", "status")
        elif status is not None:
            raise ValidationError(f"kind {self.kind!r} has no status", "status")

        issue_type = self.fields.get("type")
        if issue_type is not None and issue_type not in schema.ISSUE_TYPE:
            raise ValidationError(
                f"type {issue_type!r} not one of {list(schema.ISSUE_TYPE)}", "type")

        recur = self.fields.get("recur")
        if recur is not None and recur not in schema.RECUR:
            raise ValidationError(
                f"recur {recur!r} not one of {list(schema.RECUR)}", "recur")

        priority = self.fields.get("priority")
        if priority is not None:
            low, high = schema.PRIORITY_RANGE
            if not low <= priority <= high:
                raise ValidationError(
                    f"priority {priority} outside {low}-{high}", "priority")
        return self

    @property
    def is_open(self):
        """Mirrors the `open` formula in the bases: the checkbox and the status are
        additive, so ticking either closes the ticket."""
        if self.fields.get("done") is True:
            return False
        return self.fields.get("status") not in schema.CLOSED_STATUS

    # --- markdown -----------------------------------------------------------------

    @classmethod
    def from_markdown(cls, text, title):
        m = FRONTMATTER_RE.match(text)
        if not m:
            # Obsidian only recognises frontmatter at byte 0; anything else is a note
            # with no properties at all, which is a real state Triage reports on.
            raise ValidationError(f"{title!r} has no frontmatter at the start of the file")
        data = yaml.safe_load(m.group("yaml")) or {}
        if not isinstance(data, dict):
            raise ValidationError(f"{title!r} frontmatter is not a mapping")
        kind = data.pop("kind", None)
        if kind is None:
            raise ValidationError(f"{title!r} has no `kind`", "kind")
        return cls(kind=kind, title=title, fields=data, body=m.group("body"))

    def to_markdown(self):
        spec = schema.KINDS[self.kind]
        out = {"kind": self.kind, "icon": spec.icon, "iconColor": spec.colour}
        # Deterministic order: shared identity first, then the kind's own fields in
        # schema order, then anything left (e.g. the demo marker).
        for key in schema.allowed_fields(self.kind):
            if key in ("kind", "icon", "iconColor"):
                continue
            if key in self.fields:
                out[key] = self.fields[key]
        for key, value in self.fields.items():
            if key not in out:
                out[key] = value

        lines = ["---"]
        for key, value in out.items():
            lines.append(self._emit(key, value))
        lines.append("---")
        # No default body here. Inventing one would make this serializer lossy: the
        # Note in memory would no longer describe the bytes on disk, and POST would
        # return something a subsequent GET contradicts. Defaults belong to the
        # service, which sets them before the note is ever written.
        return "\n".join(lines) + "\n" + self.body

    @staticmethod
    def _emit(key, value):
        if key in schema.LIST_FIELDS:
            values = value or []
            if not values:
                return f"{key}: []"
            wrapped = [wrap_link(v) if key in schema.LINK_LIST_FIELDS else v
                       for v in values]
            return f"{key}:\n" + "\n".join(f'  - "{v}"' for v in wrapped)
        if key in schema.LINK_FIELDS:
            return f'{key}: "{wrap_link(value)}"'
        if isinstance(value, bool):
            return f"{key}: {str(value).lower()}"
        if isinstance(value, date):
            return f"{key}: {value.isoformat()}"
        if key in ("icon", "iconColor", "week"):
            return f'{key}: "{value}"'
        return f"{key}: {value}"

    # --- json ---------------------------------------------------------------------

    def to_dict(self):
        """JSON-safe. Dates become ISO strings; links are bare titles."""
        out = {"kind": self.kind, "title": self.title, "body": self.body}
        for key, value in self.fields.items():
            if key in ("icon", "iconColor"):
                continue
            out[key] = value.isoformat() if isinstance(value, date) else value
        return out

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        kind = data.pop("kind", None)
        title = data.pop("title", None)
        body = data.pop("body", "")
        if kind is None:
            raise ValidationError("`kind` is required", "kind")
        if title is None:
            raise ValidationError("`title` is required", "title")
        return cls(kind=kind, title=title, fields=data, body=body)
