"""
Personalized Insights Engine.

Upgrades the basic insights_generator with:
  1. Python-computed trend direction per metric (no LLM needed for this step)
  2. Clinically-grounded reference range checks
  3. User profile awareness (blood_type, name)
  4. Structured LLM recommendations validated by PersonalizedInsightOutput
  5. Safe fallback when the LLM is unavailable
"""

import json
import logging
import uuid
from typing import Dict, List, Any, Optional
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.llm_client import llm, parse_json_block
from app.schemas.ai import PersonalizedInsightOutput, MetricInsight
from app.db.models import HealthMetric, User

logger = logging.getLogger(__name__)

# ── Clinical reference ranges ────────────────────────────────────────────────
# assessment buckets: normal | borderline | elevated | critical
REFERENCE_RANGES: Dict[str, Dict] = {
    "glucose": {
        "normal":     (70,  100),
        "borderline": (100, 126),
        "elevated":   (126, 200),
        "critical":   (200, float("inf")),
        "unit": "mg/dL",
    },
    "hemoglobin": {
        "critical":   (0,   7),
        "elevated":   (7,   11),    # low side reused as "borderline low"
        "borderline": (11,  12),
        "normal":     (12,  17.5),
        "unit": "g/dL",
    },
    "creatinine": {
        "normal":     (0.7, 1.3),
        "borderline": (1.3, 1.8),
        "elevated":   (1.8, 3.0),
        "critical":   (3.0, float("inf")),
        "unit": "mg/dL",
    },
    "blood_pressure_systolic": {
        "normal":     (90,  120),
        "borderline": (120, 130),
        "elevated":   (130, 180),
        "critical":   (180, float("inf")),
        "unit": "mmHg",
    },
    "blood_pressure_diastolic": {
        "normal":     (60,  80),
        "borderline": (80,  90),
        "elevated":   (90,  120),
        "critical":   (120, float("inf")),
        "unit": "mmHg",
    },
}


def _assess(metric_name: str, value: float) -> str:
    """Return the assessment bucket for a given metric value."""
    ranges = REFERENCE_RANGES.get(metric_name.lower())
    if not ranges:
        return "normal"   # unknown metric — assume normal
    for bucket in ("critical", "elevated", "borderline", "normal"):
        lo, hi = ranges.get(bucket, (None, None))
        if lo is not None and lo <= value < hi:
            return bucket
    return "normal"


def _compute_trend(readings: List[float]) -> str:
    """
    Determine trend direction from a time-ordered list of values.
    Uses a simple comparison of the first and last thirds.
    """
    n = len(readings)
    if n < 2:
        return "unknown"
    if n < 4:
        delta = readings[-1] - readings[0]
        if abs(delta) < 0.05 * abs(readings[0] + 1e-9):
            return "stable"
        return "increasing" if delta > 0 else "decreasing"

    third = max(1, n // 3)
    early_avg = sum(readings[:third]) / third
    late_avg  = sum(readings[-third:]) / third
    delta_pct = (late_avg - early_avg) / (abs(early_avg) + 1e-9)

    if delta_pct >  0.05:
        return "increasing"
    if delta_pct < -0.05:
        return "decreasing"
    return "stable"


async def _fetch_metrics(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, List]:
    """Return metrics grouped by name, ordered chronologically."""
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == user_id)
        .order_by(HealthMetric.recorded_at.asc())
    )
    all_metrics = result.scalars().all()

    grouped: Dict[str, List] = {}
    for m in all_metrics:
        grouped.setdefault(m.metric_name, []).append({
            "value": m.metric_value,
            "unit":  m.unit or "",
            "date":  m.recorded_at.strftime("%Y-%m-%d") if m.recorded_at else "unknown",
        })
    return grouped


def _build_metric_insights(grouped: Dict[str, List]) -> List[MetricInsight]:
    """Python-computed MetricInsight objects — no LLM needed for this step."""
    insights: List[MetricInsight] = []
    for name, readings in grouped.items():
        values = [r["value"] for r in readings if r["value"] is not None]
        if not values:
            continue

        current   = values[-1]
        unit      = readings[-1].get("unit", "")
        trend     = _compute_trend(values)
        assessment = _assess(name, current)

        # Simple rule-based recommendation per assessment
        rec_map = {
            "normal":     "Values are within healthy range. Maintain your current lifestyle.",
            "borderline": "Values are borderline. Monitor closely and consult your doctor.",
            "elevated":   f"{name.replace('_', ' ').title()} is elevated. Schedule a medical review.",
            "critical":   f"CRITICAL: {name.replace('_', ' ').title()} requires immediate medical attention.",
        }
        recommendation = rec_map.get(assessment, "Consult your doctor.")

        insights.append(MetricInsight(
            metric=name,
            trend=trend,
            current_value=current,
            unit=unit,
            assessment=assessment,
            recommendation=recommendation,
        ))
    return insights


async def generate_personalized_insights(
    db: AsyncSession,
    user_id: str,
) -> Dict[str, Any]:
    """
    Main entry point.

    Returns a PersonalizedInsightOutput dict combining:
    - Python-computed per-metric trend + assessment
    - LLM-generated narrative insights (with Pydantic validation + fallback)
    """
    user_uuid = uuid.UUID(user_id)

    # ── 1. Pull user profile for personalisation ──────────────────────────────
    user_result = await db.execute(select(User).where(User.id == user_uuid))
    user: Optional[User] = user_result.scalars().first()
    user_name = getattr(user, "name", "Patient")

    # ── 2. Pull historical metrics ────────────────────────────────────────────
    grouped = await _fetch_metrics(db, user_uuid)

    if not grouped:
        return PersonalizedInsightOutput(
            insights=["No historical health data available yet. Upload a report to get started."],
            summary="No data.",
        ).model_dump()

    # ── 3. Python-compute per-metric insights (no LLM) ───────────────────────
    metric_insights = _build_metric_insights(grouped)

    # ── 4. Build structured context for the LLM ──────────────────────────────
    metric_summary_lines = []
    for mi in metric_insights:
        metric_summary_lines.append(
            f"- {mi.metric}: latest={mi.current_value} {mi.unit}, "
            f"trend={mi.trend}, assessment={mi.assessment}"
        )
    metric_context = "\n".join(metric_summary_lines)

    # ── 5. LLM narrative generation ───────────────────────────────────────────
    system_prompt = (
        f"You are CareAI, a personalised health advisor talking to {user_name}.\n"
        "Based on the structured metric analysis below, generate a JSON object with:\n"
        '  "insights": [array of 3-5 concise, actionable insight strings]\n'
        '  "summary": "One warm sentence summarising the overall health picture"\n\n'
        "Rules:\n"
        "- Reference specific metric names and trends.\n"
        "- Be encouraging but honest about elevated or critical values.\n"
        "- Use plain, non-technical language.\n"
        "- Return ONLY raw JSON. No markdown.\n\n"
        f"Metric Analysis:\n{metric_context}"
    )

    insights_list: List[str] = []
    summary: str = ""

    if llm:
        try:
            response = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.3,
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(parse_json_block(raw))

            validated = PersonalizedInsightOutput.model_validate({
                "insights": parsed.get("insights", []),
                "summary":  parsed.get("summary", ""),
                "metrics":  [m.model_dump() for m in metric_insights],
            })
            return validated.model_dump()

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Personalized insights LLM output invalid (%s) — using fallback.", e)
        except Exception as e:
            logger.error("Personalized insights LLM call failed (%s) — using fallback.", e)

    # ── 6. Fallback: build insights from metric_insights without LLM ──────────
    for mi in metric_insights:
        if mi.assessment in ("elevated", "critical"):
            insights_list.append(
                f"Your {mi.metric.replace('_', ' ')} is {mi.assessment} "
                f"({mi.current_value} {mi.unit}, trend: {mi.trend}). {mi.recommendation}"
            )
        elif mi.trend in ("increasing", "decreasing"):
            insights_list.append(
                f"Your {mi.metric.replace('_', ' ')} is {mi.trend} "
                f"(currently {mi.current_value} {mi.unit}). Monitor this over time."
            )

    if not insights_list:
        insights_list = ["All tracked metrics appear within healthy ranges. Keep it up!"]

    elevated = [m for m in metric_insights if m.assessment in ("elevated", "critical")]
    summary = (
        f"{len(elevated)} metric(s) need attention."
        if elevated else "Overall health metrics look stable."
    )

    return PersonalizedInsightOutput(
        insights=insights_list,
        metrics=metric_insights,
        summary=summary,
    ).model_dump()
