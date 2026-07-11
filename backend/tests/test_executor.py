"""Tests for the unified task runner: emit helpers, pipeline wrapper, polling."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.pipeline.executor import (
    TaskManager,
    TaskState,
    start_pipeline_task,
    wait_comfyui_output,
)


def test_emit_helpers_set_status_and_envelope() -> None:
    async def _run() -> None:
        task = TaskState(task_id="t", prompt_id="p")

        await task.emit_progress("segmenting")
        assert task.status == "running"
        assert task.last_event == {"type": "progress", "task_id": "t", "step": "segmenting"}

        await task.emit_complete("/api/v1/files/outputs/x.png", layers=[])
        assert task.status == "complete"
        assert task.last_event is not None
        assert task.last_event["image_url"].endswith("x.png")
        assert task.last_event["layers"] == []

        failed = TaskState(task_id="t2", prompt_id="p")
        await failed.emit_error("boom")
        assert failed.status == "error"
        assert failed.error == "boom"
        assert failed.last_event == {"type": "error", "task_id": "t2", "message": "boom"}

    asyncio.run(_run())


def test_start_pipeline_task_emits_error_on_exception() -> None:
    async def _run() -> None:
        async def _pipeline(task: TaskState) -> None:
            raise RuntimeError("pipeline exploded")

        task = start_pipeline_task("test", _pipeline)
        event = await asyncio.wait_for(task.events.get(), timeout=1.0)
        assert event["type"] == "error"
        assert event["message"] == "pipeline exploded"
        assert task.is_terminal

    asyncio.run(_run())


def test_task_manager_evicts_oldest_terminal_tasks() -> None:
    manager = TaskManager(max_retained=2)
    done_a = TaskState(task_id="a", prompt_id="p", status="complete")
    done_b = TaskState(task_id="b", prompt_id="p", status="error")
    running = TaskState(task_id="c", prompt_id="p", status="running")
    manager.register(done_a)
    manager.register(done_b)
    manager.register(running)

    manager.register(TaskState(task_id="d", prompt_id="p"))

    assert manager.get("a") is None  # oldest terminal evicted first
    assert manager.get("c") is not None  # running tasks are never evicted
    assert manager.get("d") is not None


def test_wait_comfyui_output_returns_copied_path() -> None:
    async def _run() -> None:
        client = AsyncMock()
        client.get_history.return_value = {"pid": {}}
        client.copy_output_image.return_value = Path("out.png")

        result = await wait_comfyui_output(client, "pid", Path("."), poll_interval=0.01)
        assert result == Path("out.png")

    asyncio.run(_run())


def test_wait_comfyui_output_times_out() -> None:
    async def _run() -> None:
        client = AsyncMock()
        client.get_history.return_value = {}

        with pytest.raises(TimeoutError):
            await wait_comfyui_output(
                client, "pid", Path("."), timeout=0.03, poll_interval=0.01
            )

    asyncio.run(_run())
