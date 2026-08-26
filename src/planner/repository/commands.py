"""Filesystem mutations as reversible commands.

Every write the repository performs is an object that knows how to do one thing and
how to undo it. That buys two properties the plain calls could not have:

    ATOMIC INDIVIDUALLY  A write goes to a temporary file in the same directory and is
                         moved into place with os.replace(), which is atomic on POSIX
                         within a filesystem. A crash cannot leave a half-written note
                         -- and this vault is read by another process that would parse
                         the truncated file quite happily.

    REVERSIBLE TOGETHER  A UnitOfWork records executed commands and, on failure, undoes
                         them in reverse. That is what makes a cascade delete of five
                         notes all-or-nothing rather than "however far it got".

The rule that makes undo trustworthy: **prior state is captured when the command runs,
not when it is constructed.** An earlier command in the same transaction may have
already changed the file, and a snapshot taken at construction time would restore the
wrong bytes -- silently, which is the worst way to be wrong about someone's notes.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable


class CommandError(RuntimeError):
    """A command failed to execute or to undo."""


class ConcurrentModification(CommandError):
    """Undo declined: the file no longer holds what this command wrote.

    Distinct from a failure, because nothing went wrong -- the command chose not to
    act. Something else changed the file between our write and our rollback, and on
    this vault the only candidate is a person editing their own notes in Obsidian.
    Restoring would silently destroy that edit to tidy up after a transaction they
    never knew about.
    """

    def __init__(self, path, describe):
        self.path = path
        super().__init__(
            f"{describe}: not undone -- {path.name} was modified by something else "
            f"since we wrote it, and its current content was left in place")


@runtime_checkable
class Command(Protocol):
    """One reversible filesystem mutation.

    Execution is split so a write-ahead journal can record intent between the two
    halves: `prepare` reads the world, the journal is flushed, then `apply` changes it.
    `execute` runs both for callers that need no journal.
    """

    def prepare(self) -> None:
        """Capture whatever `undo` will need. Changes nothing."""

    def apply(self) -> None:
        """Make the change. Only valid after `prepare`."""

    def journal_entry(self, root):
        """A record sufficient to undo this without the command object, or None if the
        command needs no journalling."""

    def execute(self) -> None:
        """Prepare and apply in one step."""

    def undo(self) -> None:
        """Restore the state that existed immediately before `execute` ran."""

    def describe(self) -> str:
        """Short human-readable summary, used in error messages and logs."""


class _Base:
    """Shared bookkeeping: a command runs once, and undoes only what it did."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._executed = False
        self._prepared = False
        self._existed: bool | None = None
        self._previous: bytes | None = None

    def _capture(self) -> None:
        """Snapshot the file as it is right now."""
        self._existed = self.path.is_file()
        self._previous = self.path.read_bytes() if self._existed else None

    def _guard_execute(self) -> None:
        if self._executed:
            raise CommandError(f"{self.describe()} has already run")

    def prepare(self) -> None:
        self._guard_execute()
        self._capture()
        self._prepared = True

    def execute(self) -> None:
        self.prepare()
        self.apply()

    def journal_entry(self, root: Path):
        """Prior and intended hashes, plus the bytes needed to put things back.

        Prior content rather than a reference to it: after a crash the command object
        is gone, so the journal has to be self-sufficient.
        """
        from .journal import Entry, digest
        return Entry(
            path=str(self.path.relative_to(root)),
            prior_hash=digest(self._previous),
            intended_hash=self._intended_hash(),
            prior_content=None if self._previous is None
            else self._previous.decode("utf-8", errors="surrogateescape"),
        )

    def _intended_hash(self) -> str | None:      # pragma: no cover - overridden
        raise NotImplementedError

    def _restore(self) -> None:
        if self._existed:
            _atomic_write(self.path, self._previous)
        elif self.path.exists():
            self.path.unlink()

    def _current_hash(self) -> str | None:
        from .journal import digest
        return digest(self.path.read_bytes() if self.path.is_file() else None)

    def undo(self) -> None:
        """Restore the prior state -- unless someone else has since changed the file.

        The same rule crash recovery applies, and for the same reason: a file that no
        longer holds what we wrote holds something we cannot account for, and on this
        vault that means a person edited it. Their edit is newer than the transaction
        we are abandoning and worth more than it.

        Without this check the in-process path was the *more* dangerous of the two --
        a crash is rare, but a rollback happens whenever a request fails, and Obsidian
        writes continuously.
        """
        if not self._executed:
            return                      # never ran; nothing to reverse
        if self._current_hash() != self._intended_hash():
            raise ConcurrentModification(self.path, self.describe())
        self._restore()
        self._executed = False

    def describe(self) -> str:          # pragma: no cover - overridden
        return f"{type(self).__name__}({self.path})"


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temporary file in the same directory, then rename over the target.

    Same directory matters: os.replace is only atomic within one filesystem, and a
    temp dir elsewhere would silently degrade to a copy. The fsync is what makes the
    content durable before the rename publishes it -- without it a crash can leave the
    name pointing at an empty file, which is worse than the old content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".planner-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class WriteFile(_Base):
    """Create or overwrite a file. Undo restores the previous content, or removes the
    file if it did not exist before."""

    def __init__(self, path: Path, content: str):
        super().__init__(path)
        self.content = content

    def apply(self) -> None:
        if not self._prepared:
            raise CommandError(f"{self.describe()} was not prepared")
        _atomic_write(self.path, self.content.encode("utf-8"))
        self._executed = True

    def _intended_hash(self) -> str | None:
        from .journal import digest
        return digest(self.content.encode("utf-8"))

    def describe(self) -> str:
        verb = "overwrite" if self.path.is_file() else "create"
        return f"{verb} {self.path.name}"


class DeleteFile(_Base):
    """Remove a file. Undo puts the bytes back."""

    def prepare(self) -> None:
        self._guard_execute()
        if not self.path.is_file():
            raise CommandError(f"cannot delete missing file {self.path}")
        self._capture()
        self._prepared = True

    def apply(self) -> None:
        if not self._prepared:
            raise CommandError(f"{self.describe()} was not prepared")
        self.path.unlink()
        self._executed = True

    def _intended_hash(self) -> str | None:
        return None                     # the file is meant to be gone

    def describe(self) -> str:
        return f"delete {self.path.name}"


class CreateDirectory:
    """Ensure a directory exists. Undo removes it only if this command created it, and
    only if it is still empty -- a directory someone else has since used is not ours to
    remove."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._created = False

    def prepare(self) -> None:
        pass                            # nothing to capture; undo is self-describing

    def apply(self) -> None:
        if self.path.is_dir():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        self._created = True

    def execute(self) -> None:
        self.prepare()
        self.apply()

    def journal_entry(self, root):
        """None: a directory holds no content to lose, and `undo` already refuses to
        remove one it did not create or one that is no longer empty."""
        return None

    def undo(self) -> None:
        if not self._created:
            return
        try:
            if not any(self.path.iterdir()):
                self.path.rmdir()
        except OSError:
            pass                        # someone else is using it; leave it alone
        self._created = False

    def describe(self) -> str:
        return f"mkdir {self.path.name}"
