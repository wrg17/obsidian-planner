"""Domain errors.

Kept in their own module so the API can map them to status codes without importing
anything that touches the filesystem.
"""


class PlannerError(Exception):
    """Base for everything this package raises deliberately."""


class ValidationError(PlannerError):
    """A note violates the schema: unknown kind, bad vocabulary value, stray field."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


class NoteNotFoundError(PlannerError):
    """No note by that title exists."""

    pass


class ChildrenExistError(PlannerError):
    """A delete would orphan child notes.

    Separate from NoteExistsError because it maps to the same 409 but means the opposite
    thing: not "this already exists" but "something depends on this".
    """


class NoteExistsError(PlannerError):
    """A note with that title already exists.

    Titles are unique vault-wide: Obsidian links by name, so Items/ is flat and two
    notes may not share a title even in different folders.
    """
