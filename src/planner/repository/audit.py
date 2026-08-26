"""The journal port, and the fallback that keeps writes possible when Postgres is not.

Two backends implement the same small interface:

    FileJournal      a single JSON file beside the vault. No history, no server.
    PostgresJournal  an append-only audit log: every operation, its outcome, and
                     enough prior content to undo it.

`resolve_journal` picks one at startup and degrades to the file if the database is
unreachable. That choice is deliberate and worth stating: the planner is a vault on
someone's disk, and a database being down is not a reason they cannot write a note. The
cost is a gap in the audit trail, which is recorded as a gap rather than papered over.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from .journal import Entry, Journal as FileJournal, RecoveryReport

log = logging.getLogger("planner.repository")


@runtime_checkable
class JournalBackend(Protocol):
    """Whatever records intent before a change lands, and can undo it afterwards."""

    def begin(self, summary: str = "", actor: str = "", request_id: str = "") -> None:
        """Open an operation. Called once per transaction, before any entry."""

    def record(self, entry: Entry) -> None:
        """Durably record one file's before-and-after, before that change is applied."""

    def commit(self) -> None:
        """Mark the operation complete."""

    def rollback(self) -> None:
        """Mark the operation abandoned. The caller has already undone it in memory."""

    def recover(self) -> RecoveryReport:
        """Undo any operation an earlier process left in flight."""

    def has_pending(self) -> bool:
        ...


def resolve_journal(root, dsn: str | None, on_degrade=None) -> JournalBackend:
    """The Postgres journal if it is reachable, otherwise the file one.

    Connectivity is checked once, here, rather than on every write: a database that
    disappears mid-transaction is a failure the transaction should surface, not
    something to silently paper over halfway through.
    """
    if not dsn:
        return FileJournal(root)
    try:
        from .postgres_journal import PostgresJournal
        return PostgresJournal(root, dsn)
    except Exception as exc:                    # noqa: BLE001 - degrading is the point
        log.warning("postgres journal unavailable (%s); falling back to the file "
                    "journal. Crash recovery still works; this operation will not "
                    "appear in the audit log.", exc)
        if on_degrade is not None:
            on_degrade(exc)
        return FileJournal(root)
