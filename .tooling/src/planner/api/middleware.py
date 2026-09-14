"""Cross-cutting request handling: correlation ids, timing, and domain-error mapping.

Error translation lives here rather than in the controllers so every transport
gets the same treatment from one place. A controller that catches NoteNotFoundError
itself
is a controller that will eventually forget to, and the caller gets a 500 for a
condition the domain described precisely.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from ..domain.errors import (
    ChildrenExistError,
    NoteExistsError,
    NoteNotFoundError,
    PlannerError,
    ValidationError,
)

log = logging.getLogger("planner.api")

#: Domain error -> HTTP status. The domain does not know about HTTP; this is the only
#: place the two vocabularies meet.
STATUS_FOR = {
    ValidationError: 422,
    NoteNotFoundError: 404,
    NoteExistsError: 409,
    ChildrenExistError: 409,
}


async def correlation_id(request: Request, call_next):
    """Attach a request id and log how long the call took.

    The vault is a directory another process (Obsidian) also writes to, so when a
    result looks wrong the first question is usually "what else touched it, and when".
    An id in the response header makes that traceable.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
    log.info(
        "%s %s -> %s in %.1fms [%s]",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response


def install_error_handlers(app):
    """Register the handlers that turn domain errors into the one error shape."""
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _request_invalid(request: Request, exc: RequestValidationError):
        """Normalise pydantic's failures into the domain's error shape.

        Both layers now reject the same things -- the DTO enum catches a bad `status`
        before the domain sees it -- so which one fires is an implementation detail.
        Leaking two different error bodies for one logical failure would push that
        detail onto every client, and onto an MCP model trying to correct itself.
        """
        first = exc.errors()[0] if exc.errors() else {}
        location = [str(p) for p in first.get("loc", []) if p not in ("body", "query")]
        field = location[-1] if location else None
        detail = first.get("msg", "request validation failed")
        given = first.get("input")
        if given is not None and field:
            detail = f"{field}: {detail} (got {given!r})"
        return JSONResponse(
            status_code=422,
            content={"detail": detail, "field": field},
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(PlannerError)
    async def _domain_error(request: Request, exc: PlannerError):
        status = next(
            (code for kind, code in STATUS_FOR.items() if isinstance(exc, kind)), 400
        )
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "field": getattr(exc, "field", None)},
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )
