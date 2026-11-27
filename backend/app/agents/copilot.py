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

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.config import settings
from app.db.models import HealthMetric, Report
from app.agents.rag_pipeline import search_similar_chunks
from app.agents.llm_client import complete, llm
from app.core.disclaimer import with_disclaimer
from app.core.redaction import redact
from app.agents.safety import scrub_text

logger = logging.getLogger(__name__)


# The disclaimer now lives in app/core/disclaimer.py so every answer
# endpoint uses the same one, not just this agent.


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
    """
    Search across all of the user's reports, and only the user's reports.

    This used to take the global top 8 and then drop other users' chunks, so
    the user's own pages were usually gone before the filter ran: Recall@5
    measured 1.2% against 30.0% for filtering first. Passing the ids into the
    search is that fix.

    Deliberately dense-only. hybrid_search() exists and scores higher overall
    on the current question set, but the gain is entirely in questions that
    quote a metric name verbatim, and it significantly regresses the
    multi-step ones. eval/EXPERIMENTS.md has the numbers and the reasoning.
    """
    if not user_report_ids:
        return "No relevant medical report context found for this question."

    user_chunks = search_similar_chunks(
        query=question, top_k=5, filter_report_ids=user_report_ids)

    if not user_chunks:
        return "No relevant medical report context found for this question."

    # Each excerpt carries the report and page it came from, so the model can
    # be held to citing a real page rather than asserting one.
    excerpts = [
        "[report {0}, page {1}]\n{2}".format(
            c["report_id"], c.get("page", "?"), c["chunk"])
        for c in user_chunks
    ]
    return "RELEVANT MEDICAL REPORT EXCERPTS:\n" + "\n\n---\n\n".join(excerpts)


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
    if llm is None:
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
        response = await complete(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.4,
        )
        answer = (response.choices[0].message.content or "").strip()
        # Same guarantee as report_analyzer: the excerpts in the prompt
        # come from uploaded files, so the rules above are a request and
        # this is the guard. See app/agents/safety.py.
        answer, removed = scrub_text(answer)
        if removed:
            logger.warning("Medication advice removed from a Copilot answer: %s",
                           [redact(r) for r in removed])
        return with_disclaimer(answer)
    except Exception as e:
        logger.error("Copilot LLM call failed: %s", e)
        raise ValueError(f"Health Copilot failed to generate a response: {e}")
