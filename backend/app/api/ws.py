"""Owner-bound, process-local compatibility WebSocket for generate tasks.

The durable Jobs API SSE stream is the recommended production integration.
This endpoint remains available for the existing same-origin frontend proxy
when API and WebSocket traffic reach the same backend process.
"""

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.pipeline.executor import task_manager
from app.production.auth import current_principal

router = APIRouter(tags=["ws"])

_TERMINAL_EVENT_TYPES = {"complete", "error"}


@router.websocket("/ws")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    try:
        principal = await current_principal(websocket.headers.get("X-API-Key"))
    except HTTPException:
        await websocket.close(code=4401)
        return
    allowed_scopes = {"generate", "jobs:read"}
    if "*" not in principal.scopes and principal.scopes.isdisjoint(allowed_scopes):
        await websocket.close(code=4403)
        return
    task = task_manager.get(task_id)
    if task is None or task.owner_key_id != principal.key_id:
        # Use the same response for absent and foreign tasks to avoid existence disclosure.
        await websocket.close(code=4404)
        return
    await websocket.accept()

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
