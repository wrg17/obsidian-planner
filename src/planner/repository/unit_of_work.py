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

  NOT DURABLE ACROSS A CRASH
                 Rollback happens in this process. If it dies mid-transaction, earlier
                 commands stay applied. Individual writes are still atomic, so nothing
                 is corrupt -- but the operation may be half-done. A journal on disk
                 would close this; it is not worth the complexity until an operation
                 spans more files than a person can eyeball.
"""

from __future__ import annotations

import logging

from .commands import Command, CommandError

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
    def __init__(self):
        self._done: list[Command] = []
        self._depth = 0
        self._failed = False

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
        self._depth += 1
        return self

    def execute(self, command: Command) -> None:
        """Run a command and record it for possible rollback.

        Recorded before the outcome is known, because a command that fails partway may
        still have changed something -- WriteFile can have replaced the file and then
        failed to fsync. Undo is safe on a command that did nothing.
        """
        self._done.append(command)
        command.execute()

    # --- completion ---------------------------------------------------------------

    def __enter__(self) -> "UnitOfWork":
        return self.enter()

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        self._depth -= 1
        if exc is not None:
            self._failed = True
        if self._depth > 0:
            return False                # inner scope: outcome is the outer one's call
        if self._failed:
            self.rollback(exc)
        self._done.clear()
        self._failed = False
        return False                    # never swallow the original exception

    def rollback(self, cause: BaseException | None = None) -> None:
        """Undo everything applied, most recent first.

        Reverse order matters: a later command may depend on what an earlier one did,
        and undoing forwards can leave the earlier undo with nothing to restore.

        Every command is attempted even after one fails, because stopping would strand
        the vault further from where it started than finishing does.
        """
        failures: list[tuple[Command, BaseException]] = []
        for command in reversed(self._done):
            try:
                command.undo()
            except Exception as exc:               # noqa: BLE001 - collected, not hidden
                failures.append((command, exc))
                log.error("rollback failed for %s: %s", command.describe(), exc)
        self._done.clear()
        if failures:
            raise RollbackError(cause or CommandError("rollback requested"), failures)
