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

from pathlib import Path
from typing import Iterable, Iterator

from ..domain import schema
from ..domain.errors import NoteNotFound, ValidationError
from ..domain.note import Note

#: Every folder that may hold notes. Journal/ is included because daily notes are
#: real notes even though nothing in the API creates them.
CONTENT_FOLDERS = ("Items", "Docs", "Meetings", "Reviews", "Journal")


class MarkdownNoteRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # --- locating -----------------------------------------------------------------

    def path_for(self, kind: str, title: str) -> Path:
        return self.root / schema.folder_for(kind) / f"{title}.md"

    def find(self, title: str) -> Path | None:
        """The file holding `title`, wherever it lives.

        Searched across folders rather than derived from kind, because the caller
        looking a note up usually does not know its kind yet -- and because titles are
        unique vault-wide, so at most one can match.
        """
        for folder in CONTENT_FOLDERS:
            candidate = self.root / folder / f"{title}.md"
            if candidate.is_file():
                return candidate
        return None

    def exists(self, title: str) -> bool:
        return self.find(title) is not None

    def _paths(self) -> Iterator[Path]:
        for folder in CONTENT_FOLDERS:
            directory = self.root / folder
            if directory.is_dir():
                yield from sorted(directory.glob("*.md"))

    # --- reading ------------------------------------------------------------------

    def get(self, title: str) -> Note:
        path = self.find(title)
        if path is None:
            raise NoteNotFound(f"no note titled {title!r}")
        return Note.from_markdown(path.read_text(encoding="utf-8"), title)

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
        for path in self._paths():
            try:
                yield path.stem, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

    # --- writing ------------------------------------------------------------------

    def save(self, note: Note) -> Note:
        existing = self.find(note.title)
        target = existing or self.path_for(note.kind, note.title)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(note.to_markdown(), encoding="utf-8")
        return note

    def delete(self, title: str) -> None:
        path = self.find(title)
        if path is None:
            raise NoteNotFound(f"no note titled {title!r}")
        path.unlink()
