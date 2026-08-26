"""MCP tools over the same service the HTTP API uses.

    python -m planner.mcp            # stdio transport

Tool schemas are generated from `domain.schema`, not written out again. That matters
more for MCP than for REST: a model reads the tool schema as the specification and will
not guess that `kind` means the ten lowercase words. Given `"type": "string"` it sends
"Epic" and gets an error it cannot see the shape of; given an enum it sends `epic`.

Every tool delegates to NoteService, so the rules are identical to the REST surface --
close still stamps `closed`, a parent is still checked for existence and kind. A second
front end that reimplemented any of that would drift within a month.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from ..contracts.note import note_properties
from ..domain import schema as S
from ..domain.errors import PlannerError
from ..domain.note import Note
from ..repository.markdown import MarkdownNoteRepository
from ..service.notes import NoteService


def build_service(root=None) -> NoteService:
    root = root or os.environ.get("PLANNER_VAULT", ".")
    return NoteService(MarkdownNoteRepository(Path(root)))


# --- tool schemas -------------------------------------------------------------------
#
# Derived from the API's NoteIn model rather than written out again. The same eighteen
# fields used to be listed here in JSON Schema, in api/schemas.py as pydantic fields,
# and in domain/fields.py -- and the three had drifted: this file was missing
# `attendees`, `closed`, `done` and `supersedes`, so a model could not set a meeting's
# attendees or record one decision superseding another.
#
# Deriving matters more for MCP than for REST. A model reads the tool schema as the
# specification; a field absent from it does not exist as far as the model is
# concerned, and no amount of server-side support makes up for that.
#
# The shared definition lives in `contracts`, not in the API: a transport importing
# another transport would mean removing REST breaks MCP.


def _kind_prop(description="The note type."):
    return {"type": "string", "enum": list(S.KIND_NAMES), "description": description}


#: Which HTTP operation each tool corresponds to. Written down because the two lists
#: were maintained separately and drifted -- eight tools against twelve routes, with no
#: record of which gaps were decided and which were merely never noticed. `reopen` was
#: the latter: a model could close a ticket and not reopen it.
#:
#: The descriptions themselves are deliberately NOT shared with the API. A model needs
#: to know when to reach for a tool and what to call first; a developer reading OpenAPI
#: needs to know what an endpoint does. Generating either from the other would make
#: both worse. It is the inventory that has to agree, not the prose.
COVERS = {
    "list_notes": ("GET", "/notes"),
    "get_note": ("GET", "/notes/{title}"),
    "create_note": ("POST", "/notes"),
    "update_note": ("PATCH", "/notes/{title}"),
    "delete_note": ("DELETE", "/notes/{title}"),
    "get_children": ("GET", "/notes/{title}/children"),
    "close_note": ("POST", "/notes/{title}/close"),
    "reopen_note": ("POST", "/notes/{title}/reopen"),
    "describe_schema": ("GET", "/schema"),
    "find_problems": ("GET", "/problems"),
}

#: Routes deliberately not exposed, and why. A route in neither this nor COVERS fails a
#: test, so the next omission has to be an argument rather than an oversight.
NOT_EXPOSED = {
    ("POST", "/notes/bulk"):
        "A model can call create_note repeatedly. Bulk adds only atomicity across the "
        "batch, and an array-of-objects argument is a poor fit for tool calling -- more "
        "ways to get it wrong than the guarantee is worth.",
    ("GET", "/health"):
        "Operational. A model has no use for liveness or the vault path, and a tool it "
        "will never sensibly call is noise in every prompt that lists the tools.",
}


TOOLS = [
    {
        "name": "list_notes",
        "description": (
            "List notes, optionally filtered. Returns title, kind and fields for each. "
            "Use `open` to exclude done and cancelled work."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": _kind_prop("Restrict to one type."),
                "project": {"type": "string", "description": "Plain title of a project."},
                "parent": {"type": "string", "description": "Direct children of this note."},
                "status": {"type": "string", "enum": list(S.ALL_STATUS)},
                "open": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_note",
        "description": "Fetch one note by its exact title.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "create_note",
        "description": (
            "Create a note. The folder is chosen from `kind`. Links are plain titles, "
            "not [[wikilink]] syntax. Which fields are legal depends on kind -- call "
            "describe_schema first if unsure."),
        "inputSchema": {
            "type": "object",
            "properties": note_properties(),
            "required": ["kind", "title"],
        },
    },
    {
        "name": "update_note",
        "description": "Change fields on an existing note. Null removes a field. "
                       "`kind` cannot be changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "changes": {"type": "object", "description":
                            "Field name to new value; null to remove."},
            },
            "required": ["title", "changes"],
        },
    },
    {
        "name": "close_note",
        "description": (
            "Close a ticket. Sets the status, ticks `done` and stamps `closed` in one "
            "step -- all three must move together."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": list(S.CLOSED_STATUS),
                           "default": "done"},
                "on": {"type": "string", "format": "date", "description": "Defaults to today."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "delete_note",
        "description": "Delete a note permanently.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "get_children",
        "description": (
            "The notes hanging off this one. Use `recursive` for the whole subtree. "
            "This is the query the Obsidian side cannot answer -- Bases has no joins "
            "and no recursion -- so it is worth reaching for rather than fetching notes "
            "one at a time and following `parent` yourself."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "recursive": {"type": "boolean", "default": False,
                              "description": "Whole subtree rather than one level."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "reopen_note",
        "description": (
            "Reopen a closed ticket: clears `closed`, unticks `done`, and puts it back "
            "in the status you give. The inverse of close_note, though not a full undo "
            "-- the original closing date is gone."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": list(S.TICKET_STATUS),
                           "default": "todo"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "describe_schema",
        "description": (
            "The note types, which fields each allows, and the vocabularies. Call this "
            "before creating notes if unsure which fields apply to a kind."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_problems",
        "description": (
            "Notes that fail to parse or validate -- misspelled statuses, out-of-range "
            "priorities, missing frontmatter. Obsidian reports none of these itself."),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# --- dispatch -----------------------------------------------------------------------

def call_tool(name: str, arguments: dict, service: NoteService | None = None) -> dict:
    """Run one tool. Transport-agnostic, so it is directly testable.

    Errors come back as a payload rather than an exception: a model needs to read what
    went wrong and correct itself, and a stack trace over stdio helps nobody.
    """
    service = service or build_service()
    try:
        return {"ok": True, "result": _dispatch(name, arguments or {}, service)}
    except PlannerError as exc:
        return {"ok": False, "error": str(exc),
                "field": getattr(exc, "field", None)}
    except Exception as exc:  # noqa: BLE001 -- surface, do not crash the server
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _dispatch(name, args, service):
    if name == "list_notes":
        notes = service.list(
            kind=args.get("kind"), open_only=args.get("open", False),
            **{k: v for k, v in
               {"project": args.get("project"), "parent": args.get("parent"),
                "status": args.get("status")}.items() if v is not None})
        return [n.to_dict() for n in notes]

    if name == "get_note":
        return service.get(args["title"]).to_dict()

    if name == "create_note":
        return service.create(Note.from_dict(
            {k: v for k, v in args.items() if v is not None})).to_dict()

    if name == "update_note":
        return service.update(args["title"], **args["changes"]).to_dict()

    if name == "get_children":
        service.get(args["title"])       # a missing note is an error, not an empty list
        found = (service.descendants_of(args["title"]) if args.get("recursive")
                 else service.children_of(args["title"]))
        return [n.to_dict() for n in found]

    if name == "reopen_note":
        return service.reopen(args["title"], status=args.get("status", "todo")).to_dict()

    if name == "close_note":
        on = date.fromisoformat(args["on"]) if args.get("on") else None
        return service.close(args["title"], status=args.get("status", "done"), on=on).to_dict()

    if name == "delete_note":
        service.delete(args["title"])
        return {"deleted": args["title"]}

    if name == "describe_schema":
        return {
            "kinds": [
                {"name": k.name, "folder": k.folder, "statuses": list(k.statuses),
                 "default_status": k.default_status,
                 "fields": list(S.allowed_fields(k.name)),
                 "parent_kinds": list(k.parent_kinds)}
                for k in S.KINDS.values()
            ],
            "vocabularies": {
                "issue_type": list(S.ISSUE_TYPE), "recur": list(S.RECUR),
                "ticket_status": list(S.TICKET_STATUS),
                "priority_range": list(S.PRIORITY_RANGE),
            },
        }

    if name == "find_problems":
        return [{"title": t, "message": m} for t, m in service.problems()]

    raise ValueError(f"unknown tool {name!r}")


# --- stdio server -------------------------------------------------------------------

async def serve():  # pragma: no cover - requires a live MCP client
    """Run over stdio. Imported lazily so the SDK stays an optional dependency."""
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    server = Server("planner")
    service = build_service()

    @server.list_tools()
    async def _list_tools():
        return [types.Tool(**t) for t in TOOLS]

    @server.call_tool()
    async def _call_tool(name, arguments):
        payload = call_tool(name, arguments, service)
        return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
