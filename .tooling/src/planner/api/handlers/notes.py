"""Note CRUD, closing, and hierarchy.

Controllers stay thin: translate, delegate, translate back. No business rules here --
domain errors propagate to the handlers installed in middleware.py, which is why there
is not a try/except in sight.

Each route documents the invariants it upholds. They are numbered per endpoint and
reference the system invariants (S1-S9) in api/app.py, so a local rule can be traced
to the principle it comes from.
"""

from __future__ import annotations

import datetime

from fastapi import Depends, Query, Response

from ...domain import schema as S
from ...domain.note import Note
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import NoteIn, NoteOut, NotePatch


def list_notes(
    kind: S.KindEnum | None = Query(None, description="Restrict to one kind."),
    project: str | None = Query(None, description="Plain title."),
    parent: str | None = Query(None, description="Direct children of this note."),
    status: S.StatusEnum | None = None,
    open_only: bool = Query(False, alias="open", description="Exclude closed work."),
    service: NoteService = Depends(get_service),
):
    """List notes, optionally filtered.

    INVARIANTS
      L1. Pure. Listing never writes, and never touches mtime -- Triage's "stale" view
          reads mtime, so a read that bumped it would corrupt that signal. (S2)
      L2. Total. An unreadable note is skipped, never raised. The vault is hand-edited
          text and a file may be mid-save; one bad note must not 500 a listing. Use
          GET /problems to see what was skipped. (S8)
      L3. Absence is [], not 404. A filter matching nothing is a successful query with
          no results; only a missing *named* resource is a 404.
      L4. Filters conjoin. Every supplied filter narrows; none widens. Adding one can
          only ever shrink the result set.
      L5. Deterministic order. Sorted by title, so pagination added later cannot skip
          or duplicate, and diffs between two calls are meaningful.
      L6. `open=true` is exactly `not is_open`, the same predicate the board's `open`
          formula uses -- the done checkbox and a closing status are additive, so
          either one excludes a note.
      L7. Every returned note validates. Anything that would appear in /problems is
          not here. The two endpoints partition the vault.
    """
    where = {k: v for k, v in
             {"project": project, "parent": parent, "status": status}.items()
             if v is not None}
    return [n.to_dict() for n in service.list(kind=kind, open_only=open_only, **where)]


def create_note(payload: NoteIn, service: NoteService = Depends(get_service)):
    """Create a note.

    INVARIANTS
      C1. Not idempotent, and honest about it. A repeated POST is a 409, never a
          silent overwrite -- losing a note to a retried request is unacceptable when
          the store is someone's planner. (S6)
      C2. Atomic. A rejected create writes nothing; validation completes before the
          first byte. (S3)
      C3. Placement is derived, never supplied. `kind` decides the folder, matching
          the Templater filing block that moves notes by type in the app. Two
          mechanisms disagreeing about where a doc lives is how notes go missing. (S5)
      C4. Titles are unique case-insensitively. macOS is case-insensitive and Linux is
          not, so an exact check would create two notes on one machine and overwrite on
          the other. Obsidian resolves [[design system]] without regard to case too, so
          two notes differing only that way could never be linked unambiguously.
      C5. Structural links must resolve. `parent` must exist and be a kind permitted to
          hold this one. Combined with D2 below, the API cannot produce a dangling
          parent by any route. (S1)
      C6. Defaults are applied, never invented later. `created`, `status` and `done`
          are set now, so a note is never in a state the schema forbids.
      C7. The response equals the subsequent GET. (S9)
      C8. What is created is clean. A note made here never appears in /problems. (S8)
    """
    return service.create(Note.from_dict(payload.model_dump(exclude_none=True))).to_dict()


def create_many(payload: list[NoteIn], service: NoteService = Depends(get_service)):
    """Create a batch. Either all of them exist afterwards, or none do.

    INVARIANTS
      B1. All-or-nothing. One rejected note undoes the whole batch, restoring any file
          already written. This is the operation the unit of work exists for -- a
          partial batch is exactly the half-built hierarchy the closure invariant
          forbids. (S1, S3)
      B2. Every per-note rule from POST still applies. This is a transaction around
          `create`, not a second, laxer path into the vault.
      B3. Order is significant and is the caller's to choose. A child listed before
          its parent fails, because each note is validated against what is on disk at
          that moment rather than against a promise about the rest of the batch.
          Deferring referential checks to commit time would trade a precise error for
          a confusing one.
      B4. The error names the note that failed, not just the batch -- a 422 saying
          only "one of these twelve is wrong" is close to useless.
      B5. Non-atomic outside this process. A crash mid-batch leaves earlier notes
          written; individual files are still whole, because every write lands by
          atomic rename. (Documented limit of the unit of work.)
    """
    notes = [Note.from_dict(item.model_dump(exclude_none=True)) for item in payload]
    return [n.to_dict() for n in service.create_many(notes)]


def get_note(title: str, service: NoteService = Depends(get_service)):
    """Fetch one note by title.

    INVARIANTS
      G1. Pure. (S2)
      G2. Lookup is case-insensitive, matching creation (C4). Without this the same
          request would 200 on macOS and 404 on Linux, since the filesystem rather than
          the application would be deciding.
      G3. Missing is 404 with the standard error shape. (S4)
      G4. Storage detail stays hidden: links come back as plain titles, and `icon`/
          `iconColor` are omitted because they are derived from `kind`. (S5)
      G5. Round-trips. Feeding this response back to POST in a fresh vault reproduces
          the note. (S9)
    """
    return service.get(title).to_dict()


def update_note(title: str, payload: NotePatch,
                service: NoteService = Depends(get_service)):
    """Partially update a note.

    INVARIANTS
      U1. Idempotent. Applying the same patch twice leaves the same state. (S6)
      U2. Minimal. Only fields present in the body are touched; everything else,
          including the markdown body, is preserved byte for byte. A field sent as
          `null` is removed -- absent and null mean different things here, which is
          why the DTO distinguishes unset from None.
      U3. Atomic. A rejected patch leaves the note exactly as it was. (S3)
      U4. `kind` is immutable. Changing it would move the folder and invalidate the
          field set; delete and recreate is the honest operation, and saying so beats
          half-performing it.
      U5. `title` is immutable here. It is the identity and the link target; renaming
          would break every [[wikilink]] pointing at it, which this API cannot fix
          because links live in note bodies it does not parse.
      U6. Closure. A patch cannot introduce a dangling `parent`, a foreign vocabulary
          value, or a field the kind does not own. The result satisfies exactly what
          POST would have required. (S1)
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("title", None)
    return service.update(title, **changes).to_dict()


def delete_note(
    title: str,
    cascade: bool = Query(False, description=
                          "Also delete every descendant. Without it, a note with "
                          "children is refused."),
    service: NoteService = Depends(get_service),
):
    """Delete a note.

    INVARIANTS
      D1. Not idempotent, deliberately. The second call is a 404, the same answer GET
          and PATCH give for a missing note, so "does this exist?" has one answer
          across the API rather than one special case. (S6)
      D2. Never orphans. Deleting a note with children is a 409 unless `cascade` is
          set. Creation refuses a `parent` that does not exist, so a delete that left
          children behind would manufacture precisely the state the write path forbids
          -- and nothing in Obsidian would show it, because Bases cannot follow a link
          to check that it resolves. (S1)
      D3. Cascade is a subtree, not a sweep. It removes exactly the descendants of this
          note, deepest first, so no intermediate state has a child pointing at an
          already-deleted parent.
      D4. Cascade terminates. A parent cycle introduced by hand is visited once.
      D5. No body. 204 means gone; there is nothing meaningful to return.
      D6. Non-structural references are left alone. A `blocked_by` entry pointing at
          the deleted note is not rewritten -- silently editing notes the caller did
          not name would be worse than a dangling reference that /problems reports.
    """
    service.delete(title, cascade=cascade)
    return Response(status_code=204)


def get_children(
    title: str,
    recursive: bool = Query(False, description="Whole subtree instead of one level."),
    service: NoteService = Depends(get_service),
):
    """Children of a note.

    INVARIANTS
      H1. Pure. (S2)
      H2. A missing parent is 404, not []. An empty list means "exists, no children";
          conflating that with "no such note" hides typos.
      H3. Recursive is a superset of direct. Every direct child appears in the
          recursive result.
      H4. Never includes itself, even if a hand-edited note names itself as parent.
      H5. Terminates. Cycles are possible -- nothing in Obsidian prevents two notes
          pointing at each other -- and a naive walk would spin forever.
      H6. Each note appears once, however many paths reach it.
      H7. This is the query Bases cannot express. There are no joins and no recursion
          in the app, which is why `project` is denormalised onto every ticket; here
          the walk is real.
    """
    service.get(title)          # 404 rather than an empty list for a missing parent
    found = service.descendants_of(title) if recursive else service.children_of(title)
    return [n.to_dict() for n in found]


def close_note(
    title: str,
    status: S.ClosingStatusEnum = Query(S.ClosingStatusEnum.DONE),
    on: datetime.date | None = Query(None, description="Defaults to today."),
    service: NoteService = Depends(get_service),
):
    """Close a ticket.

    INVARIANTS
      X1. Three fields move together, always. `status`, the `done` checkbox and the
          `closed` date are one transition. Triage carries a "Done but no closed date"
          view precisely because closing by hand moves two of the three.
      X2. `done` follows the *reason*, not the fact of closing. Cancelled work is
          closed but was never done, and the board's `lane` formula reads them
          separately -- so cancelling leaves `done` false.
      X3. Post-condition: `is_open` is false. This is the property the board's `open`
          formula relies on, and the one callers actually care about.
      X4. Idempotent in state. Closing twice yields the same fields; only an explicit
          `on` changes the date. (S6)
      X5. Tickets only. A doc has no notion of completion. The refusal names that,
          rather than surfacing "'closed' is not a field of kind 'doc'" from deep
          inside validation -- a true statement about a symptom.
      X6. Only closing statuses close. `doing` is rejected here; it is a PATCH.
      X7. Reversible. reopen restores an open state, so this is not a trapdoor.
    """
    return service.close(title, status=status, on=on).to_dict()


def reopen_note(title: str, status: S.StatusEnum = Query(S.StatusEnum.TODO),
                service: NoteService = Depends(get_service)):
    """Reopen a closed ticket.

    INVARIANTS
      R1. The inverse of close for the fields close touches: `closed` is removed and
          `done` is false. It is not a full undo -- the original closing date is gone,
          because keeping it would mean storing history the vault has nowhere to put.
      R2. Post-condition: `is_open` is true. (Mirror of X3.)
      R3. The target status must belong to this kind's vocabulary. Reopening into a
          status the board cannot render would hide the ticket, which is the exact
          failure Triage exists to catch.
      R4. Tickets only, as with close. (X5)
      R5. Idempotent. (S6)
      R6. Safe on an already-open ticket: it becomes a status change, not an error.
    """
    return service.reopen(title, status=status).to_dict()
