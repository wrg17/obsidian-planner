"""The persistence port.

A Protocol has no behaviour to test, so what is tested is that it means something:
the real adapter satisfies it, an incomplete one does not, and the service depends on
the port rather than the adapter.
"""

from contextlib import contextmanager

import pytest

from planner.domain.errors import NoteNotFound
from planner.repository.base import NoteRepository
from planner.repository.markdown import MarkdownNoteRepository


class InMemoryRepository:
    """A complete implementation, used to prove the port is honest."""

    def __init__(self):
        self.saved = {}


    def describe(self, summary="", actor="", request_id=""):
        pass

    def has_pending_transaction(self):
        return False

    @contextmanager
    def unit_of_work(self):
        """Snapshot the whole store; restore it if the block raises.

        Trivial for a dict, and that is the point: the port asks for all-or-nothing,
        not for compensating commands. A backend with real transactions would use
        them here."""
        saved = dict(self.saved)
        try:
            yield self
        except BaseException:
            self.saved = saved
            raise

    def get(self, title):
        if title not in self.saved:
            raise NoteNotFound(f"no note titled {title!r}")
        return self.saved[title]

    def exists(self, title):
        return title in self.saved

    def titles(self):
        return list(self.saved)

    def iter_all(self):
        return list(self.saved.values())

    def iter_raw(self):
        return [(t, n.to_markdown()) for t, n in self.saved.items()]

    def save(self, note):
        self.saved[note.title] = note
        return note

    def delete(self, title):
        if title not in self.saved:
            raise NoteNotFound(title)
        del self.saved[title]


class TestConformance:
    def test_markdown_adapter_satisfies_the_port(self, tmp_path):
        assert isinstance(MarkdownNoteRepository(tmp_path), NoteRepository)

    def test_in_memory_adapter_satisfies_the_port(self):
        assert isinstance(InMemoryRepository(), NoteRepository)

    def test_widening_the_port_breaks_stale_doubles(self):
        """The value of a runtime-checkable Protocol: when `titles` was added for the
        case-insensitive uniqueness check, every incomplete implementation failed
        immediately instead of at the first call."""
        class Stale(InMemoryRepository):
            titles = None

        assert not isinstance(Stale(), NoteRepository)

    def test_an_incomplete_adapter_does_not(self):
        class Missing:
            def get(self, title): ...
            def exists(self, title): ...

        assert not isinstance(Missing(), NoteRepository)

    @pytest.mark.parametrize("method", [
        "get", "exists", "titles", "iter_all", "iter_raw", "save", "delete",
        "unit_of_work", "has_pending_transaction", "describe"])
    def test_port_declares_the_whole_surface(self, method):
        assert hasattr(NoteRepository, method)


class TestServiceUsesThePort:
    def test_service_works_against_any_implementation(self):
        """The point of the port: swapping the store changes nothing above it."""
        from planner.service.notes import NoteService

        service = NoteService(InMemoryRepository())
        service.create(kind="task", title="In memory")
        assert service.get("In memory").fields["status"] == "todo"
        closed = service.close("In memory")
        assert closed.fields["done"] is True and "closed" in closed.fields

    def test_service_never_imports_the_markdown_adapter(self):
        import planner.service.notes as module

        source = open(module.__file__).read()
        assert "MarkdownNoteRepository" not in source
        assert "repository.base" in source
