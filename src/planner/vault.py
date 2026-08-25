"""CRUD over the vault's markdown files.

Folder is derived from `kind`, never chosen by the caller -- that is the same rule the
Templater filing block enforces when you create a note by hand, and having two
mechanisms disagree about where a doc lives is how notes go missing.

Titles are unique vault-wide. Items/ is deliberately flat because re-parenting should
be a property edit rather than a file move, and the cost of that choice is that
Obsidian resolves `[[Design system]]` by name alone, so two notes may not share one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import schema
from .errors import NoteExists, NoteNotFound, ValidationError
from .note import Note

CONTENT_FOLDERS = ("Items", "Docs", "Meetings", "Reviews", "Journal")


class Vault:
    def __init__(self, root):
        self.root = Path(root)

    # --- locating -----------------------------------------------------------------

    def _path_for(self, kind, title):
        return self.root / schema.folder_for(kind) / f"{title}.md"

    def find(self, title):
        """The file holding `title`, wherever it lives. None if absent."""
        for folder in CONTENT_FOLDERS:
            candidate = self.root / folder / f"{title}.md"
            if candidate.is_file():
                return candidate
        return None

    def exists(self, title):
        return self.find(title) is not None

    # --- reading ------------------------------------------------------------------

    def get(self, title):
        path = self.find(title)
        if path is None:
            raise NoteNotFound(f"no note titled {title!r}")
        return Note.from_markdown(path.read_text(encoding="utf-8"), title)

    def list(self, kind=None, **where):
        """Every readable note, optionally filtered by kind and field equality.

        Unreadable notes are skipped rather than raised on: a vault is a directory of
        hand-editable text, so a malformed note is an expected state. Use `problems()`
        to see them.
        """
        out = []
        for path in self._iter_paths():
            try:
                note = Note.from_markdown(path.read_text(encoding="utf-8"), path.stem)
            except ValidationError:
                continue
            if kind is not None and note.kind != kind:
                continue
            if all(note.fields.get(k) == v for k, v in where.items()):
                out.append(note)
        return sorted(out, key=lambda n: n.title)

    def problems(self):
        """(title, message) for every note that fails to parse or validate.

        This is the API-side equivalent of the Triage base: Bases has no enum property
        type, so a misspelled status hides work silently rather than erroring.
        """
        found = []
        for path in self._iter_paths():
            title = path.stem
            try:
                note = Note.from_markdown(path.read_text(encoding="utf-8"), title)
                note.validate(strict_fields=False)
            except ValidationError as exc:
                found.append((title, str(exc)))
        return sorted(found)

    def _iter_paths(self):
        for folder in CONTENT_FOLDERS:
            directory = self.root / folder
            if directory.is_dir():
                yield from sorted(directory.glob("*.md"))

    # --- writing ------------------------------------------------------------------

    def create(self, note=None, **kwargs):
        note = note or Note.from_dict(kwargs)
        note.validate()
        if self.exists(note.title):
            raise NoteExists(f"a note titled {note.title!r} already exists")
        self._check_parent(note)
        note.fields.setdefault("created", date.today())
        spec = schema.KINDS[note.kind]
        if spec.default_status and "status" not in note.fields:
            note.fields["status"] = spec.default_status
        if spec.has_done and "done" not in note.fields:
            note.fields["done"] = False
        path = self._path_for(note.kind, note.title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note.to_markdown(), encoding="utf-8")
        return note

    def update(self, title, **changes):
        note = self.get(title)
        for key, value in changes.items():
            if value is None:
                note.fields.pop(key, None)
            else:
                note.fields[key] = value
        note._coerce()
        note.validate()
        self._check_parent(note)
        self.find(title).write_text(note.to_markdown(), encoding="utf-8")
        return note

    def delete(self, title):
        path = self.find(title)
        if path is None:
            raise NoteNotFound(f"no note titled {title!r}")
        path.unlink()

    def close(self, title, status="done", on=None):
        """Close a ticket: set the status, tick `done`, and stamp `closed`.

        Bundled deliberately. Closing by hand means remembering three fields, and
        Triage carries a "Done but no closed date" view precisely because people
        forget the third.
        """
        if status not in schema.CLOSED_STATUS:
            raise ValidationError(f"{status!r} does not close a ticket", "status")
        note = self.get(title)
        changes = {"status": status, "closed": on or date.today()}
        if schema.KINDS[note.kind].has_done:
            changes["done"] = status == "done"
        return self.update(title, **changes)

    def _check_parent(self, note):
        parent = note.fields.get("parent")
        if not parent:
            return
        spec = schema.KINDS[note.kind]
        target = self.find(parent)
        if target is None:
            raise ValidationError(f"parent {parent!r} does not exist", "parent")
        if spec.parent_kinds:
            actual = self.get(parent).kind
            if actual not in spec.parent_kinds:
                raise ValidationError(
                    f"a {note.kind} may not hang off a {actual}; "
                    f"expected one of {list(spec.parent_kinds)}", "parent")
