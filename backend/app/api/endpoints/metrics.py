from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, List, Any
import uuid
from collections import defaultdict

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, HealthMetric

router = APIRouter()

@router.get("/trends", response_model=Dict[str, List[Dict[str, Any]]])
async def get_metrics_trends(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns time-series data formatted explicitly for Highcharts/Chart.js frontends.
    Aggregates all values mapped strictly by their chronological dates.
    """
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == current_user.id)
        .order_by(HealthMetric.recorded_at.asc())
    )
    all_metrics = result.scalars().all()
    
    # Structure: {"glucose": [{"date": "...", "value": 110}, ...]}
    trends = defaultdict(list)
    
    for metric in all_metrics:
        if metric.metric_value is not None:
            # Include time to prevent duplicate labels causing Recharts Tooltip bugs
            date_str = metric.recorded_at.strftime("%b %d, %H:%M")
            trends[metric.metric_name].append({
                "date": date_str,
                "value": metric.metric_value,
                "unit": metric.unit
            })
            
    return dict(trends)

@router.get("/{report_id}")
async def get_report_metrics(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetches raw un-modified structured DB metrics mapped strictly to a target report.
    """
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id constraint format.")
        
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.report_id == report_uuid, HealthMetric.user_id == current_user.id)
    )
    metrics = result.scalars().all()
    return metrics
