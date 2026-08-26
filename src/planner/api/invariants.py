"""The system invariants, as data.

Properties that hold across every endpoint. Per-endpoint invariants are documented on
the routes themselves and are meant to be *instances* of these, not exceptions to them;
where an endpoint cannot honour one, it says so and gives the reason.

WHY THIS IS A TABLE AND NOT PROSE

These were written twice in api/app.py: once in the module docstring with the reasoning,
once as a markdown table for the OpenAPI description. Two hand-maintained copies of nine
rules, in one file, is the same shape of problem as the note fields that had already
drifted across three files -- and a client reading a stale invariant is worse served
than one reading none, because they will believe it.

So each invariant is a record, and both renderings are generated from it. The long
`rationale` is the source; the short `summary` is what fits in a table cell.

GUARANTEE vs DETECTION

The vault is a folder of markdown that Obsidian edits too, at any moment, with no
locking. That splits the properties into two kinds, and conflating them is how an API
over a shared store ends up promising more than it can deliver:

    GUARANTEE   what this API will never itself do
    DETECTION   what it will tell you about when someone else has done it
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["guarantee", "detection"]


@dataclass(frozen=True)
class Invariant:
    id: str
    name: str
    kind: Kind
    summary: str        # one line; what a client needs
    rationale: str      # why, and what it cost to hold


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        "S1", "CLOSURE", "guarantee",
        "No operation produces a state another would refuse. Structural links "
        "(`parent`, `project`, `area`) are protected on both sides; reference links "
        "(`blocked_by`, `supersedes`) on write only — deleting a blocker may leave a "
        "dangling reference, which `/problems` reports.",
        """No operation may produce a state that another operation would refuse to
create. A write path that rejects a dangling `parent` while a delete path manufactures
one is not a validated system, only a system with validation in it. This is why DELETE
refuses to orphan children rather than silently succeeding.

Links come in two kinds and are protected differently:

  STRUCTURAL   `parent`, `project`, `area` -- the hierarchy depends on them. Protected
               on both sides: they cannot be created dangling, and a note cannot be
               deleted out from under one. Closure is absolute.

  REFERENCE    `blocked_by`, `supersedes` -- one note mentioning another. Protected on
               write only. Deleting a blocker is a legitimate act, and both
               alternatives are worse: refusing to delete anything mentioned anywhere
               would make the vault immovable, and silently editing notes the caller
               never named would be a surprise write. So a delete CAN leave a dangling
               reference, and GET /problems reports it. This is the sole exception, and
               it is a deliberate trade rather than an oversight."""),

    Invariant(
        "S2", "PURITY OF READS", "guarantee",
        "`GET` never writes, and never touches mtime.",
        """GET never changes the vault. No lazy migration, no touching mtimes -- mtime
is load-bearing here, because Triage's "stale" view reads it and Iconize repaints on
it."""),

    Invariant(
        "S3", "ATOMICITY", "guarantee",
        "A rejected write leaves the vault byte-identical.",
        """A rejected write leaves the vault byte-identical. Validation completes before
the first byte is written; there is no partially-applied note. Multi-note operations run
inside a unit of work, so a failure part-way restores what it had already changed."""),

    Invariant(
        "S4", "ONE ERROR SHAPE", "guarantee",
        "Every deliberate 4xx is `{detail, field}`.",
        """Every deliberate 4xx is {"detail": str, "field": str | null}. Both validation
layers -- the DTO enums and the domain -- normalise to it, because which of the two
fired is an implementation detail no client should have to model."""),

    Invariant(
        "S5", "STORAGE IS NOT THE CONTRACT", "guarantee",
        "No wikilinks, folders or icon names cross the wire.",
        """Wikilink syntax, folder placement and icon names never cross the wire. Links
are plain titles in and out; `kind` decides the folder; `icon`/`iconColor` are derived
and are not echoed, so a client cannot send one that disagrees."""),

    Invariant(
        "S6", "DECLARED IDEMPOTENCE", "guarantee",
        "`PATCH`, close and reopen are idempotent; `POST` is not; `DELETE` "
        "deliberately 404s on the second call.",
        """An operation documented as idempotent is idempotent. PATCH, close and reopen
are. POST is not, and says so. DELETE is deliberately NOT idempotent: the second call
404s, matching GET and PATCH on a missing note, so "did that exist?" has one answer
across the API rather than a special case."""),

    Invariant(
        "S7", "TRANSPORT PARITY", "guarantee",
        "REST and MCP share one service; neither holds rules of its own.",
        """REST and MCP call the same NoteService. A rule enforced on one is enforced on
the other; neither holds business logic of its own. The wire shapes they publish come
from one `contracts` module, so the two cannot offer different fields."""),

    Invariant(
        "S8", "TRIAGE COMPLETENESS", "detection",
        "`/problems` reports every state the API would refuse. `/notes` and "
        "`/problems` overlap; their union is the whole vault.",
        """GET /problems reports every state the API would refuse to create -- bad
vocabularies, unparseable frontmatter, and structural links that do not resolve. S1
keeps the API from creating them; S8 is how you find the ones that arrived by hand. A
vault built solely through this API always has an empty /problems, except across the S1
reference-link exception above.

Note that /notes and /problems OVERLAP rather than partition. A note that parses but
fails validation appears in both, deliberately: excluding it from /notes would leave it
repairable only by hand in Obsidian. Their union is every note on disk -- that is the
property worth having, not disjointness."""),

    Invariant(
        "S9", "ROUND-TRIP FIDELITY", "guarantee",
        "What `POST` returns is what `GET` returns.",
        """What POST returns is what a subsequent GET returns. Writing a note and
reading it back is lossless, including the markdown body."""),
)

BY_ID = {invariant.id: invariant for invariant in INVARIANTS}


def as_prose() -> str:
    """The long form, for anyone reading the source."""
    return "\n\n".join(
        f"{i.id}. {i.name} ({i.kind})\n"
        + "\n".join("    " + line for line in i.rationale.splitlines())
        for i in INVARIANTS
    )


def as_markdown_table() -> str:
    """The short form, for the OpenAPI description and therefore Swagger.

    A client author should not have to read the source to learn what this API promises,
    which is why the summaries are published rather than merely written down.
    """
    rows = "\n".join(
        f"| **{i.id}** | {i.name} | {i.kind} | {i.summary} |" for i in INVARIANTS)
    return "| | | | |\n|---|---|---|---|\n" + rows
