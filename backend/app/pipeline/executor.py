"""Task state, unified event contract, and shared ComfyUI orchestration.

Every pipeline (single-workflow or multi-step) runs through
:func:`start_pipeline_task`, which owns TaskState creation and error
handling, and emits events with a single envelope:

    {"type": "progress", "task_id": ..., "step": ...}
    {"type": "complete", "task_id": ..., "image_url": ..., ...extras}
    {"type": "error",    "task_id": ..., "message": ...}
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.pipeline.comfyui_client import ComfyUIClient

MAX_RETAINED_TASKS = 100


@dataclass
class TaskState:
    task_id: str
    prompt_id: str
    owner_key_id: str | None = None
    status: str = "queued"
    image_path: Path | None = None
    error: str | None = None
    last_event: dict[str, Any] | None = None
    events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)

    async def emit(self, payload: dict[str, Any]) -> None:
        """Publish a task event and retain the latest payload for WS reconnect."""
        self.last_event = payload
        await self.events.put(payload)

    async def emit_progress(self, step: str) -> None:
        self.status = "running"
        await self.emit({"type": "progress", "task_id": self.task_id, "step": step})

    async def emit_complete(self, image_url: str, **extra: Any) -> None:
        self.status = "complete"
        await self.emit(
            {"type": "complete", "task_id": self.task_id, "image_url": image_url, **extra}
        )

    async def emit_error(self, message: str) -> None:
        self.status = "error"
        self.error = message
        await self.emit({"type": "error", "task_id": self.task_id, "message": message})

    @property
    def is_terminal(self) -> bool:
        """Return True when the task has completed or failed."""
        return self.status in {"complete", "error"}


class TaskManager:
    def __init__(self, max_retained: int = MAX_RETAINED_TASKS) -> None:
        self._tasks: dict[str, TaskState] = {}
        self._max_retained = max_retained

    def create(self, prompt_id: str, owner_key_id: str | None = None) -> TaskState:
        """Create and register a process-local task."""
        task = TaskState(
            task_id=str(uuid.uuid4()),
            prompt_id=prompt_id,
            owner_key_id=owner_key_id,
        )
        self.register(task)
        return task

    def get(self, task_id: str) -> TaskState | None:
        return self._tasks.get(task_id)

    def bind_owner(self, task_id: str, owner_key_id: str) -> TaskState:
        """Bind a task to one API principal without allowing reassignment."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.owner_key_id not in {None, owner_key_id}:
            raise ValueError("task owner is already bound")
        task.owner_key_id = owner_key_id
        return task

    def register(self, task: TaskState) -> None:
        self._evict_terminal()
        self._tasks[task.task_id] = task

    def _evict_terminal(self) -> None:
        """Drop oldest finished tasks once the retention cap is exceeded."""
        overflow = len(self._tasks) - self._max_retained + 1
        if overflow <= 0:
            return
        for task_id in [tid for tid, t in self._tasks.items() if t.is_terminal][:overflow]:
            del self._tasks[task_id]


task_manager = TaskManager()

PipelineFn = Callable[[TaskState], Awaitable[None]]


def start_pipeline_task(prompt_id: str, pipeline: PipelineFn) -> TaskState:
    """Register a task and run `pipeline(task)` in the background.

    The pipeline body only emits progress/complete; failures are funneled
    into a single error event here.
    """
    task = task_manager.create(prompt_id)

    async def _run() -> None:
        try:
            await pipeline(task)
        except Exception as exc:
            await task.emit_error(str(exc))

    asyncio.create_task(_run())
    return task


async def wait_comfyui_output(
    client: ComfyUIClient,
    prompt_id: str,
    outputs_dir: Path,
    *,
    timeout: float = 300.0,
    poll_interval: float = 2.0,
) -> Path:
    """Poll ComfyUI history until the prompt's output image lands in outputs_dir."""
    elapsed = 0.0
    while elapsed < timeout:
        history = await client.get_history(prompt_id)
        if prompt_id in history:
            copied = await client.copy_output_image(prompt_id, outputs_dir)
            if copied:
                return copied
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError("ComfyUI task timed out")


async def inpaint_image_files(
    image_path: Path,
    mask_path: Path,
    *,
    prompt: str,
    negative_prompt: str,
    outputs_dir: Path,
) -> Path:
    """Upload image+mask, run the inpaint workflow, and wait for the output."""
    client = ComfyUIClient()
    image_name = await client.upload_image(image_path)
    mask_name = await client.upload_image(mask_path)
    workflow = client.build_inpaint_workflow(
        image_name=image_name,
        mask_name=mask_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
    prompt_id = await client.queue_prompt(workflow)
    return await wait_comfyui_output(client, prompt_id, outputs_dir)


async def run_comfyui_task(
    *,
    workflow: dict,
    outputs_dir: Path,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> TaskState:
    """Queue a prepared workflow and track it as a single-step task."""
    client = ComfyUIClient()
    prompt_id = await client.queue_prompt(workflow, client_id=str(uuid.uuid4()))

    async def _pipeline(task: TaskState) -> None:
        await task.emit_progress("generating")
        copied = await wait_comfyui_output(
            client, prompt_id, outputs_dir, timeout=timeout, poll_interval=poll_interval
        )
        task.image_path = copied
        await task.emit_complete(f"/api/v1/files/outputs/{copied.name}")

    return start_pipeline_task(prompt_id, _pipeline)
