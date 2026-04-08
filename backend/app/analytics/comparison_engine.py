from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import HealthMetric
import uuid

def calculate_change(current: float, previous: float) -> str:
    """Calculates the percentage change correctly between two floats."""
    if previous == 0:
        return "+0.00%" if current == 0 else "N/A"
    
    change = ((current - previous) / previous) * 100
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.2f}%"

def evaluate_trend_status(metric_name: str, previous: float, current: float) -> str:
    """
    Very basic hardcoded rule-set to determine if a recorded trend is 'worsening', 'improving', or 'stable'.
    """
    if previous == current:
        return "stable"
        
    diff = current - previous
    
    # Simple medical heuristics defining which metrics are harmful when elevated vs dropped
    worse_if_up = ["glucose", "creatinine", "blood_pressure_systolic", "blood_pressure_diastolic", "ldl", "cholesterol"]
    worse_if_down = ["hemoglobin", "hdl"]
    
    if metric_name in worse_if_up:
        return "worsening" if diff > 0 else "improving"
    elif metric_name in worse_if_down:
        return "worsening" if diff < 0 else "improving"
    
    # Default fallback
    return "changed"

async def compare_report_metrics(db: AsyncSession, report_id: str, user_id: str) -> Dict[str, Any]:
    """
    Compares metrics of the given report_id against the temporally PREVIOUS metrics for the user.
    """
    report_uuid = uuid.UUID(report_id)
    user_uuid = uuid.UUID(user_id)
    
    # 1. Fetch metrics assigned solely to the target latest report
    current_result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.report_id == report_uuid, HealthMetric.user_id == user_uuid)
    )
    current_metrics = current_result.scalars().all()
    
    if not current_metrics:
        return {}
        
    # Anchor logic point: grab the creation time to search backwards
    current_time = current_metrics[0].recorded_at
    
    # 2. Extract the patient's entire historical timeline *prior* to this specific report
    previous_result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == user_uuid, HealthMetric.recorded_at < current_time)
        .order_by(HealthMetric.recorded_at.desc())
    )
    all_previous_metrics = previous_result.scalars().all()
    
    # Collate latest historical instances per metric_name grouping
    latest_previous = {}
    for pm in all_previous_metrics:
        if pm.metric_name not in latest_previous:
            latest_previous[pm.metric_name] = pm
            
    # 3. Construct intelligent comparative JSON output
    comparison = {}
    for cm in current_metrics:
        name = cm.metric_name
        curr_val = cm.metric_value
        
        if name in latest_previous:
            prev_val = latest_previous[name].metric_value
            if curr_val is not None and prev_val is not None:
                comparison[name] = {
                    "previous": prev_val,
                    "current": curr_val,
                    "change": calculate_change(curr_val, prev_val),
                    "status": evaluate_trend_status(name, prev_val, curr_val)
                }
            else:
                comparison[name] = {"current": curr_val, "previous": prev_val, "status": "missing_data"}
        else:
            # Baseline baseline; no existing historical context found for this feature yet!
            comparison[name] = {
                "previous": None,
                "current": curr_val,
                "change": "N/A",
                "status": "new_metric"
            }
            
    return comparison
