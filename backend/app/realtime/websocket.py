"""
WebSocket endpoint: /ws/agents/{report_id}

Protocol:
  1. Client connects → registered in ConnectionManager
  2. Server pushes agent events as JSON frames
  3. Client may send "ping" → server replies "pong" (keep-alive)
  4. On disconnect → cleanly unregistered

No authentication on the WS itself (the report_id is opaque and short-lived).
Production hardening: add token validation in the handshake if needed.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.connection_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agents/{report_id}")
async def agent_events_ws(ws: WebSocket, report_id: str):
    await ws.accept()
    ws_manager.connect(report_id, ws)
    logger.info("[WS] Handshake accepted for report_id=%s", report_id)

    try:
        while True:
            # Block until client sends a message or disconnects.
            # We use this to keep the connection alive and handle pings.
            data = await ws.receive_text()
            if data.strip().lower() == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected cleanly for report_id=%s", report_id)
    except Exception as exc:
        logger.warning("[WS] Connection error for report_id=%s: %s", report_id, exc)
    finally:
        ws_manager.disconnect(report_id, ws)
