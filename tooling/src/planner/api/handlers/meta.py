"""Schema, triage and health.

These describe the system rather than the content. Invariants reference the system
invariants (S1-S9) documented in api/app.py.
"""

from __future__ import annotations

from fastapi import Depends

from ...domain import schema as S
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import KindOut, Problem, SchemaOut


def get_schema():
    """The rules this server enforces.

    INVARIANTS
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
          without trial and error -- which is what an MCP model does with it.
    """
    return SchemaOut(
        kinds=[
            KindOut(name=k.name, folder=k.folder, statuses=list(k.statuses),
                    default_status=k.default_status,
                    fields=list(S.allowed_fields(k.name)),
                    parent_kinds=list(k.parent_kinds), has_done=k.has_done)
            for k in S.KINDS.values()
        ],
        vocabularies={
            "ticket_status": list(S.TICKET_STATUS),
            "container_status": list(S.CONTAINER_STATUS),
            "routine_status": list(S.ROUTINE_STATUS),
            "doc_status": list(S.DOC_STATUS),
            "decision_status": list(S.DECISION_STATUS),
            "issue_type": list(S.ISSUE_TYPE),
            "recur": list(S.RECUR),
            "closing_status": list(S.CLOSED_STATUS),
            "priority_range": list(S.PRIORITY_RANGE),
        },
    )


def get_problems(service: NoteService = Depends(get_service)):
    """Every note the API would refuse to accept.

    This is the Triage base as an endpoint, and it exists because of what Obsidian
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
      P7. Deterministic order, so two runs are diffable.
    """
    return [Problem(title=t, message=m) for t, m in service.problems()]


def health(service: NoteService = Depends(get_service)):
    """Liveness, plus whether the configured vault is actually there.

    INVARIANTS
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
          nobody intended -- the one thing a health check must not stay quiet about.
    """
    status = service.vault_status()
    return {
        "status": "ok" if status["reachable"] else "vault-missing",
        "vault": status["vault"],
        # An interrupted transaction means the vault may hold state nobody intended --
        # the one condition a health check must not stay quiet about.
        "interrupted_transaction": status["interrupted_transaction"],
    }
