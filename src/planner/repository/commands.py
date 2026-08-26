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


@runtime_checkable
class Command(Protocol):
    """One reversible filesystem mutation."""

    def execute(self) -> None:
        """Apply. Must capture whatever `undo` will need, at this moment."""

    def undo(self) -> None:
        """Restore the state that existed immediately before `execute` ran."""

    def describe(self) -> str:
        """Short human-readable summary, used in error messages and logs."""


class _Base:
    """Shared bookkeeping: a command runs once, and undoes only what it did."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._executed = False
        self._existed: bool | None = None
        self._previous: bytes | None = None

    def _capture(self) -> None:
        """Snapshot the file as it is right now."""
        self._existed = self.path.is_file()
        self._previous = self.path.read_bytes() if self._existed else None

    def _guard_execute(self) -> None:
        if self._executed:
            raise CommandError(f"{self.describe()} has already run")

    def _restore(self) -> None:
        if self._existed:
            _atomic_write(self.path, self._previous)
        elif self.path.exists():
            self.path.unlink()

    def undo(self) -> None:
        if not self._executed:
            return                      # never ran; nothing to reverse
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

    def execute(self) -> None:
        self._guard_execute()
        self._capture()
        _atomic_write(self.path, self.content.encode("utf-8"))
        self._executed = True

    def describe(self) -> str:
        verb = "overwrite" if self.path.is_file() else "create"
        return f"{verb} {self.path.name}"


class DeleteFile(_Base):
    """Remove a file. Undo puts the bytes back."""

    def execute(self) -> None:
        self._guard_execute()
        if not self.path.is_file():
            raise CommandError(f"cannot delete missing file {self.path}")
        self._capture()
        self.path.unlink()
        self._executed = True

    def describe(self) -> str:
        return f"delete {self.path.name}"


class CreateDirectory:
    """Ensure a directory exists. Undo removes it only if this command created it, and
    only if it is still empty -- a directory someone else has since used is not ours to
    remove."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._created = False

    def execute(self) -> None:
        if self.path.is_dir():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        self._created = True

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
