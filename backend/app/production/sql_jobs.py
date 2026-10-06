"""PostgreSQL implementation of the jobs repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import settings
from app.production.jobs import (
    JobEventRecord,
    JobRecord,
    JobStatus,
    JobSubmit,
    job_request_hash,
    queue_for_kind,
    validate_idempotency_hash,
)
from app.production.models import Job, JobEvent


class SqlJobRepository:
    """Async SQLAlchemy job repository with row-locked state transitions."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def submit(
        self,
        owner_key_id: str,
        submission: JobSubmit,
        idempotency_key: str | None,
    ) -> tuple[JobRecord, bool]:
        """Create a job or return the previous idempotent job."""
        async with self.sessions() as session:
            request_hash = job_request_hash(submission)
            if idempotency_key:
                query = select(Job).where(
                    Job.owner_key_id == owner_key_id,
                    Job.idempotency_key == idempotency_key,
                )
                existing = await session.scalar(query)
                if existing:
                    validate_idempotency_hash(existing.request_hash, request_hash)
                    return _record(existing), False
            row = Job(
                owner_key_id=owner_key_id,
                kind=submission.kind,
                queue=queue_for_kind(submission.kind),
                status=JobStatus.QUEUED.value,
                payload=submission.payload,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                max_attempts=submission.max_retries + 1,
                timeout_seconds=submission.timeout_seconds,
            )
            session.add(row)
            try:
                await session.flush()
                session.add(
                    JobEvent(
                        job_id=row.id,
                        sequence=1,
                        event_type="queued",
                        data={"queue": row.queue},
                    )
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if not idempotency_key:
                    raise
                existing = await session.scalar(
                    select(Job).where(
                        Job.owner_key_id == owner_key_id,
                        Job.idempotency_key == idempotency_key,
                    )
                )
                if existing is None:
                    raise
                validate_idempotency_hash(existing.request_hash, request_hash)
                return _record(existing), False
            return _record(row), True

    async def get(self, job_id: str, owner_key_id: str) -> JobRecord | None:
        """Get an owned job."""
        async with self.sessions() as session:
            row = await session.scalar(
                select(Job).where(Job.id == job_id, Job.owner_key_id == owner_key_id)
            )
            return _record(row) if row else None

    async def cancel(self, job_id: str, owner_key_id: str) -> JobRecord | None:
        """Set cooperative cancellation under a row lock."""
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(Job)
                .where(Job.id == job_id, Job.owner_key_id == owner_key_id)
                .with_for_update()
            )
            if row is None:
                return None
            row.cancel_requested = True
            if row.status in {JobStatus.QUEUED.value, JobStatus.RETRYING.value}:
                row.status = JobStatus.CANCELLED.value
                await _append_event(session, row.id, "cancelled", {})
            return _record(row)

    async def events(self, job_id: str, after: int = 0) -> list[JobEventRecord]:
        """Return ordered job events after a sequence."""
        async with self.sessions() as session:
            rows = (
                await session.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job_id, JobEvent.sequence > after)
                    .order_by(JobEvent.sequence)
                )
            ).all()
            return [
                JobEventRecord(
                    sequence=row.sequence,
                    event_type=row.event_type,
                    data=row.data,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def acquire(self, job_id: str, worker_id: str) -> JobRecord:
        """Acquire an expired lease using a row lock."""
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if row is None:
                raise KeyError(job_id)
            now = datetime.now(UTC)
            if row.lease_expires_at and row.lease_expires_at > now:
                raise RuntimeError("job lease is already held")
            if row.cancel_requested:
                row.status = JobStatus.CANCELLED.value
                await _append_event(session, row.id, "cancelled", {})
                return _record(row)
            row.status = JobStatus.RUNNING.value
            row.attempts += 1
            row.lease_owner = worker_id
            row.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
            await _append_event(session, row.id, "running", {"attempt": row.attempts})
            return _record(row)

    async def finish(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> JobRecord:
        """Commit success, retry, cancellation, or dead-letter state."""
        async with self.sessions.begin() as session:
            row = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if row is None:
                raise KeyError(job_id)
            row.lease_owner = None
            row.lease_expires_at = None
            if row.cancel_requested:
                row.status = JobStatus.CANCELLED.value
                event_type, data = "cancelled", {}
            elif error is None:
                row.status, row.result = JobStatus.SUCCEEDED.value, result or {}
                event_type, data = "succeeded", row.result
            elif row.attempts < row.max_attempts:
                row.status, row.error = JobStatus.RETRYING.value, error
                event_type, data = "retrying", error
            else:
                row.status, row.error = JobStatus.DEAD_LETTER.value, error
                event_type, data = "dead_letter", error
            await _append_event(session, row.id, event_type, data)
            return _record(row)


async def _append_event(session: Any, job_id: str, event_type: str, data: dict[str, Any]) -> None:
    sequence = await session.scalar(
        select(func.coalesce(func.max(JobEvent.sequence), 0)).where(JobEvent.job_id == job_id)
    )
    session.add(
        JobEvent(job_id=job_id, sequence=int(sequence) + 1, event_type=event_type, data=data)
    )


def _record(row: Job, timeout_seconds: int | None = None) -> JobRecord:
    return JobRecord(
        id=row.id,
        owner_key_id=row.owner_key_id or "",
        kind=row.kind,
        payload=row.payload,
        queue=row.queue,
        status=JobStatus(row.status),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        timeout_seconds=timeout_seconds or row.timeout_seconds,
        cancel_requested=row.cancel_requested,
        result=row.result,
        error=row.error,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at or row.created_at,
    )
