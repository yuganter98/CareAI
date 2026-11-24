"""
WebSocket endpoint: /ws/agents/{report_id}

Protocol:
  1. Client connects with its careai_token httpOnly cookie (sent automatically
     by the browser on the handshake).
  2. Server validates the token and checks the report belongs to that user.
     Unauthenticated or non-owner handshakes are rejected (policy violation, 1008).
  3. Server pushes agent events as JSON frames.
  4. Client may send "ping" → server replies "pong" (keep-alive).
  5. On disconnect → cleanly unregistered.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_report, resolve_user_from_token
from app.db.session import get_db
from app.realtime.connection_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agents/{report_id}")
async def agent_events_ws(ws: WebSocket, report_id: str, db: AsyncSession = Depends(get_db)):
    # ── Authenticate + authorise before accepting the handshake ──
    try:
        user = await resolve_user_from_token(db, ws.cookies.get("careai_token"))
        await get_owned_report(db, report_id, user)
    except HTTPException as exc:
        logger.info("[WS] Rejected handshake for report_id=%s: %s", report_id, exc.detail)
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    finally:
        # Release the pooled DB connection — the socket may stay open for minutes.
        await db.close()

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
