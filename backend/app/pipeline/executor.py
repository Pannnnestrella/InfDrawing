import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.pipeline.comfyui_client import ComfyUIClient


@dataclass
class TaskState:
    task_id: str
    prompt_id: str
    status: str = "queued"
    image_path: Path | None = None
    error: str | None = None
    last_event: dict[str, Any] | None = None
    events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)

    async def emit(self, payload: dict[str, Any]) -> None:
        """Publish a task event and retain the latest payload for WS reconnect."""
        self.last_event = payload
        await self.events.put(payload)

    @property
    def is_terminal(self) -> bool:
        """Return True when the task has completed or failed."""
        return self.status in {"complete", "error"}


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}

    def create(self, prompt_id: str) -> TaskState:
        task = TaskState(task_id=str(uuid.uuid4()), prompt_id=prompt_id)
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> TaskState | None:
        return self._tasks.get(task_id)

    def register(self, task: TaskState) -> None:
        self._tasks[task.task_id] = task


task_manager = TaskManager()


async def run_comfyui_task(
    *,
    workflow: dict,
    outputs_dir: Path,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
) -> TaskState:
    client = ComfyUIClient()
    client_id = str(uuid.uuid4())
    prompt_id = await client.queue_prompt(workflow, client_id=client_id)
    task = task_manager.create(prompt_id)

    async def _poll() -> None:
        elapsed = 0.0
        task.status = "running"
        await task.emit({"type": "progress", "task_id": task.task_id, "status": "running"})
        while elapsed < timeout:
            history = await client.get_history(prompt_id)
            if prompt_id in history:
                copied = await client.copy_output_image(prompt_id, outputs_dir)
                if copied:
                    task.image_path = copied
                    task.status = "complete"
                    await task.emit(
                        {
                            "type": "complete",
                            "task_id": task.task_id,
                            "image_url": f"/api/v1/files/outputs/{copied.name}",
                        }
                    )
                    return
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        task.status = "error"
        task.error = "timeout"
        await task.emit(
            {"type": "error", "task_id": task.task_id, "message": "ComfyUI task timed out"}
        )

    asyncio.create_task(_poll())
    return task
