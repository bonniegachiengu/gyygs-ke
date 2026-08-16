"""Domain errors and their HTTP mapping.

ARCHITECTURE.md §5: "422 for schema errors (FastAPI default); 400 for domain errors."

A schema error means the request was malformed (missing `contact.name`, a negative
quantity). A domain error means the request was well-formed but asked for something the
catalogue does not contain (an unknown service key, a carpet size that isn't a tier).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """A well-formed request that the domain cannot satisfy. Maps to HTTP 400."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    payload: dict[str, str] = {"detail": exc.message}
    if exc.field:
        payload["field"] = exc.field
    return JSONResponse(status_code=400, content=payload)
