import asyncio

from app.pipeline.executor import TaskState, task_manager


def test_task_emit_stores_last_event() -> None:
    async def _run() -> None:
        task = TaskState(task_id="task-1", prompt_id="prompt-1")
        await task.emit({"type": "progress", "task_id": "task-1", "status": "running"})
        assert task.last_event == {"type": "progress", "task_id": "task-1", "status": "running"}

    asyncio.run(_run())


def test_task_emit_replay_for_reconnect() -> None:
    async def _run() -> None:
        task = TaskState(task_id="task-2", prompt_id="prompt-2")
        await task.emit({"type": "progress", "task_id": "task-2", "step": "inpainting"})
        await task.emit(
            {
                "type": "complete",
                "task_id": "task-2",
                "image_url": "/api/v1/files/outputs/out.png",
            }
        )

        replay = task.last_event
        assert replay is not None
        assert replay["type"] == "complete"
        assert replay["image_url"].endswith("out.png")

    asyncio.run(_run())


def test_task_is_terminal() -> None:
    running = TaskState(task_id="a", prompt_id="p", status="running")
    complete = TaskState(task_id="b", prompt_id="p", status="complete")
    error = TaskState(task_id="c", prompt_id="p", status="error")

    assert not running.is_terminal
    assert complete.is_terminal
    assert error.is_terminal


def test_task_events_queue_still_delivers() -> None:
    async def _run() -> None:
        task = TaskState(task_id="registered", prompt_id="p")
        task_manager.register(task)
        await task.emit({"type": "progress", "task_id": "registered", "status": "running"})
        received = await asyncio.wait_for(task.events.get(), timeout=1.0)
        assert received["type"] == "progress"

    asyncio.run(_run())
