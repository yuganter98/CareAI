"""
Health Copilot Engine — Cross-report RAG + trends + insights for personalized chat.

Architecture:
  1. Searches FAISS across ALL of the user's reports (no filter_report_id)
  2. Pulls the latest HealthMetric rows from Postgres for trend context
  3. Builds a rich system prompt combining RAG chunks + metric trends
  4. Sends to LLM for a warm, context-aware, personalized answer
  5. Appends non-medical disclaimer to every response
"""

import json
import logging
import uuid
from typing import Dict, Any, List

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.config import settings
from app.db.models import HealthMetric, Report
from app.agents.rag_pipeline import search_similar_chunks

logger = logging.getLogger(__name__)

# Shared LLM client
try:
    _client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or "lm-studio",
        base_url=settings.OPENAI_API_BASE or "http://localhost:1234/v1",
    )
except Exception as e:
    logger.error("Copilot LLM client init failed: %s", e)
    _client = None

DISCLAIMER = (
    "\n\n---\n"
    "⚕️ *Disclaimer: This is AI-generated health guidance based on your uploaded reports. "
    "It is NOT a substitute for professional medical advice, diagnosis, or treatment. "
    "Always consult your doctor for clinical decisions.*"
)


async def _get_user_report_ids(db: AsyncSession, user_id: str) -> List[str]:
    """Fetch all report IDs belonging to the user."""
    result = await db.execute(
        select(Report.id).where(Report.user_id == uuid.UUID(user_id))
    )
    return [str(r) for r in result.scalars().all()]


async def _get_trend_context(db: AsyncSession, user_id: str) -> str:
    """Build a structured text block summarising the latest metric trends."""
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == uuid.UUID(user_id))
        .order_by(HealthMetric.recorded_at.desc())
        .limit(50)  # Cap to avoid context overflow
    )
    metrics = result.scalars().all()

    if not metrics:
        return "No historical health metrics available yet."

    # Group by metric name, show latest N readings
    grouped: Dict[str, list] = {}
    for m in metrics:
        if m.metric_name not in grouped:
            grouped[m.metric_name] = []
        if len(grouped[m.metric_name]) < 5:  # max 5 readings per metric
            grouped[m.metric_name].append({
                "value": m.metric_value,
                "unit": m.unit or "",
                "date": m.recorded_at.strftime("%Y-%m-%d") if m.recorded_at else "unknown",
            })

    lines = ["PATIENT HEALTH TRENDS (latest readings, most recent first):"]
    for name, readings in grouped.items():
        vals = ", ".join([f"{r['value']} {r['unit']} ({r['date']})" for r in readings])
        lines.append(f"  • {name}: {vals}")

    return "\n".join(lines)


def _get_rag_context(question: str, user_report_ids: List[str]) -> str:
    """Search FAISS across ALL of the user's reports."""
    # Search without filter to get cross-report context
    all_chunks = search_similar_chunks(query=question, top_k=8, filter_report_id=None)

    # Post-filter: only keep chunks belonging to the user's reports
    user_chunks = [c for c in all_chunks if c.get("report_id") in user_report_ids]

    if not user_chunks:
        return "No relevant medical report context found for this question."

    chunks_text = "\n\n---\n\n".join([c["chunk"] for c in user_chunks[:5]])
    return f"RELEVANT MEDICAL REPORT EXCERPTS:\n{chunks_text}"


async def copilot_chat(
    db: AsyncSession,
    user_id: str,
    question: str,
    conversation_history: List[Dict[str, str]] | None = None,
) -> str:
    """
    Main Copilot entrypoint.
    Combines cross-report RAG + metric trends into a single LLM call.
    """
    if not _client:
        raise ValueError("LLM client not available. Check your OPENAI_API_KEY.")

    # 1. Get user's report IDs for scoping
    report_ids = await _get_user_report_ids(db, user_id)

    # 2. Pull RAG context (cross-report)
    rag_context = _get_rag_context(question, report_ids)

    # 3. Pull metric trend context
    trend_context = await _get_trend_context(db, user_id)

    # 4. Build system prompt
    system_prompt = (
        "You are CareAI Health Copilot — a warm, knowledgeable health assistant. "
        "You have access to the patient's COMPLETE medical history across all their uploaded reports "
        "and their longitudinal health metric trends.\n\n"
        "RULES:\n"
        "1. Answer the patient's question using the context provided below.\n"
        "2. Be specific — reference actual values, dates, and trends from their data.\n"
        "3. Give personalized, actionable guidance in simple language.\n"
        "4. If something looks concerning, recommend they consult their doctor.\n"
        "5. NEVER fabricate data that isn't in the provided context.\n"
        "6. Keep answers concise but thorough (3-6 paragraphs max).\n\n"
        f"{rag_context}\n\n"
        f"{trend_context}\n"
    )

    # 5. Build messages with optional conversation history
    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-6:]:  # Keep last 6 turns to fit context
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

    messages.append({"role": "user", "content": question})

    # 6. Call LLM
    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
        )
        answer = (response.choices[0].message.content or "").strip()
        return answer + DISCLAIMER
    except Exception as e:
        logger.error("Copilot LLM call failed: %s", e)
        raise ValueError(f"Health Copilot failed to generate a response: {e}")
