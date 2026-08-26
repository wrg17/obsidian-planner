"""MCP transport over the same NoteService the HTTP API uses."""

from .server import TOOLS, build_service, call_tool

__all__ = ["TOOLS", "call_tool", "build_service"]
