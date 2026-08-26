"""All-or-nothing filesystem transactions.

    with repo.unit_of_work():
        repo.save(a)
        repo.delete(b)          # if this raises, `a` is restored too

Commands are executed as they arrive and recorded; on failure they are undone in
reverse. That is compensation, not a real transaction -- there is no filesystem
equivalent of a write-ahead log we could rely on here, and the vault is being read by
another process throughout. What it does guarantee is that a failure part-way through a
multi-note operation does not leave the vault in a state the API would refuse to
create, which is the property that actually matters (S1).

Two limits, stated rather than hidden:

  NOT ISOLATED   Obsidian sees each write as it lands, including ones later rolled
                 back. Nothing short of a lock file would change that, and locking a
                 vault the user is editing is worse than the flicker.

                 A consequence worth stating: because writes are visible, they can be
                 edited before the rollback reaches them. Undo therefore checks that a
                 file still holds what we wrote before restoring it, and leaves it
                 alone otherwise -- the same rule crash recovery applies. A rollback
                 that destroyed someone's edit to tidy up after a transaction they
                 never knew about would be worse than an incomplete rollback.

  DURABLE, WITH A JOURNAL
                 Given one, intent is flushed to disk before each change lands, so a
                 crash mid-transaction is undone on the next startup -- see
                 journal.py, and repository.recover(). Without one, rollback is
                 in-process only and a crash leaves the operation half-done (though
                 never any individual file corrupt, because writes land by rename).
"""

from __future__ import annotations

import logging

from .commands import Command, CommandError, ConcurrentModification
from .journal import Journal  # noqa: F401 - type only

log = logging.getLogger("planner.repository")


class RollbackError(CommandError):
    """A command failed, and undoing the ones before it also failed.

    Raised only when the vault could not be returned to its prior state. It carries
    both faults because the original failure explains what was attempted and the
    rollback failure explains what is now inconsistent -- and someone is going to have
    to reconcile that by hand.
    """

    def __init__(self, cause: BaseException, failures: list[tuple[Command, BaseException]]):
        self.cause = cause
        self.failures = failures
        detail = "; ".join(f"{c.describe()}: {e}" for c, e in failures)
        super().__init__(
            f"{cause}; rollback then failed for {len(failures)} command(s): {detail}")


class UnitOfWork:
    def __init__(self, journal=None, summary: str = "", actor: str = "",
                 request_id: str = ""):
        self._done: list[Command] = []
        self._depth = 0
        self._failed = False
        self._journal = journal
        self.conflicts: list = []
        self._summary = summary
        self._actor = actor
        self._request_id = request_id

    # --- participation ------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._depth > 0

    def enter(self) -> "UnitOfWork":
        """Join, or open if this is the outermost caller.

        Nesting joins rather than starting a new transaction: `close()` calls
        `update()`, which saves, so a wrapped operation calling another wrapped
        operation is routine. An inner transaction committing independently would let
        half an outer operation survive its failure.
        """
        if self._depth == 0 and self._journal is not None:
            self._journal.begin(self._summary, self._actor, self._request_id)
        self._depth += 1
        return self

    def execute(self, command: Command) -> None:
        """Run a command, journalling intent first and recording it for rollback.

        The order is the whole point of splitting prepare from apply: read the world,
        write down what we are about to do to it, and only then do it. A crash between
        the flush and the change is recoverable; a crash before the flush leaves
        nothing to recover because nothing happened.

        Recorded for rollback before the outcome is known, because a command that
        fails partway may still have changed something. Undo is safe on a command that
        did nothing.
        """
        command.prepare()
        if self._journal is not None:
            entry = command.journal_entry(self._journal.root)
            if entry is not None:
                self._journal.record(entry)
        self._done.append(command)
        command.apply()

    # --- completion ---------------------------------------------------------------

    def __enter__(self) -> "UnitOfWork":
        return self.enter()

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        self._depth -= 1
        if exc is not None:
            self._failed = True
        failed = self._failed
        if self._depth > 0:
            return False                # inner scope: outcome is the outer one's call
        try:
            if self._failed:
                self.rollback(exc)
        finally:
            self._done.clear()
            self._failed = False
            if self._journal is not None:
                # Closed on both paths, but distinguishably. After a commit there is
                # nothing to recover; after an in-process rollback the vault is already
                # back where it started. Either way a journal left open would make the
                # next startup "recover" a transaction already dealt with -- but the
                # audit log wants to know which of the two happened, because "we tried
                # this and backed out" is worth keeping.
                if failed:
                    self._journal.rollback()
                else:
                    self._journal.commit()
        return False                    # never swallow the original exception

    def rollback(self, cause: BaseException | None = None) -> None:
        """Undo everything applied, most recent first.

        Reverse order matters: a later command may depend on what an earlier one did,
        and undoing forwards can leave the earlier undo with nothing to restore.

        Every command is attempted even after one fails, because stopping would strand
        the vault further from where it started than finishing does.
        """
        failures: list[tuple[Command, BaseException]] = []
        self.conflicts = []
        for command in reversed(self._done):
            try:
                command.undo()
            except ConcurrentModification as exc:
                # Not a failure: the command declined to act, which is the correct
                # outcome. Logged loudly and kept on the unit of work, but it does not
                # replace the original exception -- the caller needs to see why the
                # transaction failed, and a rollback that deliberately preserved
                # someone's edit is not the reason.
                self.conflicts.append(exc)
                log.warning("%s", exc)
            except Exception as exc:               # noqa: BLE001 - collected, not hidden
                failures.append((command, exc))
                log.error("rollback failed for %s: %s", command.describe(), exc)
        self._done.clear()
        if failures:
            raise RollbackError(cause or CommandError("rollback requested"), failures)
