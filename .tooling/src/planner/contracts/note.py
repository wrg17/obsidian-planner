"""The wire shape of a note, shared by every transport.

A layer of its own because both the HTTP API and the MCP server need the same answer to
"what may a caller send, and what is it called" -- and neither should have to import the
other to get it. A transport that depended on another transport would mean removing
REST breaks MCP.

WHY THIS MODEL IS BUILT RATHER THAN WRITTEN

The same eighteen fields were listed three times: in domain/fields.py, again as pydantic
fields in the API, and a third time as JSON Schema in the MCP tool definitions. They had
already drifted -- MCP was missing `attendees`, `closed`, `done` and `supersedes`, so a
model could not set a meeting's attendees or record one decision superseding another.
Nobody did anything wrong; three hand-maintained copies of one list is simply a thing
that decays.

So the model is assembled from FIELD_TYPES. The tables below hold only what the domain
genuinely does not know: how a property should be described to a caller, and where the
wire type is narrower than the storage type (`priority` is a number in the vault and
1..4 here). Everything else follows from the domain, and the MCP tool schemas are
derived from this model in turn -- so one definition reaches the vault, the OpenAPI
document and the MCP tools.

This is not the domain. The distinction earns its keep at the enum boundary: `kind` is
`KindEnum` rather than `str`, so the published schema declares the ten legal values. A
bare string validates identically at runtime -- the domain rejects "Epic" either way --
but it publishes nothing, and a generated client or a model reads the published schema
as the truth.
"""

from __future__ import annotations

import datetime

from pydantic import ConfigDict, Field, create_model

from ..domain import schema as S
from .operations import DEMO


# --- what the domain does not know -------------------------------------------------

#: Storage type -> wire type. The default mapping; PRECISE overrides it where the API
#: can say something sharper than "text".
BY_STORAGE_TYPE = {
    S.TEXT: str,
    S.DATE: datetime.date,
    S.NUMBER: int,
    S.CHECKBOX: bool,
    S.LINK: str,            # a plain title on the wire; [[wikilink]] only on disk
    S.LINK_LIST: list[str],
    S.TEXT_LIST: list[str],
}

#: Fields whose wire type is narrower than their storage type. Each is a real
#: constraint the vault cannot express: Obsidian has no enum property type, and
#: `priority` is just a number to it.
PRECISE = {
    "kind": S.KindEnum,
    "status": S.StatusEnum,
    "type": S.IssueTypeEnum,
    "recur": S.RecurEnum,
}

#: How each property is explained to a caller. Presentation, so it lives at the wire
#: boundary rather than in the domain -- but in exactly one place.
DESCRIPTIONS = {
    "kind": "Determines the folder and which fields are legal.",
    "status": "Legal values depend on kind: tickets use backlog..cancelled, containers "
              "use active/paused/done. See GET /schema.",
    "type": "Issue type; tickets only.",
    "priority": "1 is highest.",
    "done": "Additive with status == 'done': ticking either closes the ticket.",
    "parent": "Plain title, not [[wikilink]] syntax. Must exist, and must be a kind "
              "permitted to hold this one.",
    "project": "Denormalised onto every ticket. Bases cannot walk a parent chain, so "
               "without it 'everything in this project' is not expressible.",
    "area": "The area this belongs to. Plain title.",
    "due": "When it is due.",
    "scheduled": "When you intend to work on it.",
    "closed": "Set by close(); usually let the API manage it.",
    "last_done": "Routines: when it was last completed.",
    "recur": "Routines only.",
    "date": "Meetings and decisions.",
    "week": "Reviews, ISO week.",
    "blocked_by": "Plain titles of notes blocking this one.",
    "supersedes": "Decisions this one replaces.",
    "attendees": "Names; free text, not links.",
}

EXAMPLES = {
    "kind": ["task"],
    "parent": [DEMO["parent"]],
    "project": [DEMO["project"]],
    "week": ["2026-W35"],
}

#: The body Swagger pre-fills for POST /notes. A whole request rather than field-level
#: hints, so "Try it out" then "Execute" works with nothing typed -- against a vault
#: with the demo data loaded, which is what the demo is for.
#:
#: The title is one the demo deliberately does not create. An example that already
#: existed would 409 on the first click, which teaches the wrong lesson about the
#: endpoint.
CREATE_EXAMPLE = {
    "kind": "task",
    "title": DEMO["new_title"],
    "parent": DEMO["parent"],
    "project": DEMO["project"],
    "type": "chore",
    "priority": 2,
}

#: Properties the API owns and a caller may never set. `icon` and `iconColor` are
#: derived from kind -- accepting them would invite a client to send one that
#: disagrees -- and `created`/`demo` are stamped by the writer.
NOT_ON_THE_WIRE = {"icon", "iconColor", "created", "demo"}


def _field_definition(name: str):
    """(type, FieldInfo) for one property, as create_model wants it."""
    annotation = PRECISE.get(name) or BY_STORAGE_TYPE[S.FIELD_TYPES[name]]
    options = {"description": DESCRIPTIONS.get(name)}
    if name in EXAMPLES:
        options["examples"] = EXAMPLES[name]
    if name == "priority":
        # The one numeric range the vault cannot enforce, and the reason Triage has an
        # "Invalid values" view at all.
        options |= {"ge": S.PRIORITY_RANGE[0], "le": S.PRIORITY_RANGE[1]}
    return (annotation | None, Field(None, **options))


#: Every property except `kind`, which is required and therefore declared separately.
OPTIONAL_FIELDS = {
    name: _field_definition(name)
    for name in S.FIELD_TYPES
    if name not in NOT_ON_THE_WIRE and name != "kind"
}


NoteIn = create_model(
    "NoteIn",
    __config__=ConfigDict(extra="forbid", use_enum_values=True,
                          json_schema_extra={"examples": [CREATE_EXAMPLE]}),
    __doc__="A note to create. Which fields are legal depends on `kind`; sending one "
            "that does not belong is a 422, and GET /schema publishes the rules.",
    kind=(S.KindEnum, Field(..., description=DESCRIPTIONS["kind"],
                            examples=EXAMPLES["kind"])),
    title=(str, Field(..., min_length=1,
                      description="Unique vault-wide. Obsidian resolves links by name, "
                                  "so a doc and a task may not share one.",
                      examples=[DEMO["new_title"]])),
    body=(str, Field("", description="Markdown after the frontmatter.")),
    **OPTIONAL_FIELDS,
)


NotePatch = create_model(
    "NotePatch",
    __base__=NoteIn,
    __doc__="Partial update. Only fields present in the body are touched; a field sent "
            "as `null` is removed from the note. `kind` cannot be changed.",
    kind=(S.KindEnum | None, Field(None, description="Read-only; changing kind is a "
                                                     "422.")),
    title=(str | None, Field(None, description="Read-only; ignored if sent.")),
    body=(str | None, Field(None)),
)



# --- json schema --------------------------------------------------------------------

def inline_refs(schema: dict) -> dict:
    """Resolve $defs into the properties that reference them.

    Pydantic factors enums out into $defs and points at them with $ref, which is valid
    JSON Schema but leaves the reader to resolve it. FastAPI serves the whole document
    so a $ref is fine there; an MCP client gets one tool at a time, so the enum values
    have to be where a model will look for them.
    """
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs.get(node["$ref"].rsplit("/", 1)[-1], {})
                return {**resolve(target),
                        **{k: v for k, v in node.items() if k != "$ref"}}
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def collapse_nullable(spec: dict) -> dict:
    """Turn `anyOf: [X, null]` back into X.

    Every optional field is `X | None` in Python, which pydantic renders honestly as a
    union with null. For a tool schema that is noise: optionality is already expressed
    by absence from `required`, and a model reading `anyOf` has to look one level
    deeper to find the enum values it needs. FastAPI's own document keeps the precise
    form -- this is only for schemas handed to a model one tool at a time.
    """
    options = spec.get("anyOf")
    if not options:
        return spec
    concrete = [o for o in options if o.get("type") != "null"]
    if len(concrete) != 1:
        return spec
    return {**{k: v for k, v in spec.items() if k != "anyOf"}, **concrete[0]}


def note_properties(*, omit=()) -> dict:
    """The writable note fields as self-contained JSON Schema, flattened for tools."""
    schema = inline_refs(NoteIn.model_json_schema())
    return {name: collapse_nullable(spec)
            for name, spec in schema["properties"].items()
            if name not in omit}
