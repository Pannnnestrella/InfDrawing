import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.pipeline.executor import task_manager

router = APIRouter(tags=["ws"])

_TERMINAL_EVENT_TYPES = {"complete", "error"}


@router.websocket("/ws")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    task = task_manager.get(task_id)
    if task is None:
        await websocket.send_json({"type": "error", "message": "unknown task_id"})
        await websocket.close()
        return

    try:
        if task.last_event is not None:
            await websocket.send_json(task.last_event)
            if task.last_event.get("type") in _TERMINAL_EVENT_TYPES:
                return

        while True:
            event = await asyncio.wait_for(task.events.get(), timeout=300.0)
            await websocket.send_json(event)
            if event.get("type") in _TERMINAL_EVENT_TYPES:
                break
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close()
