"""Schema, triage and health.

These describe the system rather than the content, and none of them touches a note's
contents -- which is why `get_schema` needs no vault at all.

What each promises is in `contracts/operations.py`, and the system invariants those
cite (S1-S9) are in `api/invariants.py`.
"""

from __future__ import annotations

from fastapi import Depends

from ...domain import schema as S
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import KindOut, Problem, SchemaOut


def get_schema():
    """The rules this server enforces.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
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

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    return [Problem(title=t, message=m) for t, m in service.problems()]


def health(service: NoteService = Depends(get_service)):
    """Liveness, plus whether the configured vault is actually there.

    What this operation promises -- the guidance a newcomer needs and the numbered
    invariants it upholds -- is in `contracts/operations.py`, keyed by
    (method, path). It lives there rather than here because the MCP tool for the
    same operation publishes that text too, and neither transport should have to
    import the other to get it.
    """
    status = service.vault_status()
    return {
        "status": "ok" if status["reachable"] else "vault-missing",
        "vault": status["vault"],
        # An interrupted transaction means the vault may hold state nobody intended --
        # the one condition a health check must not stay quiet about.
        "interrupted_transaction": status["interrupted_transaction"],
    }
