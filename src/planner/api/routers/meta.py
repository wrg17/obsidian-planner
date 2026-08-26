"""Schema and vault-health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...domain import schema as S
from ...service.notes import NoteService
from ..dependencies import get_service
from ..schemas import KindOut, Problem, SchemaOut

router = APIRouter(tags=["meta"])


@router.get("/schema", response_model=SchemaOut, summary="Kinds, fields, vocabularies")
def get_schema():
    """The rules the server actually enforces.

    Generated from the same module the domain validates against, so this cannot
    promise something the validator would reject.
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


@router.get("/problems", response_model=list[Problem], summary="Notes that fail to validate")
def get_problems(service: NoteService = Depends(get_service)):
    """The Triage base as an endpoint.

    Bases has no enum property type, so a misspelled status raises nothing in Obsidian
    -- the ticket just stops appearing where you expect it.
    """
    return [Problem(title=t, message=m) for t, m in service.problems()]


@router.get("/health", summary="Liveness and vault reachability")
def health(service: NoteService = Depends(get_service)):
    root = service.repo.root
    return {"status": "ok" if root.is_dir() else "vault-missing", "vault": str(root)}
