"""Consistent public API errors with request correlation IDs."""

from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def http_exception_handler(request: Request, exception: HTTPException) -> JSONResponse:
    detail = exception.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", "request_failed"))
        message = str(detail.get("message", "The request could not be completed"))
    else:
        code = "request_failed"
        message = str(detail)
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=exception.status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={**(exception.headers or {}), "X-Request-ID": request_id},
    )


async def validation_exception_handler(
    request: Request, _exception: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )
