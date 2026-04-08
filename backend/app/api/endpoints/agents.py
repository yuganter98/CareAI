from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import asc
from typing import List, Dict, Any
import uuid

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Report, AgentLog

router = APIRouter()


@router.get("/logs/{report_id}", response_model=List[Dict[str, Any]])
async def get_agent_logs(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns the full ordered execution log for a single report's agent pipeline.
    Enforces ownership — users can only view logs for their own reports.
    """
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")

    # Enforce ownership before exposing telemetry
    result = await db.execute(
        select(Report).where(Report.id == report_uuid, Report.user_id == current_user.id)
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Report not found or access denied.")

    logs_result = await db.execute(
        select(AgentLog)
        .where(AgentLog.report_id == report_uuid)
        .order_by(asc(AgentLog.timestamp))
    )
    logs = logs_result.scalars().all()

    return [
        {
            "id": str(log.id),
            "agent_name": log.agent_name,
            "status": log.status,
            "message": log.message,
            "duration_ms": log.duration_ms,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
