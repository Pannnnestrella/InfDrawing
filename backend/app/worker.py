"""arq worker entrypoint with leases, retries, timeouts, and GPU slots."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from arq import Retry
from arq.connections import RedisSettings

from app.agent.orchestrator import execute_plan
from app.agent.router import plan_intent
from app.agent.schemas import AgentPlanRequest, IntentPlan, IntentType
from app.config import settings
from app.pipeline.executor import TaskState
from app.pipeline.txt2img_router import resolve_inpaint_backend, resolve_txt2img_backend
from app.production.artifacts import ArtifactRecord, ArtifactResponse, get_artifact_service
from app.production.jobs import (
    DecomposeJobPayload,
    InpaintJobPayload,
    JobRecord,
    JobRepository,
    JobStatus,
    TextEditJobPayload,
    Txt2ImgJobPayload,
    get_job_repository,
)
from app.production.telemetry import ProviderCallEvent, record_provider_call

JobHandler = Callable[[JobRecord, JobRepository], Awaitable[dict[str, Any]]]
_gpu_slots = asyncio.Semaphore(settings.gpu_concurrency)


class JobCancellation(RuntimeError):
    """Raised when a cooperative cancellation is observed."""


async def _route_handler(job: JobRecord, repository: JobRepository) -> dict[str, Any]:
    await _ensure_active(job, repository)
    request = AgentPlanRequest.model_validate(job.payload)
    plan = await plan_intent(request)
    return plan.model_dump(mode="json")


async def _txt2img_handler(job: JobRecord, repository: JobRepository) -> dict[str, Any]:
    await _ensure_active(job, repository)
    request = Txt2ImgJobPayload.model_validate(job.payload)
    backend = await resolve_txt2img_backend(request.backend)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.TXT2IMG,
            refined_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            target_tool="comfyui_txt2img_v1",
            params={"seed": request.seed, "steps": request.steps},
        ),
        {"backend": backend},
    )
    return await _persist_pipeline_result(
        job,
        task,
        await _wait_for_pipeline(job, task, repository),
        repository,
    )


async def _inpaint_handler(job: JobRecord, repository: JobRepository) -> dict[str, Any]:
    request = InpaintJobPayload.model_validate(job.payload)
    image = await _read_artifact(job, str(request.image.artifact_id), repository)
    mask = await _read_artifact(job, str(request.mask.artifact_id), repository)
    backend = await resolve_inpaint_backend(request.backend)
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.INPAINT,
            refined_prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            target_tool="comfyui_inpaint_v1",
            params={"seed": request.seed, "steps": request.steps},
        ),
        {
            "backend": backend,
            "image_bytes": image[1],
            "mask_bytes": mask[1],
            "image_media_type": image[0].media_type,
            "mask_media_type": mask[0].media_type,
        },
    )
    return await _persist_pipeline_result(
        job,
        task,
        await _wait_for_pipeline(job, task, repository),
        repository,
    )


async def _decompose_handler(job: JobRecord, repository: JobRepository) -> dict[str, Any]:
    request = DecomposeJobPayload.model_validate(job.payload)
    _, image_bytes = await _read_artifact(
        job, str(request.image.artifact_id), repository
    )
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.DECOMPOSE,
            refined_prompt=request.background_prompt,
            negative_prompt=request.negative_prompt,
            target_tool="comfyui_decompose_v1",
        ),
        {"image_bytes": image_bytes},
    )
    return await _persist_pipeline_result(
        job,
        task,
        await _wait_for_pipeline(job, task, repository),
        repository,
    )


async def _text_edit_handler(job: JobRecord, repository: JobRepository) -> dict[str, Any]:
    request = TextEditJobPayload.model_validate(job.payload)
    _, image_bytes = await _read_artifact(
        job, str(request.image.artifact_id), repository
    )
    task = await execute_plan(
        IntentPlan(
            intent=IntentType.TEXT_EDIT,
            refined_prompt=request.inpaint_prompt,
            negative_prompt=request.negative_prompt,
            target_tool="comfyui_text_edit_v1",
        ),
        {
            "image_bytes": image_bytes,
            "bbox_json": str(request.bbox).replace(" ", ""),
            "new_text": request.new_text,
        },
    )
    return await _persist_pipeline_result(
        job,
        task,
        await _wait_for_pipeline(job, task, repository),
        repository,
    )


async def _wait_for_pipeline(
    job: JobRecord,
    task: TaskState,
    repository: JobRepository,
) -> dict[str, Any]:
    while True:
        await _ensure_active(job, repository)
        try:
            event = await asyncio.wait_for(task.events.get(), timeout=1.0)
        except TimeoutError:
            continue
        event_type = event.get("type")
        if event_type == "complete":
            return event
        if event_type == "error":
            raise RuntimeError(str(event.get("message", "generation failed")))


async def _read_artifact(
    job: JobRecord,
    artifact_id: str,
    repository: JobRepository,
) -> tuple[ArtifactRecord, bytes]:
    await _ensure_active(job, repository)
    found = await get_artifact_service().read_owned(artifact_id, job.owner_key_id)
    if found is None:
        raise ValueError("input artifact not found")
    await _ensure_active(job, repository)
    return found


async def _persist_pipeline_result(
    job: JobRecord,
    task: TaskState,
    event: dict[str, Any],
    repository: JobRepository,
) -> dict[str, Any]:
    await _ensure_active(job, repository)
    paths = _output_paths(task, event)
    artifacts: list[ArtifactResponse] = []
    for path in paths:
        await _ensure_active(job, repository)
        artifacts.append(
            await get_artifact_service().create_output(
                job.owner_key_id,
                job.id,
                path,
            )
        )
    if not artifacts:
        raise RuntimeError("pipeline completed without a local output")
    result: dict[str, Any] = {
        "primary_artifact": artifacts[0].model_dump(mode="json"),
        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
    }
    if "overlay" in event:
        result["overlay"] = event["overlay"]
    return result


def _output_paths(task: TaskState, event: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    if task.image_path is not None:
        paths.append(task.image_path)
    for layer in event.get("layers", []):
        image_url = layer.get("image_url") if isinstance(layer, dict) else None
        if not isinstance(image_url, str):
            continue
        candidate = (settings.outputs_dir / Path(image_url).name).resolve()
        if settings.outputs_dir.resolve() not in candidate.parents:
            continue
        if candidate.is_file() and candidate not in paths:
            paths.append(candidate)
    return paths


async def _ensure_active(job: JobRecord, repository: JobRepository) -> None:
    current = await repository.get(job.id, job.owner_key_id)
    if current is None or current.cancel_requested:
        raise JobCancellation("job cancellation requested")


JOB_HANDLERS: dict[str, JobHandler] = {
    "agent_route": _route_handler,
    "txt2img": _txt2img_handler,
    "inpaint": _inpaint_handler,
    "decompose": _decompose_handler,
    "text_edit": _text_edit_handler,
}


async def execute_job(_context: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Execute one leased job and persist all terminal/retry transitions."""
    repository = get_job_repository()
    started = time.perf_counter()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    job = await repository.acquire(job_id, worker_id)
    if job.status == JobStatus.CANCELLED:
        return {"status": job.status.value}
    handler = JOB_HANDLERS.get(job.kind)
    if handler is None:
        error = {"code": "unsupported_job_kind", "message": job.kind}
        finished = await repository.finish(job.id, error=error)
        if finished.status == JobStatus.RETRYING:
            raise Retry(defer=5)
        return {"status": finished.status.value}

    async def run() -> dict[str, Any]:
        if job.queue == settings.queue_gpu:
            async with _gpu_slots:
                return await handler(job, repository)
        return await handler(job, repository)

    try:
        result = await asyncio.wait_for(run(), timeout=job.timeout_seconds)
        await _record_agent_provider(job, started, result=result)
    except asyncio.CancelledError:
        await _try_record_agent_provider(job, started, error_code="worker_cancelled")
        await repository.finish(
            job.id, error={"code": "worker_cancelled", "message": "worker cancelled"}
        )
        raise
    except TimeoutError:
        await _try_record_agent_provider(job, started, error_code="timeout")
        finished = await repository.finish(
            job.id, error={"code": "timeout", "message": "job execution timed out"}
        )
        if finished.status == JobStatus.RETRYING:
            raise Retry(defer=min(2**job.attempts, 60))
        return {"status": finished.status.value}
    except Exception as exc:
        await _try_record_agent_provider(
            job,
            started,
            error_code=type(exc).__name__,
        )
        finished = await repository.finish(
            job.id,
            error={"code": type(exc).__name__, "message": str(exc)[:500]},
        )
        if finished.status == JobStatus.RETRYING:
            raise Retry(defer=min(2**job.attempts, 60))
        return {"status": finished.status.value}
    finished = await repository.finish(job.id, result=result)
    return {"status": finished.status.value, "result": result}


async def _record_agent_provider(
    job: JobRecord,
    started: float,
    *,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
) -> None:
    if job.kind != "agent_route" or job.payload.get("intent_override") is not None:
        return
    fallback = bool(
        result
        and str(result.get("reasoning", "")).startswith("provider unavailable")
    )
    from app.agent.providers import intent_model_name

    provider = settings.llm_provider
    model = intent_model_name(settings)
    success = error_code is None and not fallback
    await record_provider_call(
        ProviderCallEvent(
            job_id=job.id,
            provider=provider,
            model=model,
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            success=success,
            status_code=200 if success else None,
            error_code=error_code or ("provider_unavailable" if fallback else None),
        )
    )


async def _try_record_agent_provider(
    job: JobRecord,
    started: float,
    *,
    error_code: str,
) -> None:
    try:
        await _record_agent_provider(job, started, error_code=error_code)
    except Exception:
        # Preserve the job state transition if telemetry storage is unavailable.
        return


class WorkerSettings:
    """arq worker configuration.

    Run one worker process per queue using ``INFD_WORKER_QUEUE``. GPU process
    concurrency is additionally capped by ``INFD_GPU_CONCURRENCY``.
    """

    functions = [execute_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url or "redis://127.0.0.1:6379")
    queue_name = os.getenv("INFD_WORKER_QUEUE", settings.queue_api)
    max_jobs = settings.gpu_concurrency if queue_name == settings.queue_gpu else 10
    job_timeout = settings.job_timeout_seconds
    keep_result = 3600
