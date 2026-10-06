"""Job contracts and concurrency-safe development repository."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.schemas import AgentPlanRequest
from app.config import settings


class JobStatus(str, Enum):
    """Durable job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.DEAD_LETTER,
}
PUBLIC_JOB_KINDS = frozenset(
    {"agent_route", "txt2img", "inpaint", "decompose", "text_edit"}
)


class Txt2ImgJobPayload(BaseModel):
    """Executable txt2img worker input."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=4_000)
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, ugly",
        max_length=4_000,
    )
    seed: int = Field(default=42, ge=0)
    steps: int = Field(default=20, ge=1, le=150)
    backend: Literal["auto", "local", "sd15", "flux", "openai", "dashscope"] = "auto"


class StoredImageInput(BaseModel):
    """Owner-bound persisted image input."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID


class InpaintJobPayload(BaseModel):
    """Executable inpaint artifact input."""

    model_config = ConfigDict(extra="forbid")

    image: StoredImageInput
    mask: StoredImageInput
    prompt: str = Field(min_length=1, max_length=4_000)
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, ugly",
        max_length=4_000,
    )
    seed: int = Field(default=42, ge=0)
    steps: int = Field(default=20, ge=1, le=150)
    backend: Literal["auto", "local", "sd15", "flux", "openai", "dashscope"] = "auto"


class DecomposeJobPayload(BaseModel):
    """Executable decompose artifact input."""

    model_config = ConfigDict(extra="forbid")

    image: StoredImageInput
    background_prompt: str = Field(default="clean seamless background", max_length=4_000)
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, ugly",
        max_length=4_000,
    )


class TextEditJobPayload(BaseModel):
    """Executable text-edit artifact input."""

    model_config = ConfigDict(extra="forbid")

    image: StoredImageInput
    bbox: list[int] = Field(min_length=4, max_length=4)
    new_text: str = Field(min_length=1, max_length=2_000)
    inpaint_prompt: str = Field(default="clean seamless background", max_length=4_000)
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, ugly, text, letters",
        max_length=4_000,
    )


class JobSubmit(BaseModel):
    """Public job submission; only kinds with executable handlers are accepted."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["agent_route", "txt2img", "inpaint", "decompose", "text_edit"]
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=600, ge=1, le=86_400)
    max_retries: int = Field(default=2, ge=0, le=10)

    @model_validator(mode="after")
    def validate_payload(self) -> "JobSubmit":
        """Validate and normalize payload according to the executable kind."""
        if self.kind == "agent_route":
            validated = AgentPlanRequest.model_validate(self.payload)
        elif self.kind == "txt2img":
            validated = Txt2ImgJobPayload.model_validate(self.payload)
        elif self.kind == "inpaint":
            validated = InpaintJobPayload.model_validate(self.payload)
        elif self.kind == "decompose":
            validated = DecomposeJobPayload.model_validate(self.payload)
        else:
            validated = TextEditJobPayload.model_validate(self.payload)
        self.payload = validated.model_dump(mode="json", exclude_none=True)
        return self


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


def job_request_hash(submission: JobSubmit) -> str:
    """Return a deterministic hash for idempotency conflict detection."""
    canonical = json.dumps(
        submission.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_idempotency_hash(existing_hash: str, request_hash: str) -> None:
    """Raise a conflict when an idempotent retry changes request content."""
    if existing_hash != request_hash:
        raise IdempotencyConflict(
            "Idempotency-Key was already used with a different request"
        )


class JobEventRecord(BaseModel):
    """Ordered job event."""

    sequence: int
    event_type: str
    data: dict[str, Any]
    created_at: datetime


class JobRecord(BaseModel):
    """Serializable job state."""

    id: str
    owner_key_id: str
    kind: str
    payload: dict[str, Any]
    queue: str
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    max_attempts: int
    timeout_seconds: int
    cancel_requested: bool = False
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def queue_for_kind(kind: str) -> str:
    """Choose an isolated queue for GPU, CPU, or external API workloads."""
    if kind in {"txt2img", "inpaint", "decompose", "text_edit"}:
        return settings.queue_gpu
    if kind in {"thumbnail", "validate_image"}:
        return settings.queue_cpu
    return settings.queue_api


class MemoryJobRepository:
    """Lock-protected job repository for tests and local development."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._events: dict[str, list[JobEventRecord]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        owner_key_id: str,
        submission: JobSubmit,
        idempotency_key: str | None,
    ) -> tuple[JobRecord, bool]:
        """Create a job or return the previous idempotent result."""
        async with self._lock:
            request_hash = job_request_hash(submission)
            if idempotency_key:
                existing = self._idempotency.get((owner_key_id, idempotency_key))
                if existing:
                    existing_id, existing_hash = existing
                    validate_idempotency_hash(existing_hash, request_hash)
                    return self._jobs[existing_id], False
            now = datetime.now(UTC)
            job = JobRecord(
                id=str(uuid.uuid4()),
                owner_key_id=owner_key_id,
                kind=submission.kind,
                payload=submission.payload,
                queue=queue_for_kind(submission.kind),
                max_attempts=submission.max_retries + 1,
                timeout_seconds=submission.timeout_seconds,
                created_at=now,
                updated_at=now,
            )
            self._jobs[job.id] = job
            self._events[job.id] = []
            if idempotency_key:
                self._idempotency[(owner_key_id, idempotency_key)] = (
                    job.id,
                    request_hash,
                )
            self._append_event(job.id, "queued", {"queue": job.queue})
            return job, True

    async def get(self, job_id: str, owner_key_id: str) -> JobRecord | None:
        """Get an owned job."""
        job = self._jobs.get(job_id)
        return job if job and job.owner_key_id == owner_key_id else None

    async def cancel(self, job_id: str, owner_key_id: str) -> JobRecord | None:
        """Request cancellation and immediately cancel queued jobs."""
        async with self._lock:
            job = await self.get(job_id, owner_key_id)
            if job is None:
                return None
            if job.status in TERMINAL_STATUSES:
                return job
            job.cancel_requested = True
            if job.status in {JobStatus.QUEUED, JobStatus.RETRYING}:
                job.status = JobStatus.CANCELLED
                self._append_event(job.id, "cancelled", {})
            job.updated_at = datetime.now(UTC)
            return job

    async def events(self, job_id: str, after: int = 0) -> list[JobEventRecord]:
        """Return events with sequence greater than ``after``."""
        return [event for event in self._events.get(job_id, []) if event.sequence > after]

    async def acquire(self, job_id: str, worker_id: str) -> JobRecord:
        """Acquire or renew an expired lease before execution."""
        async with self._lock:
            job = self._jobs[job_id]
            now = datetime.now(UTC)
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                self._append_event(job.id, "cancelled", {})
                return job
            if job.lease_expires_at and job.lease_expires_at > now:
                raise RuntimeError("job lease is already held")
            job.status = JobStatus.RUNNING
            job.attempts += 1
            job.lease_owner = worker_id
            job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
            job.updated_at = now
            self._append_event(job.id, "running", {"attempt": job.attempts})
            return job

    async def finish(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> JobRecord:
        """Finish, retry, or dead-letter an acquired job."""
        async with self._lock:
            job = self._jobs[job_id]
            job.lease_owner = None
            job.lease_expires_at = None
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                self._append_event(job.id, "cancelled", {})
            elif error is None:
                job.status = JobStatus.SUCCEEDED
                job.result = result or {}
                self._append_event(job.id, "succeeded", job.result)
            elif job.attempts < job.max_attempts:
                job.status = JobStatus.RETRYING
                job.error = error
                self._append_event(job.id, "retrying", error)
            else:
                job.status = JobStatus.DEAD_LETTER
                job.error = error
                self._append_event(job.id, "dead_letter", error)
            job.updated_at = datetime.now(UTC)
            return job

    def _append_event(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        events = self._events[job_id]
        events.append(
            JobEventRecord(
                sequence=len(events) + 1,
                event_type=event_type,
                data=data,
                created_at=datetime.now(UTC),
            )
        )


job_repository = MemoryJobRepository()


class JobRepository(Protocol):
    """Repository contract shared by memory and PostgreSQL implementations."""

    async def submit(
        self, owner_key_id: str, submission: JobSubmit, idempotency_key: str | None
    ) -> tuple[JobRecord, bool]: ...

    async def get(self, job_id: str, owner_key_id: str) -> JobRecord | None: ...

    async def cancel(self, job_id: str, owner_key_id: str) -> JobRecord | None: ...

    async def events(self, job_id: str, after: int = 0) -> list[JobEventRecord]: ...

    async def acquire(self, job_id: str, worker_id: str) -> JobRecord: ...

    async def finish(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> JobRecord: ...


_configured_repository: JobRepository | None = None


def get_job_repository() -> JobRepository:
    """Return the configured development or PostgreSQL repository."""
    global _configured_repository
    if _configured_repository is not None:
        return _configured_repository
    if settings.persistence_backend == "memory":
        _configured_repository = job_repository
        return _configured_repository
    if settings.persistence_backend == "postgres":
        from app.production.models import create_engine
        from app.production.sql_jobs import SqlJobRepository

        _configured_repository = SqlJobRepository(create_engine())
        return _configured_repository
    raise RuntimeError(f"unsupported persistence backend: {settings.persistence_backend}")
