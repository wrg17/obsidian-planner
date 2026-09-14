"""Wire contracts shared by every transport.

Sits above the domain and below the transports: it may import the domain, and both
`api` and `mcp` may import it, but it knows nothing about HTTP or MCP.
"""

from .note import (
    NoteIn,
    NotePatch,
    collapse_nullable,
    inline_refs,
    note_properties,
)
from .operations import OPERATIONS, Operation

__all__ = [
    "OPERATIONS",
    "NoteIn",
    "NotePatch",
    "Operation",
    "collapse_nullable",
    "inline_refs",
    "note_properties",
]
