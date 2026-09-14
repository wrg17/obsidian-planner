"""A NoteRepository backed by the vault's markdown files.

Persistence only: read a file, write a file, work out which folder it belongs in.
Defaults, relationship rules and anything that decides *whether* a write should happen
live in the service. The split matters here more than usual, because this store is not
exclusively ours -- Obsidian writes to the same files, by hand, at any moment.

Folder is derived from `kind` rather than taken from the caller. That mirrors the
Templater filing block, which moves a note by type when you create one in the app. Two
mechanisms disagreeing about where a doc belongs is how notes go missing.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ..domain import schema
from ..domain.errors import NoteNotFoundError, ValidationError
from ..domain.note import Note
from .audit import resolve_journal
from .commands import CreateDirectory, DeleteFile, WriteFile
from .journal import RecoveryReport
from .unit_of_work import UnitOfWork


def _names_in(directory: Path) -> set[str]:
    """The actual directory entries.

    Read rather than assumed, so a case-insensitive filesystem cannot pass off the
    caller's spelling as the stored one.
    """
    try:
        return {p.name for p in directory.iterdir()}
    except OSError:
        return set()


#: Every folder that may hold notes. Journal/ is included because daily notes are
#: real notes even though nothing in the API creates them.
CONTENT_FOLDERS = ("Items", "Docs", "Meetings", "Reviews", "Journal")


class MarkdownNoteRepository:
    """Notes stored as markdown files, in the folders Obsidian reads."""

    def __init__(self, root: str | Path, dsn: str | None = None):
        self.root = Path(root)
        # An ambient transaction rather than one passed to every call. The service
        # already reads as `self.repo.save(...)`; threading a uow argument through
        # every one of those would put transaction plumbing in the layer that is
        # supposed to be about rules. Safe because dependencies.get_repository builds
        # a fresh repository per request, so this is never shared across callers.
        # Postgres when reachable, the file journal otherwise. Degrading is
        # deliberate: a database being down is not a reason someone cannot write a
        # note in their own vault. The cost is a gap in the audit trail, and it is
        # logged as a gap rather than passed over in silence.
        self.journal = resolve_journal(self.root, dsn)
        self._uow = UnitOfWork(self.journal)

    def describe(
        self, summary: str = "", actor: str = "", request_id: str = ""
    ) -> None:
        """Attach audit metadata to the next transaction.

        Set before opening the unit of work, because the operation row is inserted
        when the transaction opens -- after that there is nothing left to label.
        """
        self._uow._summary = summary
        self._uow._actor = actor
        self._uow._request_id = request_id

    def has_pending_transaction(self) -> bool:
        """True when a journal is on disk, i.e.

        a transaction was interrupted and recovery has not run or could not finish.
        """
        return self.journal.has_pending()

    def recover(self) -> RecoveryReport:
        """Undo any transaction abandoned by a crash. Safe to call at any time.

        Call once at startup, before serving. It is a single stat when there is
        nothing to do, so it costs nothing on the normal path.

        Files changed since the crash by anything other than us are reported as
        conflicts and left exactly as they are -- see journal.py for why that is the
        only defensible choice when provenance is not observable.
        """
        return self.journal.recover()

    @contextmanager
    def unit_of_work(self):
        """Group writes so they succeed or fail together.

            with repo.unit_of_work():
                repo.save(a)
                repo.delete(b)      # if this raises, `a` is restored

        Nesting joins the outer transaction rather than opening a new one.
        """
        with self._uow as uow:
            yield uow

    def _run(self, *commands) -> None:
        """Apply commands, inside the active transaction if there is one.

        Outside a transaction each call is its own single-command unit, so an
        individual save is still atomic -- the temp-file-and-rename in WriteFile -- and
        the two paths cannot diverge in behaviour.
        """
        if self._uow.active:
            for command in commands:
                self._uow.execute(command)
            return
        with self._uow:
            for command in commands:
                self._uow.execute(command)

    # --- locating -----------------------------------------------------------------

    def path_for(self, kind: str, title: str) -> Path:
        """Where a note of this kind and title belongs. Touches no disk."""
        return self.root / schema.folder_for(kind) / f"{title}.md"

    def find(self, title: str) -> Path | None:
        """The file holding `title`, wherever it lives.

        Searched across folders rather than derived from kind, because the caller
        looking a note up usually does not know its kind yet -- and because titles are
        unique vault-wide, so at most one can match.
        """
        folded = title.casefold()
        for folder in CONTENT_FOLDERS:
            candidate = self.root / folder / f"{title}.md"
            if candidate.is_file():
                # The probe succeeded, but on a case-insensitive volume it may have
                # matched a differently-cased file -- and Path.stem echoes the string
                # we built, not the directory entry. Returning it would make
                # GET /notes/PICK%20A%20TYPE%20SCALE answer with title "PICK A TYPE
                # SCALE", a title no note actually has and one that would 409 as a
                # case clash if fed back. Canonicalise against the real entry.
                if candidate.name in _names_in(candidate.parent):
                    return candidate
                return next(
                    (
                        p
                        for p in sorted(candidate.parent.glob("*.md"))
                        if p.stem.casefold() == folded
                    ),
                    candidate,
                )
        # Nothing at the exact path. On a case-sensitive filesystem that is the only
        # probe that could have matched, so scan before giving up -- otherwise the same
        # request 200s on macOS and 404s on Linux, with the disk deciding rather than
        # the application.
        return self._scan_for(folded)

    def _scan_for(self, folded: str) -> Path | None:
        """Locate a note by casefolded title, ignoring the exact-path fast path.

        Split out because it is the branch that only runs on a case-sensitive
        filesystem: on macOS the probe above always matches first, so this would be
        dead code in the test run on a developer machine and live code in production
        on Linux. Testing it directly covers it on either.
        """
        for path in self._paths():
            if path.stem.casefold() == folded:
                return path
        return None

    def exists(self, title: str) -> bool:
        """Whether a note with this title is stored, wherever it lives."""
        return self.find(title) is not None

    def _paths(self) -> Iterator[Path]:
        for folder in CONTENT_FOLDERS:
            directory = self.root / folder
            if directory.is_dir():
                yield from sorted(
                    p for p in directory.glob("*.md") if not p.name.startswith(".")
                )

    # --- reading ------------------------------------------------------------------

    def titles(self) -> Iterable[str]:
        """Every note title, without parsing any of the files."""
        return [p.stem for p in self._paths()]

    def get(self, title: str) -> Note:
        """The note with this title. Raises NoteNotFoundError."""
        path = self.find(title)
        if path is None:
            raise NoteNotFoundError(f"no note titled {title!r}")
        # path.stem, not `title`: the note is identified by what is stored, not by how
        # the caller spelled it.
        return Note.from_markdown(path.read_text(encoding="utf-8"), path.stem)

    def iter_all(self) -> Iterable[Note]:
        """Readable notes only.

        A malformed note is an expected state, not an exception: this is a directory of
        hand-editable text and someone may be halfway through an edit. Listing must not
        fail because one file is mid-flight. `iter_raw` exposes the skipped ones.
        """
        for path in self._paths():
            try:
                yield Note.from_markdown(path.read_text(encoding="utf-8"), path.stem)
            except (ValidationError, UnicodeDecodeError):
                continue

    def iter_raw(self) -> Iterable[tuple[str, str]]:
        """(title, text) for every note, including ones that will not parse."""
        for path in self._paths():
            try:
                yield path.stem, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

    # --- writing ------------------------------------------------------------------

    def save(self, note: Note) -> Note:
        """Write the note, creating or overwriting."""
        existing = self.find(note.title)
        target = existing or self.path_for(note.kind, note.title)
        self._run(CreateDirectory(target.parent), WriteFile(target, note.to_markdown()))
        return note

    def delete(self, title: str) -> None:
        """Remove the note. Raises NoteNotFoundError."""
        path = self.find(title)
        if path is None:
            raise NoteNotFoundError(f"no note titled {title!r}")
        self._run(DeleteFile(path))
