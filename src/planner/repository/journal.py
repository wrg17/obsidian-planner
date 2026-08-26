"""A write-ahead journal, so a crash mid-transaction can be undone on restart.

The unit of work rolls back in memory, which is useless if the process dies. This
records intent to disk *before* each change lands, so recovery has something to work
from.

===============================================================================
WHO CHANGED THE FILE?
===============================================================================

The tempting model is "changes made by the code are authoritative, changes made in
Obsidian are authoritative for the user". The obstacle is that provenance is not
observable: the filesystem stores bytes and an mtime, not an author. After a crash
there is no field to consult.

What *is* observable is divergence. The journal records, for every file it is about to
touch, the hash of what was there and the hash of what we intend to put there. On
recovery those two hashes turn an unanswerable question into a decidable one:

    file matches PRIOR hash        our write never landed        nothing to do
    file matches INTENDED hash     our write landed, txn broke   restore prior
    file is absent, prior existed  our delete landed             restore prior
    file matches NEITHER           someone edited it after the   LEAVE IT ALONE,
                                   crash -- only Obsidian could  report a conflict

That last row is the rule the user's intuition was reaching for, made decidable. We
never overwrite a change we cannot account for, because the only thing that could have
produced it is a human editing their own notes -- and their edit is newer than our
abandoned transaction and worth more than it.

The cost of being sure is one sha256 per touched file (~21us) and one fsync per
command (~1ms). Both are paid only on writes.

===============================================================================
WHAT THIS STILL DOES NOT GIVE YOU
===============================================================================

NO ROLL-FORWARD
    Recovery restores the *prior* state; it never re-applies a half-finished
    transaction. Rolling forward would mean re-deciding validation questions against a
    vault that has moved on since, which is how you resurrect a note the user deleted
    in the meantime.

NOT A LOCK
    Obsidian can write during a transaction. If it does, recovery sees the conflict row
    above and steps back rather than fighting.

THE COMMIT-RECORD WINDOW
    Clearing the journal cannot be atomic with the last file write -- they are separate
    stores, and no filesystem offers a way to join them. So there is a window:

        apply the last file  ──┬── a crash here leaves the journal present
                               │   and the file matching `intended_hash`
        clear the journal    ──┘

    Recovery cannot distinguish "committed, but we died before clearing the journal"
    from "applied, but the transaction never completed". Both look identical: journal
    present, file holds what we intended.

    We restore the prior state, which means a transaction that actually succeeded can
    be undone. That is the deliberate choice, and it is the conservative one: the
    result is a vault in a state the API would accept, and a caller who either saw an
    error or can safely retry. Assuming "committed" instead would risk presenting a
    half-applied transaction as though it were whole -- inconsistent data rather than
    lost work, which is the worse of the two.

    Closing this properly requires two-phase commit, and the filesystem is not a
    participant that can prepare. It cannot be fixed here; moving the journal into
    Postgres does not fix it either, because the window is between the file write and
    the commit record wherever that record lives.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_NAME = ".planner-journal.json"


def digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


@dataclass
class Entry:
    """One file's before-and-after, enough to undo it without the command object."""

    path: str
    prior_hash: str | None          # None means "did not exist"
    intended_hash: str | None       # None means "will be deleted"
    prior_content: str | None       # kept so recovery needs nothing but this file

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "prior_hash": self.prior_hash,
            "intended_hash": self.intended_hash,
            "prior_content": self.prior_content,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Entry":
        return cls(data["path"], data["prior_hash"], data["intended_hash"],
                   data["prior_content"])


@dataclass
class Conflict:
    """A file recovery declined to touch, because it holds content we never wrote."""

    path: str
    reason: str = "modified outside this process after the crash"


@dataclass
class RecoveryReport:
    restored: list[str] = field(default_factory=list)
    untouched: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.conflicts

    def __bool__(self) -> bool:
        """Truthy when recovery actually had something to do."""
        return bool(self.restored or self.untouched or self.conflicts)


class Journal:
    """The on-disk record of a transaction in flight.

    One journal per vault, not one per transaction: two concurrent writers on a
    personal planner is not a case worth the complexity, and a single well-known path
    is what makes recovery on startup a single stat.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / JOURNAL_NAME
        self._entries: list[Entry] = []

    # --- recording ----------------------------------------------------------------

    def begin(self, summary: str = "", actor: str = "", request_id: str = "") -> None:
        """No-op: a file journal records only what is in flight, so there is nothing to
        open. The arguments exist so the two backends share one interface -- the
        Postgres one keeps them as audit metadata."""

    def commit(self) -> None:
        """Nothing to keep. See the module docstring: a finished transaction leaves no
        trace here, which is precisely the gap the Postgres backend fills."""
        self.clear()

    def rollback(self) -> None:
        self.clear()

    def has_pending(self) -> bool:
        return self.path.is_file()

    def record(self, entry: Entry) -> None:
        """Append an entry and flush it to disk before the change is applied.

        Written per command rather than per transaction because the unit of work
        streams -- callers execute commands as they go and can read their own writes,
        so the full set is not known up front. One fsync per command is the price of
        keeping that.
        """
        self._entries.append(entry)
        self._flush()

    def _flush(self) -> None:
        payload = {
            "started": datetime.now(timezone.utc).isoformat(),
            "entries": [e.to_json() for e in self._entries],
        }
        handle, temporary = tempfile.mkstemp(dir=self.root, prefix=".planner-j-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def clear(self) -> None:
        """Discard the journal. Called once a transaction has fully landed or has been
        rolled back in memory -- in either case there is nothing left to recover."""
        self._entries.clear()
        self.path.unlink(missing_ok=True)

    # --- recovery -----------------------------------------------------------------

    def pending(self) -> list[Entry]:
        """Entries from a transaction that never finished. Empty if none."""
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Entry.from_json(e) for e in data["entries"]]
        except (ValueError, KeyError, OSError):
            # A journal that will not parse is itself evidence of a crash -- possibly
            # during its own write. There is nothing safe to infer from it, and acting
            # on a guess is worse than leaving the vault as the user finds it.
            return []

    def recover(self) -> RecoveryReport:
        """Undo an abandoned transaction, refusing to clobber unexplained changes."""
        report = RecoveryReport()
        entries = self.pending()
        if not entries:
            return report

        # Reverse order, for the same reason the in-memory rollback uses it: a later
        # command may depend on what an earlier one did.
        for entry in reversed(entries):
            target = self.root / entry.path
            current = target.read_bytes() if target.is_file() else None
            current_hash = digest(current)

            if current_hash == entry.prior_hash:
                report.untouched.append(entry.path)      # our write never landed
            elif current_hash == entry.intended_hash:
                self._restore(target, entry)             # ours; undo it
                report.restored.append(entry.path)
            else:
                report.conflicts.append(Conflict(entry.path))

        self.clear()
        return report

    @staticmethod
    def _restore(target: Path, entry: Entry) -> None:
        if entry.prior_content is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".planner-r-")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(entry.prior_content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
