"""Domain errors, kept separate so the API can map them to status codes without
importing anything that touches the filesystem."""


class PlannerError(Exception):
    """Base for everything this package raises deliberately."""


class ValidationError(PlannerError):
    """A note violates the schema: unknown kind, bad vocabulary value, stray field."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


class NoteNotFound(PlannerError):
    pass


class ChildrenExist(PlannerError):
    """A delete would orphan child notes.

    Separate from NoteExists because it maps to the same 409 but means the opposite
    thing: not "this already exists" but "something depends on this".
    """


class NoteExists(PlannerError):
    """Titles are unique vault-wide -- Obsidian links by name, so Items/ is flat and
    two notes may not share a title even in different folders."""
