"""Request correlation and stable API error envelopes."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings

logger = logging.getLogger(__name__)


class RedactingLogFilter(logging.Filter):
    """Redact configured sensitive keys from structured dictionary arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            sensitive = {field.lower() for field in settings.redact_log_fields}
            record.args = {
                key: "[REDACTED]" if str(key).lower() in sensitive else value
                for key, value in record.args.items()
            }
        return True


def _serializable_errors(errors: Any) -> Any:
    """Stringify validator exceptions that pydantic places in ``ctx`` so errors encode."""
    cleaned = []
    for error in errors:
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error = {**error, "ctx": {key: str(value) for key, value in ctx.items()}}
        cleaned.append(error)
    return jsonable_encoder(cleaned)


def install_log_redaction() -> None:
    """Install the redaction filter on current root handlers."""
    redactor = RedactingLogFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a trusted request ID to every request and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(settings.request_id_header)
        if not request_id or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id):
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request failure", extra={"request_id": request_id})
            return error_response(request_id, 500, "internal_error", "Internal server error")
        response.headers[settings.request_id_header] = request_id
        return response


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce the configured request rate with Redis in production."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.redis_url:
            return await call_next(request)
        from app.production.infrastructure import RedisInfrastructure

        credential = request.headers.get("X-API-Key")
        source = credential or (request.client.host if request.client else "unknown")
        identity = hashlib.sha256(source.encode()).hexdigest()
        redis = RedisInfrastructure(settings.redis_url)
        try:
            allowed = await redis.allow_request(identity, settings.rate_limit_per_minute)
        finally:
            await redis.close()
        if not allowed:
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            return error_response(request_id, 429, "rate_limited", "Rate limit exceeded")
        return await call_next(request)


def error_response(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """Build the stable JSON error response."""
    body: dict[str, Any] = {
        "error": {"code": code, "message": message},
        "request_id": request_id,
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def install_error_handlers(app: FastAPI) -> None:
    """Install HTTP and validation handlers without leaking production internals."""

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        message = str(exc.detail)
        return error_response(
            getattr(request.state, "request_id", "unknown"),
            exc.status_code,
            "http_error",
            message,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = (
            _serializable_errors(exc.errors()) if settings.environment != "production" else None
        )
        return error_response(
            getattr(request.state, "request_id", "unknown"),
            422,
            "validation_error",
            "Request validation failed",
            details,
        )
