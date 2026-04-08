"""
ConnectionManager — Thread-safe WebSocket connection registry for CareAI.

Design:
- Connections are bucketed by report_id so we only push events to subscribers
  watching a specific report's pipeline.
- All public methods are sync (no await required) except send helpers,
  making them safe to call from fire-and-forget background tasks.
- Disconnection is idempotent: double-disconnect never raises.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections, bucketed by report_id."""

    def __init__(self) -> None:
        # report_id → set of WebSocket connections
        self._subscriptions: Dict[str, Set[WebSocket]] = defaultdict(set)

    def connect(self, report_id: str, ws: WebSocket) -> None:
        """Register a connection for a specific report's event stream."""
        self._subscriptions[report_id].add(ws)
        logger.info("[WS] Client connected for report_id=%s (total=%d)",
                     report_id, len(self._subscriptions[report_id]))

    def disconnect(self, report_id: str, ws: WebSocket) -> None:
        """Remove a connection. Idempotent — safe to call multiple times."""
        bucket = self._subscriptions.get(report_id)
        if bucket:
            bucket.discard(ws)
            if not bucket:
                del self._subscriptions[report_id]  # GC empty buckets
        logger.info("[WS] Client disconnected for report_id=%s", report_id)

    def subscriber_count(self, report_id: str) -> int:
        return len(self._subscriptions.get(report_id, set()))

    async def broadcast(self, report_id: str, payload: Dict[str, Any]) -> None:
        """
        Push a JSON payload to every WebSocket subscribed to this report_id.
        Dead connections are silently pruned.
        """
        bucket = self._subscriptions.get(report_id)
        if not bucket:
            return  # Nobody listening — short-circuit

        dead: list[WebSocket] = []
        for ws in bucket:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        # Prune broken sockets
        for ws in dead:
            bucket.discard(ws)
            logger.debug("[WS] Pruned dead connection for report_id=%s", report_id)

    def broadcast_sync(self, report_id: str, payload: Dict[str, Any]) -> None:
        """
        Fire-and-forget broadcast — safe to call from synchronous code or
        background tasks that shouldn't await.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.broadcast(report_id, payload))
            else:
                loop.run_until_complete(self.broadcast(report_id, payload))
        except RuntimeError:
            pass  # No event loop — silently skip (tests, CLI, etc.)


# ── Singleton ──────────────────────────────────────────────────────────────────
ws_manager = ConnectionManager()
