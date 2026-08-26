"""The persistence port.

Defined as a Protocol rather than an ABC so a test double is just a class with the
right methods -- no inheritance, no registration. The service depends on this, never
on the markdown implementation, which is what keeps "where notes live" a swappable
decision. Today it is a folder of files that Obsidian also edits; a future
implementation could be SQLite or an object store without the service noticing.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from ..domain.note import Note


@runtime_checkable
class NoteRepository(Protocol):
    """Storage for notes, keyed by title.

    Implementations do no validation beyond what is needed to read a note back. Rules
    about which fields a kind may carry belong to the domain, and rules about defaults
    and relationships belong to the service.
    """

    def get(self, title: str) -> Note:
        """The note titled `title`. Raises NoteNotFound."""

    def exists(self, title: str) -> bool:
        ...

    def titles(self) -> Iterable[str]:
        """Every note title, without parsing the files.

        Cheap enough to call on every create, which is what the case-insensitive
        uniqueness check needs.
        """

    def iter_all(self) -> Iterable[Note]:
        """Every note that can be read. Unreadable ones are skipped."""

    def iter_raw(self) -> Iterable[tuple[str, str]]:
        """(title, text) for every note, readable or not, so callers can report on
        the ones that fail to parse."""

    def save(self, note: Note) -> Note:
        """Create or overwrite. Placement is the implementation's business."""

    def delete(self, title: str) -> None:
        """Raises NoteNotFound."""

    def describe(self, summary: str = "", actor: str = "", request_id: str = ""):
        """Label the next transaction for the audit log. No-op for backends without
        one; the file journal keeps nothing after a transaction finishes."""

    def has_pending_transaction(self) -> bool:
        """True when an interrupted transaction is awaiting recovery.

        Part of the port because callers need to surface the condition without knowing
        how the backend records it -- a journal file here, an uncommitted transaction
        elsewhere.
        """

    def unit_of_work(self):
        """A context manager grouping writes so they succeed or fail together.

        Part of the port because the service needs multi-note operations to be
        all-or-nothing without knowing what the store is. A backend with real
        transactions can implement this with them; the markdown adapter compensates
        with reversible commands. An in-memory double can snapshot a dict.
        """
