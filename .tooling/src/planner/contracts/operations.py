"""What each operation promises, in words, shared by every transport.

Three things per operation: a one-line `summary` for tables, `guidance` for someone
meeting it for the first time, and the numbered `invariants` it upholds.

WHY THIS IS NOT IN THE API LAYER

It was -- in the route handlers' docstrings -- while the MCP tools carried their own,
shorter prose, on the theory that a model and a developer want different things. That
was wrong. A developer new to the repo does not know to read GET /schema before creating
a note any more than a model does; the only reader that distinction fits is one who
already knows the system. The result was Swagger showing the contract without the
operational advice and the tools showing the advice without the contract, each missing
what the other had.

Moving it here rather than having MCP import it from `api` is what the layering test
insists on, and rightly: a transport depending on another transport would mean removing
REST breaks MCP.

Per-endpoint invariants cite the system invariants (S1-S9) in api/invariants.py by
number, so a local rule can be traced to the principle behind it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Operation:
    summary: str
    guidance: str
    invariants: str = ""

    @property
    def description(self) -> str:
        """Guidance first, then the contract -- used verbatim by OpenAPI and by the MCP
        tool covering the same operation."""
        return "\n\n".join(p for p in (self.guidance.strip(),
                                        self.invariants.strip()) if p)


#: Keyed by (method, path), matching the routing table.
OPERATIONS: dict[tuple[str, str], Operation] = {
    ("GET", "/notes"): Operation(
        summary='List notes',
        guidance='List notes, optionally filtered. Returns title, kind and every field for each. Use `open` to exclude done and cancelled work.',
        invariants="""INVARIANTS
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
      not here. The two endpoints partition the vault.""",
    ),
    ("POST", "/notes"): Operation(
        summary='Create a note',
        guidance='Create a note. The folder is chosen from `kind`. Links are plain titles, not `[[wikilink]]` syntax. Which fields are legal depends on kind -- read GET /schema first if unsure.',
        invariants="""INVARIANTS
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
  C8. What is created is clean. A note made here never appears in /problems. (S8)""",
    ),
    ("POST", "/notes/bulk"): Operation(
        summary='Create several notes as one transaction',
        guidance='Create several notes as one transaction -- either all of them exist afterwards or none do. Order matters: a child listed before its parent fails.',
        invariants="""INVARIANTS
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
      atomic rename. (Documented limit of the unit of work.)""",
    ),
    ("GET", "/notes/{title}"): Operation(
        summary='Fetch one note',
        guidance='Fetch one note by title. Matching ignores case, as it does everywhere else.',
        invariants="""INVARIANTS
  G1. Pure. (S2)
  G2. Lookup is case-insensitive, matching creation (C4). Without this the same
      request would 200 on macOS and 404 on Linux, since the filesystem rather than
      the application would be deciding.
  G3. Missing is 404 with the standard error shape. (S4)
  G4. Storage detail stays hidden: links come back as plain titles, and `icon`/
      `iconColor` are omitted because they are derived from `kind`. (S5)
  G5. Round-trips. Feeding this response back to POST in a fresh vault reproduces
      the note. (S9)""",
    ),
    ("PATCH", "/notes/{title}"): Operation(
        summary='Update a note',
        guidance='Change fields on an existing note. A field sent as null is removed; a field left out is untouched. `kind` cannot be changed.',
        invariants="""INVARIANTS
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
      POST would have required. (S1)""",
    ),
    ("DELETE", "/notes/{title}"): Operation(
        summary='Delete a note',
        guidance='Delete a note permanently. A note with children is refused unless you pass `cascade`.',
        invariants="""INVARIANTS
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
      not name would be worse than a dangling reference that /problems reports.""",
    ),
    ("GET", "/notes/{title}/children"): Operation(
        summary='Direct children',
        guidance='The notes hanging off this one. Use `recursive` for the whole subtree. This is the query the Obsidian side cannot answer -- Bases has no joins and no recursion -- so it is worth reaching for rather than following `parent` one note at a time.',
        invariants="""INVARIANTS
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
      the walk is real.""",
    ),
    ("POST", "/notes/{title}/close"): Operation(
        summary='Close a ticket',
        guidance='Close a ticket. Sets the status, ticks `done` and stamps `closed` in one step; all three must move together. Only tickets track completion -- a doc cannot be closed.',
        invariants="""INVARIANTS
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
  X7. Reversible. reopen restores an open state, so this is not a trapdoor.""",
    ),
    ("POST", "/notes/{title}/reopen"): Operation(
        summary='Reopen a ticket',
        guidance='Reopen a closed ticket: clears `closed`, unticks `done`, and puts it back in the status you give. The inverse of close, though not a full undo -- the original closing date is gone.',
        invariants="""INVARIANTS
  R1. The inverse of close for the fields close touches: `closed` is removed and
      `done` is false. It is not a full undo -- the original closing date is gone,
      because keeping it would mean storing history the vault has nowhere to put.
  R2. Post-condition: `is_open` is true. (Mirror of X3.)
  R3. The target status must belong to this kind's vocabulary. Reopening into a
      status the board cannot render would hide the ticket, which is the exact
      failure Triage exists to catch.
  R4. Tickets only, as with close. (X5)
  R5. Idempotent. (S6)
  R6. Safe on an already-open ticket: it becomes a status change, not an error.""",
    ),
    ("GET", "/schema"): Operation(
        summary='Kinds, fields, vocabularies',
        guidance='The note types, which fields each allows, and the vocabularies. Read this before creating notes if unsure which fields apply to a kind; it is generated from the same module that enforces them, so it cannot promise something a write would reject.',
        invariants="""INVARIANTS
  M1. Generated, not written. Every value comes from domain/schema.py, the same
      module the validator reads. It is therefore impossible for this endpoint to
      promise something a write would reject -- the failure mode a hand-maintained
      API document always eventually has.
  M2. Complete. Every kind the API accepts appears, with its folder, its legal
      fields, its status vocabulary and the kinds its `parent` may point at.
  M3. Vault-independent. It touches no note and needs no vault, so it answers
      identically against an empty directory. This is what makes it usable as a
      discovery call before anything exists.
  M4. Pure and cacheable within a process: the rules cannot change at runtime.
  M5. Self-consistent. Each kind's `default_status` is a member of its own
      `statuses`; otherwise every newly created note of that kind would land in
      Triage the instant it was made.
  M6. Sufficient. A client that reads this can construct a valid note for any kind
      without trial and error -- which is what an MCP model does with it.""",
    ),
    ("GET", "/problems"): Operation(
        summary='Notes that fail to validate',
        guidance='Notes that fail to parse or validate -- misspelled statuses, out-of-range priorities, structural links that do not resolve. Obsidian reports none of these itself, because Bases has no enum type and cannot follow a link to check it.',
        invariants="""This is the Triage base as an endpoint, and it exists because of what Obsidian
cannot do: Bases has no enum property type, so a misspelled status raises nothing
-- the ticket simply stops appearing where you expect it. Nor can Bases follow a
link to check that it resolves, so a `parent` pointing at a deleted note looks
exactly like one that works.

INVARIANTS
  P1. Pure, and total. It reports on broken notes without ever failing on one;
      an endpoint whose job is finding malformed input cannot itself be defeated
      by malformed input. (S2)
  P2. Complementary to GET /notes, and overlapping on purpose. Their union is
      every note on disk, so nothing is invisible to the API; their intersection
      is the notes that parse but fail validation. Those stay listable and
      patchable, since a note repairable only by hand in Obsidian is a note the
      API cannot help with. A note that will not parse appears here alone.
  P3. Empty by construction. A vault built only through this API always returns
      []. Anything here arrived by hand or by another process. That is what makes
      a non-empty result meaningful rather than noise. (S1, S8)
  P4. Covers values *and* structure -- bad vocabularies, unparseable frontmatter,
      and structural links (`parent`, `project`, `area`, `blocked_by`,
      `supersedes`) that do not resolve.
  P5. Reports, never repairs. Silently rewriting someone's notes is a worse
      failure than the one being reported, and the vault is edited concurrently by
      an app that would not expect it.
  P6. Link checking is case-insensitive, matching how notes are found (G2) and
      created (C4), so a link differing only in case is not falsely flagged.
  P7. Deterministic order, so two runs are diffable.""",
    ),
    ("GET", "/health"): Operation(
        summary='Liveness and vault reachability',
        guidance='Liveness, the resolved vault path, and whether a transaction was interrupted.',
        invariants="""INVARIANTS
  N1. Always 200 while the process is alive. A missing vault is reported in the
      body, not as an error status -- "the server is up but misconfigured" and
      "the server is down" are different conditions and a load balancer must be
      able to tell them apart.
  N2. Cheap. It stats one directory; it does not read, parse or count notes, so it
      stays fast on a large vault and safe to poll.
  N3. Pure. It never creates the vault directory it is checking for. (S2)
  N4. Discloses the resolved vault path, because the commonest deployment mistake
      here is a PLANNER_VAULT pointing somewhere unexpected, and a health check
      that hides the answer makes that harder to see rather than easier.
  N5. Reports an interrupted transaction. A journal still on disk means startup
      recovery has not run or could not finish, and the vault may hold state
      nobody intended -- the one thing a health check must not stay quiet about.""",
    ),
}
