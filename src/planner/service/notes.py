"""Business rules, independent of how a request arrived.

Everything here is transport-agnostic on purpose. The HTTP controllers and the MCP
tools both call this, and neither owns a rule the other lacks -- otherwise closing a
ticket over MCP would forget the `closed` date that the REST route remembers, and the
two surfaces would slowly become different products.
"""

from __future__ import annotations

from datetime import date

from ..domain import schema
from ..domain.errors import NoteExists, ValidationError
from ..domain.note import Note
from ..repository.base import NoteRepository


class NoteService:
    def __init__(self, repository: NoteRepository):
        self.repo = repository

    # --- queries ------------------------------------------------------------------

    def get(self, title: str) -> Note:
        return self.repo.get(title)

    def exists(self, title: str) -> bool:
        return self.repo.exists(title)

    def list(self, kind=None, open_only=False, **where) -> list[Note]:
        if kind is not None and kind not in schema.KINDS:
            raise ValidationError(f"unknown kind {kind!r}", "kind")
        notes = [
            n for n in self.repo.iter_all()
            if (kind is None or n.kind == kind)
            and all(n.fields.get(k) == v for k, v in where.items())
        ]
        if open_only:
            notes = [n for n in notes if n.is_open]
        return sorted(notes, key=lambda n: n.title)

    def children_of(self, title: str) -> list[Note]:
        """Direct children only.

        Bases cannot walk a parent chain -- no joins, no recursion -- so the app fakes
        depth with a denormalised `project` field. Here the walk is cheap, but the
        method stays deliberately one level deep so it matches what the epic and task
        notes show. `descendants_of` is the recursive one.
        """
        return self.list(parent=title)

    def descendants_of(self, title: str) -> list[Note]:
        found, frontier = [], [title]
        seen = {title}
        while frontier:
            current = frontier.pop()
            for child in self.list(parent=current):
                if child.title in seen:      # a hand-edited cycle must not hang us
                    continue
                seen.add(child.title)
                found.append(child)
                frontier.append(child.title)
        return sorted(found, key=lambda n: n.title)

    def problems(self) -> list[tuple[str, str]]:
        """Notes that will not parse or do not validate.

        The API's counterpart to the Triage base. Bases has no enum property type, so a
        misspelled status does not raise anywhere in Obsidian -- the ticket simply stops
        appearing on the board. This is how you find it without waiting to notice.
        """
        found = []
        for title, text in self.repo.iter_raw():
            try:
                Note.from_markdown(text, title).validate(strict_fields=False)
            except ValidationError as exc:
                found.append((title, str(exc)))
        return sorted(found)

    # --- commands -----------------------------------------------------------------

    def create(self, note: Note | None = None, **kwargs) -> Note:
        note = note or Note.from_dict(kwargs)
        note.validate()
        if self.repo.exists(note.title):
            raise NoteExists(f"a note titled {note.title!r} already exists")
        self._check_parent(note)
        self._apply_defaults(note)
        return self.repo.save(note)

    def update(self, title: str, **changes) -> Note:
        note = self.repo.get(title)
        if changes.get("kind") not in (None, note.kind):
            raise ValidationError(
                "kind cannot be changed; delete and recreate instead", "kind")
        changes.pop("kind", None)
        for key, value in changes.items():
            if value is None:
                note.fields.pop(key, None)
            else:
                note.fields[key] = value
        note._coerce()
        note.validate()
        self._check_parent(note)
        return self.repo.save(note)

    def delete(self, title: str) -> None:
        self.repo.delete(title)

    def close(self, title: str, status: str = "done", on: date | None = None) -> Note:
        """Close a ticket: status, the `done` checkbox and the `closed` date together.

        Bundled because they must move as one and routinely don't. Triage carries a
        "Done but no closed date" view for exactly the tickets where someone remembered
        two of the three.
        """
        if status not in schema.CLOSED_STATUS:
            raise ValidationError(
                f"{status!r} does not close a ticket; use one of "
                f"{list(schema.CLOSED_STATUS)}", "status")
        note = self.repo.get(title)
        changes = {"status": status, "closed": on or date.today()}
        if schema.KINDS[note.kind].has_done:
            # `cancelled` work is closed but was never done, and the board's `lane`
            # formula reads the two separately.
            changes["done"] = status == "done"
        return self.update(title, **changes)

    def reopen(self, title: str, status: str = "todo") -> Note:
        note = self.repo.get(title)
        spec = schema.KINDS[note.kind]
        if spec.statuses and status not in spec.statuses:
            raise ValidationError(
                f"status {status!r} not one of {list(spec.statuses)}", "status")
        changes = {"status": status, "closed": None}
        if spec.has_done:
            changes["done"] = False
        return self.update(title, **changes)

    # --- internals ----------------------------------------------------------------

    def _apply_defaults(self, note: Note) -> None:
        spec = schema.KINDS[note.kind]
        note.fields.setdefault("created", date.today())
        if spec.default_status:
            note.fields.setdefault("status", spec.default_status)
        if spec.has_done:
            note.fields.setdefault("done", False)

    def _check_parent(self, note: Note) -> None:
        parent = note.fields.get("parent")
        if not parent:
            return
        if parent == note.title:
            raise ValidationError("a note cannot be its own parent", "parent")
        if not self.repo.exists(parent):
            raise ValidationError(f"parent {parent!r} does not exist", "parent")
        allowed = schema.KINDS[note.kind].parent_kinds
        if allowed:
            actual = self.repo.get(parent).kind
            if actual not in allowed:
                raise ValidationError(
                    f"a {note.kind} may not hang off a {actual}; "
                    f"expected one of {list(allowed)}", "parent")
