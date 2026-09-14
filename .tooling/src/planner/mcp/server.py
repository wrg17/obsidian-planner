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
from importlib.metadata import version
from pathlib import Path

from ..contracts.note import note_properties
from ..contracts.operations import OPERATIONS
from ..domain import schema as S
from ..domain.errors import PlannerError
from ..domain.note import Note
from ..repository.markdown import MarkdownNoteRepository
from ..service.notes import NoteService


def build_service(root=None) -> NoteService:
    """A service over the vault named by PLANNER_VAULT, or the argument."""
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
#: The descriptions are shared with the API, and this mapping is how. An earlier version
#: wrote them twice on the theory that a model and a developer want different things --
#: which was wrong. A developer meeting the repo for the first time does not know to
#: read /schema before creating a note any more than a model does; the only reader that
#: distinction fits is one who already knows the system. The result was that Swagger
#: carried the invariants without the operational advice, and the tools carried the
#: advice without the invariants, so each surface was missing what the other had.
COVERS = {
    "list_notes": ("GET", "/notes"),
    "get_note": ("GET", "/notes/{title}"),
    "create_note": ("POST", "/notes"),
    "update_note": ("PATCH", "/notes/{title}"),
    "get_children": ("GET", "/notes/{title}/children"),
    "close_note": ("POST", "/notes/{title}/close"),
    "reopen_note": ("POST", "/notes/{title}/reopen"),
    "describe_schema": ("GET", "/schema"),
    "find_problems": ("GET", "/problems"),
}

#: Routes deliberately not exposed, and why. A route in neither this nor COVERS fails a
#: test, so the next omission has to be an argument rather than an oversight.
NOT_EXPOSED = {
    (
        "POST",
        "/notes/bulk",
    ): "A model can call create_note repeatedly. Bulk adds only atomicity across the "
    "batch, and an array-of-objects argument is a poor fit for tool calling -- more "
    "ways to get it wrong than the guarantee is worth.",
    (
        "GET",
        "/health",
    ): "Operational. A model has no use for liveness or the vault path, and a tool it "
    "will never sensibly call is noise in every prompt that lists the tools.",
    (
        "DELETE",
        "/notes/{title}",
    ): "Withheld deliberately. Deleting a note destroys work with no undo -- the audit "
    "log records that it happened and keeps the prior content, but nothing puts the "
    "file back. For a model an absent tool does not exist, which is a far stronger "
    "guarantee than a refusal it might argue with or a confirmation it might assume. "
    "Closing or cancelling covers what an assistant legitimately needs: both leave the "
    "note in place and out of the way. Deletion stays a human action, over REST.",
}


def _description(name: str) -> str:
    """The documentation for a tool, taken from the operation it covers.

    Guidance first, then the invariants, exactly as OpenAPI shows them. It makes for a
    long tool description -- but a model that has not been told deleting a parent is
    refused will simply try it, and an error it could not anticipate costs more than the
    tokens did.

    Read from `contracts`, not from `api`. Both transports document the same operations,
    and neither should have to import the other to say so.
    """
    return OPERATIONS[COVERS[name]].description


TOOLS = [
    {
        "name": "list_notes",
        "description": _description("list_notes"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": _kind_prop("Restrict to one type."),
                "project": {
                    "type": "string",
                    "description": "Plain title of a project.",
                },
                "parent": {
                    "type": "string",
                    "description": "Direct children of this note.",
                },
                "status": {"type": "string", "enum": list(S.ALL_STATUS)},
                "open": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "get_note",
        "description": _description("get_note"),
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "create_note",
        "description": _description("create_note"),
        "inputSchema": {
            "type": "object",
            "properties": note_properties(),
            "required": ["kind", "title"],
        },
    },
    {
        "name": "update_note",
        "description": _description("update_note"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "changes": {
                    "type": "object",
                    "description": "Field name to new value; null to remove.",
                },
            },
            "required": ["title", "changes"],
        },
    },
    {
        "name": "close_note",
        "description": _description("close_note"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": list(S.CLOSED_STATUS),
                    "default": "done",
                },
                "on": {
                    "type": "string",
                    "format": "date",
                    "description": "Defaults to today.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "get_children",
        "description": _description("get_children"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "recursive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whole subtree rather than one level.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "reopen_note",
        "description": _description("reopen_note"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": list(S.TICKET_STATUS),
                    "default": "todo",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "describe_schema",
        "description": _description("describe_schema"),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_problems",
        "description": _description("find_problems"),
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
        return {"ok": False, "error": str(exc), "field": getattr(exc, "field", None)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _dispatch(name, args, service):
    if name == "list_notes":
        notes = service.find(
            kind=args.get("kind"),
            open_only=args.get("open", False),
            **{
                k: v
                for k, v in {
                    "project": args.get("project"),
                    "parent": args.get("parent"),
                    "status": args.get("status"),
                }.items()
                if v is not None
            },
        )
        return [n.to_dict() for n in notes]

    if name == "get_note":
        return service.get(args["title"]).to_dict()

    if name == "create_note":
        return service.create(
            Note.from_dict({k: v for k, v in args.items() if v is not None})
        ).to_dict()

    if name == "update_note":
        return service.update(args["title"], **args["changes"]).to_dict()

    if name == "get_children":
        service.get(args["title"])  # a missing note is an error, not an empty list
        found = (
            service.descendants_of(args["title"])
            if args.get("recursive")
            else service.children_of(args["title"])
        )
        return [n.to_dict() for n in found]

    if name == "reopen_note":
        return service.reopen(
            args["title"], status=args.get("status", "todo")
        ).to_dict()

    if name == "close_note":
        on = date.fromisoformat(args["on"]) if args.get("on") else None
        return service.close(
            args["title"], status=args.get("status", "done"), on=on
        ).to_dict()

    if name == "describe_schema":
        return {
            "kinds": [
                {
                    "name": k.name,
                    "folder": k.folder,
                    "statuses": list(k.statuses),
                    "default_status": k.default_status,
                    "fields": list(S.allowed_fields(k.name)),
                    "parent_kinds": list(k.parent_kinds),
                }
                for k in S.KINDS.values()
            ],
            "vocabularies": {
                "issue_type": list(S.ISSUE_TYPE),
                "recur": list(S.RECUR),
                "ticket_status": list(S.TICKET_STATUS),
                "priority_range": list(S.PRIORITY_RANGE),
            },
        }

    if name == "find_problems":
        return [{"title": t, "message": m} for t, m in service.problems()]

    raise ValueError(f"unknown tool {name!r}")


# --- stdio server -------------------------------------------------------------------


async def serve():  # pragma: no cover - measured out of process; see the test below
    """Run over stdio. Imported lazily so the SDK stays an optional dependency.

    Handlers are passed to the constructor rather than registered with `@server.*`
    decorators. The decorators are the 1.x SDK's API and were removed in 2.0 -- against
    which this raised `AttributeError` on the first line of the body, so the server
    exited before a client could complete the handshake and every client reported it as
    "connection closed" rather than as a version mismatch. `mcp>=2` in pyproject is half
    the fix; this is the other half.

    Everything above this line is transport-agnostic and directly tested. This function
    is the part that can only be exercised by starting the process, which is what
    `tests/mcp/serve.integration.test.py` does -- nothing did before, which is why the
    break shipped. It stays `no cover` because that test runs the server as a
    subprocess, where this process's coverage cannot see it.
    """
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    from mcp import types

    service = build_service()

    async def list_tools(_context, _params):
        return types.ListToolsResult(tools=[types.Tool(**t) for t in TOOLS])

    async def invoke(_context, params):
        payload = call_tool(params.name, params.arguments, service)
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=json.dumps(payload, indent=2))
            ],
            # A failed tool call is a result, not a protocol error: the payload says
            # what went wrong and the model reads it and corrects itself. `is_error`
            # is how a client knows to show it as a failure rather than as an answer.
            is_error=not payload["ok"],
        )

    # Read from the installed metadata rather than written here: the number lives in
    # pyproject, and a copy of it in the source is a copy that goes stale.
    server = Server(
        "planner",
        version=version("planner"),
        on_list_tools=list_tools,
        on_call_tool=invoke,
    )

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
