from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gateway.auth import credential_ok
from gateway.state import state

router = APIRouter()

PING_INTERVAL = 25


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = "") -> None:
    if not await credential_ok(token):
        await ws.close(code=4401)
        return

    await ws.accept()
    await state.hub.add(ws)
    await ws.send_json({"type": "hello", "service": "gateway"})

    async def pinger() -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await ws.send_json({"type": "ping"})

    ping_task = asyncio.create_task(pinger())
    try:
        while True:
            # Inbound messages are only pongs/keepalives; ignore content.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ping_task
        await state.hub.remove(ws)
