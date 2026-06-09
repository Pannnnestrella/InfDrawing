import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.pipeline.executor import task_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    task = task_manager.get(task_id)
    if task is None:
        await websocket.send_json({"type": "error", "message": "unknown task_id"})
        await websocket.close()
        return

    try:
        while True:
            event = await asyncio.wait_for(task.events.get(), timeout=300.0)
            await websocket.send_json(event)
            if event.get("type") in {"complete", "error"}:
                break
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close()
