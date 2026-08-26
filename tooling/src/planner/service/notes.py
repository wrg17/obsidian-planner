"""Business rules, independent of how a request arrived.

Everything here is transport-agnostic on purpose. The HTTP controllers and the MCP
tools both call this, and neither owns a rule the other lacks -- otherwise closing a
ticket over MCP would forget the `closed` date that the REST route remembers, and the
two surfaces would slowly become different products.
"""

from __future__ import annotations

import builtins
from datetime import date

from ..domain import schema
from ..domain.errors import (
    ChildrenExist, NoteExists, PlannerError, ValidationError,
)
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

    # `builtins.list[...]` throughout this class, not `list[...]`: the method below is
    # named `list`, which shadows the builtin in the class namespace. Runtime is
    # unaffected because annotations are strings here, but anything that resolves them
    # -- pdoc, and any typing tool -- fails with "'function' object is not
    # subscriptable". The same shape of bug once made a pydantic field named `date`
    # unresolvable against `date | None`.
    def list(self, kind=None, open_only=False, **where) -> builtins.list[Note]:
        if kind is not None and kind not in schema.KINDS:
            raise ValidationError(f"unknown kind {kind!r}", "kind")
        notes = [
            n for n in self.repo.iter_all()
            if (kind is None or n.kind == kind)
            and all(self._matches(n, k, v) for k, v in where.items())
        ]
        if open_only:
            notes = [n for n in notes if n.is_open]
        return sorted(notes, key=lambda n: n.title)

    @staticmethod
    def _matches(note: Note, field: str, wanted) -> bool:
        """Field equality, case-insensitive for links.

        Everything else about a title ignores case -- lookup (G2), uniqueness (C4) and
        the dangling-link check (P6) -- so a filter that did not would be the odd one
        out, and would produce the worst possible answer: 200 with an empty list,
        which reads as "no children" rather than "you spelled it differently".
        """
        actual = note.fields.get(field)
        if field in schema.LINK_FIELDS and isinstance(actual, str) \
                and isinstance(wanted, str):
            return actual.casefold() == wanted.casefold()
        return actual == wanted

    def children_of(self, title: str) -> builtins.list[Note]:
        """Direct children only.

        Bases cannot walk a parent chain -- no joins, no recursion -- so the app fakes
        depth with a denormalised `project` field. Here the walk is cheap, but the
        method stays deliberately one level deep so it matches what the epic and task
        notes show. `descendants_of` is the recursive one.
        """
        return self.list(parent=title)

    def descendants_of(self, title: str) -> builtins.list[Note]:
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

    def vault_status(self) -> dict:
        """Whether the vault is reachable and whether a transaction was interrupted.

        Here rather than in the controller because "is there a journal on disk" is a
        fact about the store, and a controller that knew the answer would be reaching
        past the service into the backend it is not supposed to know about.
        """
        root = self.repo.root
        return {
            "reachable": root.is_dir(),
            "interrupted_transaction": self.repo.has_pending_transaction(),
            "vault": str(root),
        }

    def problems(self) -> builtins.list[tuple[str, str]]:
        """Notes that will not parse or do not validate.

        The API's counterpart to the Triage base. Bases has no enum property type, so a
        misspelled status does not raise anywhere in Obsidian -- the ticket simply stops
        appearing on the board. This is how you find it without waiting to notice.
        """
        found = []
        readable = {}
        for title, text in self.repo.iter_raw():
            try:
                note = Note.from_markdown(text, title)
                note.validate(strict_fields=False)
                readable[title] = note
            except ValidationError as exc:
                found.append((title, str(exc)))

        # Referential integrity. The API refuses to write a dangling structural link,
        # but the vault is shared with Obsidian: a note deleted or renamed by hand
        # leaves one behind, and nothing in the app reports it. Bases cannot follow a
        # link to check it resolves, so this is the only place it can surface.
        known = {t.casefold() for t in self.repo.titles()}
        for title, note in readable.items():
            for field in ("parent", "project", "area"):
                target = note.fields.get(field)
                if target and target.casefold() not in known:
                    found.append((title, f"{field} {target!r} does not exist"))
            for field in ("blocked_by", "supersedes"):
                for target in note.fields.get(field) or []:
                    if target.casefold() not in known:
                        found.append((title, f"{field} entry {target!r} does not exist"))
        return sorted(found)

    # --- commands -----------------------------------------------------------------

    def create(self, note: Note | None = None, **kwargs) -> Note:
        note = note or Note.from_dict(kwargs)
        note.validate()
        clash = self._title_clash(note.title)
        if clash is not None:
            raise NoteExists(
                f"a note titled {clash!r} already exists"
                + ("" if clash == note.title else " (titles differ only by case)"))
        self._check_parent(note)
        self._check_references(note)
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
        self._check_references(note)
        return self.repo.save(note)

    def delete(self, title: str, cascade: bool = False) -> builtins.list[str]:
        """Delete a note, refusing to orphan its children.

        INVARIANT (closure): the API must never produce a state it would refuse to
        accept. `create` rejects a `parent` that does not exist, so a delete that left
        children pointing at a deleted note would manufacture exactly the state the
        write path forbids -- and nothing in Obsidian would show it, because Bases
        cannot follow a link to check it resolves.

        `cascade=True` removes the subtree instead, which is the other consistent
        answer. Returns every title removed, deepest first.
        """
        self.repo.get(title)                 # 404 before anything else
        children = self.children_of(title)
        if children and not cascade:
            raise ChildrenExist(
                f"{title!r} has {len(children)} child note(s): "
                f"{[c.title for c in children]}. Re-parent them, or pass cascade.")
        removed = []
        # One transaction for the whole subtree. Without it a failure part-way leaves
        # some children deleted and the rest pointing at a parent that is about to be,
        # or already is, gone -- the exact state D2 exists to prevent, arrived at by a
        # different road.
        with self.repo.unit_of_work():
            if cascade:
                for note in reversed(self.descendants_of(title)):
                    self.repo.delete(note.title)
                    removed.append(note.title)
            self.repo.delete(title)
            removed.append(title)
        return removed

    def create_many(self, notes) -> builtins.list[Note]:
        """Create several notes as one transaction.

        Order matters and is the caller's: a child listed before its parent fails the
        `parent` check, because validation runs against what is actually on disk at
        that moment rather than against a promise about the rest of the batch. Making
        it order-independent would mean deferring referential checks to commit time,
        which trades a clear error for a confusing one.
        """
        created = []
        with self.repo.unit_of_work():
            for index, note in enumerate(notes):
                try:
                    created.append(self.create(note))
                except PlannerError as exc:
                    # Name the offender. A 422 reporting only that "one of these
                    # twelve is wrong" leaves the caller to bisect the batch by hand.
                    raise type(exc)(
                        f"note {index} ({note.title!r}): {exc}",
                        *([exc.field] if isinstance(exc, ValidationError) else []),
                    ) from exc
        return created

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
        self._require_ticket(note, "closed")
        changes = {"status": status, "closed": on or date.today()}
        if schema.KINDS[note.kind].has_done:
            # `cancelled` work is closed but was never done, and the board's `lane`
            # formula reads the two separately.
            changes["done"] = status == "done"
        return self.update(title, **changes)

    def reopen(self, title: str, status: str = "todo") -> Note:
        note = self.repo.get(title)
        self._require_ticket(note, "reopened")
        spec = schema.KINDS[note.kind]
        if spec.statuses and status not in spec.statuses:
            raise ValidationError(
                f"status {status!r} not one of {list(spec.statuses)}", "status")
        changes = {"status": status, "closed": None}
        if spec.has_done:
            changes["done"] = False
        return self.update(title, **changes)

    # --- internals ----------------------------------------------------------------

    def _check_references(self, note: Note) -> None:
        """Reject a reference link pointing at nothing.

        Without this, POST would return 201 for a note that GET /problems flags in the
        same breath -- the API creating a state it immediately calls a problem.

        Note the asymmetry with `parent`, which is deliberate and documented as the one
        exception to closure (S1). A structural link is protected on *both* sides: you
        cannot create a dangling one, and you cannot delete a note that would leave
        one. A reference is protected only on write. Deleting a blocker is a legitimate
        thing to want, and the alternatives -- refusing to delete anything mentioned
        anywhere, or silently editing notes the caller never named -- are both worse
        than a dangling reference that /problems reports.
        """
        for field in ("blocked_by", "supersedes"):
            for target in note.fields.get(field) or []:
                if not self.repo.exists(target):
                    raise ValidationError(
                        f"{field} entry {target!r} does not exist", field)

    def _require_ticket(self, note: Note, verb: str) -> None:
        """Guard the ticket-only operations with a message about the actual problem.

        Without this the failure surfaces from deep inside validation as "'closed' is
        not a field of kind 'doc'", which is true but describes a symptom. A caller
        needs to be told that a doc is not a work item.
        """
        if note.kind not in schema.TICKET_KINDS:
            raise ValidationError(
                f"a {note.kind} cannot be {verb}; only "
                f"{list(schema.TICKET_KINDS)} track completion", "kind")

    def _title_clash(self, title: str) -> str | None:
        """An existing title equal to `title` ignoring case, if any.

        Case-insensitive on purpose. macOS is case-insensitive by default and Linux is
        not, so an exact-match check would let the same call create two notes on one
        machine and silently overwrite on another. Obsidian resolves `[[design
        system]]` without regard to case too, so two notes differing only that way
        could never be linked to unambiguously.
        """
        folded = title.casefold()
        for existing in self.repo.titles():
            if existing.casefold() == folded:
                return existing
        return None

    def _apply_defaults(self, note: Note) -> None:
        spec = schema.KINDS[note.kind]
        if not note.body.strip():
            # A note with no body opens in Obsidian as a blank page under a filename.
            # Giving it an H1 matching the title is what every template does, and doing
            # it here rather than in the serializer keeps the returned object equal to
            # what was written (S9).
            note.body = f"\n# {note.title}\n"
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
