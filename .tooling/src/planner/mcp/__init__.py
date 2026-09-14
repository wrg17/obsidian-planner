"""MCP transport over the same NoteService the HTTP API uses."""

from .server import COVERS, NOT_EXPOSED, TOOLS, build_service, call_tool

__all__ = ["COVERS", "NOT_EXPOSED", "TOOLS", "build_service", "call_tool"]
