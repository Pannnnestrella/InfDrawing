"""Durable jobs API with idempotency, cancellation, and SSE events."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.production.artifacts import get_artifact_service
from app.production.auth import ApiPrincipal, require_scopes
from app.production.infrastructure import RedisInfrastructure
from app.production.jobs import (
    TERMINAL_STATUSES,
    IdempotencyConflict,
    JobEventRecord,
    JobRecord,
    JobSubmit,
    get_job_repository,
)
from app.production.telemetry import record_audit

router = APIRouter(prefix="/jobs", tags=["jobs"])
repository = get_job_repository()


@router.post("", response_model=JobRecord, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    submission: JobSubmit,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ApiPrincipal = Depends(require_scopes("jobs:write")),
) -> JobRecord:
    """Submit an idempotent asynchronous job."""
    if idempotency_key and len(idempotency_key) > 160:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    await _validate_artifact_ownership(submission, principal.key_id)
    try:
        job, created = await repository.submit(
            principal.key_id, submission, idempotency_key
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created and settings.redis_url:
        redis = RedisInfrastructure(settings.redis_url)
        try:
            await redis.enqueue(job.id, job.queue)
        finally:
            await redis.close()
    await record_audit(
        principal.key_id,
        "job.submit",
        "job",
        job.id,
        details={"kind": job.kind, "queue": job.queue, "created": created},
    )
    return job


@router.get("/{job_id}", response_model=JobRecord)
async def get_job(
    job_id: str,
    principal: ApiPrincipal = Depends(require_scopes("jobs:read")),
) -> JobRecord:
    """Return an owned job."""
    job = await repository.get(job_id, principal.key_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobRecord)
async def cancel_job(
    job_id: str,
    principal: ApiPrincipal = Depends(require_scopes("jobs:write")),
) -> JobRecord:
    """Request cooperative cancellation."""
    job = await repository.cancel(job_id, principal.key_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    await record_audit(
        principal.key_id,
        "job.cancel",
        "job",
        job.id,
        details={"status": job.status.value},
    )
    return job


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    after: int | None = Query(default=None, ge=0),
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID", ge=0),
    principal: ApiPrincipal = Depends(require_scopes("jobs:read")),
) -> StreamingResponse:
    """Stream ordered events with resume support and heartbeat comments."""
    job = await repository.get(job_id, principal.key_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    sequence = after if after is not None else (last_event_id or 0)
    return StreamingResponse(
        _stream_events(job_id, principal.key_id, sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_events(
    job_id: str,
    owner_key_id: str,
    sequence: int,
) -> AsyncIterator[str]:
    last_output = time.monotonic()
    while True:
        events = await repository.events(job_id, sequence)
        for event in events:
            sequence = event.sequence
            last_output = time.monotonic()
            yield _format_event(event)

        current = await repository.get(job_id, owner_key_id)
        if current is None:
            return
        if current.status in TERMINAL_STATUSES:
            trailing = await repository.events(job_id, sequence)
            for event in trailing:
                sequence = event.sequence
                yield _format_event(event)
            return

        now = time.monotonic()
        if now - last_output >= settings.sse_heartbeat_seconds:
            last_output = now
            yield ": heartbeat\n\n"
        await asyncio.sleep(settings.sse_poll_seconds)


def _format_event(event: JobEventRecord) -> str:
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(event.data, ensure_ascii=False)}\n\n"
    )


async def _validate_artifact_ownership(
    submission: JobSubmit,
    owner_key_id: str,
) -> None:
    artifact_ids: list[str] = []
    if submission.kind in {"decompose", "text_edit"}:
        artifact_ids.append(str(submission.payload["image"]["artifact_id"]))
    elif submission.kind == "inpaint":
        artifact_ids.extend(
            (
                str(submission.payload["image"]["artifact_id"]),
                str(submission.payload["mask"]["artifact_id"]),
            )
        )
    service = get_artifact_service()
    for artifact_id in artifact_ids:
        if await service.get_owned(artifact_id, owner_key_id) is None:
            raise HTTPException(status_code=404, detail="artifact not found")
