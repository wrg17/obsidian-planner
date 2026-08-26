"""Wire contracts shared by every transport.

Sits above the domain and below the transports: it may import the domain, and both
`api` and `mcp` may import it, but it knows nothing about HTTP or MCP.
"""

from .note import (
    NoteIn, NotePatch, collapse_nullable, inline_refs, note_properties,
)

__all__ = [
    "NoteIn", "NotePatch", "note_properties", "inline_refs", "collapse_nullable",
]
