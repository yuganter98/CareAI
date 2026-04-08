"""
AgentLogger — Non-blocking async observability service for the CareAI multi-agent pipeline.

Design principles:
- Fire-and-forget: never raises, never blocks the main workflow
- Uses its own scoped DB session (independent of the request session)
- Returns timing via context manager so callers get duration_ms for free
- Emits real-time WebSocket events to connected frontends
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from app.db.session import async_session_maker
from app.db.models import AgentLog
from app.realtime.connection_manager import ws_manager

logger = logging.getLogger(__name__)


async def _write_log(
    report_id: str,
    agent_name: str,
    status: str,
    message: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """Internal coroutine: writes a single log row using its own DB session."""
    try:
        async with async_session_maker() as session:
            log_entry = AgentLog(
                report_id=uuid.UUID(report_id),
                agent_name=agent_name,
                status=status,
                message=message,
                duration_ms=duration_ms,
                timestamp=datetime.utcnow(),
            )
            session.add(log_entry)
            await session.commit()
    except Exception as exc:
        logger.warning("[AgentLogger] DB write failed for %s: %s", agent_name, exc)


async def _emit_ws_event(
    report_id: str,
    agent_name: str,
    status: str,
    message: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """Push a real-time event to all WebSocket subscribers for this report."""
    try:
        await ws_manager.broadcast(report_id, {
            "type": "agent_event",
            "agent": agent_name,
            "status": status,
            "message": message,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as exc:
        logger.warning("[AgentLogger] WS broadcast failed for %s: %s", agent_name, exc)


def log_agent(
    report_id: str,
    agent_name: str,
    status: str,
    message: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """
    Public fire-and-forget entry point.
    Schedules both the DB write AND the WebSocket broadcast as background tasks.
    Calling code does NOT need to await this.
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_write_log(report_id, agent_name, status, message, duration_ms))
        loop.create_task(_emit_ws_event(report_id, agent_name, status, message, duration_ms))
    except RuntimeError:
        # No running loop — fallback (shouldn't happen under FastAPI)
        asyncio.run(_write_log(report_id, agent_name, status, message, duration_ms))


@asynccontextmanager
async def observe_agent(
    report_id: str,
    agent_name: str,
) -> AsyncGenerator[None, None]:
    """
    Async context manager for clean agent instrumentation.

    Usage:
        async with observe_agent(report_id, "ReportAnalyzerAgent"):
            state = await agent.run(state)

    Lifecycle:
        1. Emits 'started' event (DB + WS)
        2. Yields control to the caller
        3. On success: emits 'completed' with duration_ms
        4. On failure: emits 'failed' with error message, then re-raises
    """
    start = time.monotonic()
    log_agent(report_id, agent_name, "started")
    try:
        yield
        elapsed = round((time.monotonic() - start) * 1000, 2)
        log_agent(report_id, agent_name, "completed", duration_ms=elapsed)
    except Exception as exc:
        elapsed = round((time.monotonic() - start) * 1000, 2)
        log_agent(report_id, agent_name, "failed", message=str(exc), duration_ms=elapsed)
        raise  # Always re-raise — observability is transparent
