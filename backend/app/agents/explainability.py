"""
Explainability Engine — answers "why" questions about CareAI decisions.

Given a report_id and a natural language question such as:
  - "Why was my risk level assessed as High?"
  - "Why are these actions being suggested?"
  - "What data made the AI flag glucose as a concern?"

The engine:
  1. Pulls the patient's HealthMetric records (objective data)
  2. Retrieves relevant FAISS report chunks (grounding context)
  3. Asks the LLM to explain the decision *using only the data above*
  4. Returns a validated ExplainabilityOutput

Fallback: returns a structured "insufficient data" response — never raises.
"""

import json
import logging
import uuid
from typing import Dict, Any, List
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.llm_client import llm, parse_json_block
from app.agents.rag_pipeline import search_similar_chunks
from app.schemas.ai import ExplainabilityOutput
from app.db.models import HealthMetric

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are CareAI's explainability engine. Your job is to answer "why" questions
about AI-driven health assessments, using ONLY the patient data provided.

Return a raw JSON object — no markdown, no extra text:
{
  "explanation": "Clear, 2-4 sentence explanation referencing actual data values.",
  "supporting_data": ["Fact 1 from the data", "Fact 2 from the data"],
  "confidence": "high" | "medium" | "low"
}

Rules:
- Ground EVERY claim in the provided data (metrics + report excerpts).
- If the data is insufficient to explain fully, say so and set confidence = "low".
- Use plain language the patient can understand.
- Never fabricate values or diagnoses not present in the context.
""".strip()


async def _get_metric_context(db: AsyncSession, user_id: str) -> List[str]:
    """Build a list of factual strings from the patient's stored metrics."""
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == uuid.UUID(user_id))
        .order_by(HealthMetric.recorded_at.desc())
        .limit(30)
    )
    metrics = result.scalars().all()

    facts = []
    for m in metrics:
        date = m.recorded_at.strftime("%Y-%m-%d") if m.recorded_at else "unknown date"
        facts.append(
            f"{m.metric_name}: {m.metric_value} {m.unit or ''} (recorded {date})"
        )
    return facts


def _get_report_context(question: str, report_id: str) -> List[str]:
    """Retrieve the most relevant FAISS chunks for this report and question."""
    chunks = search_similar_chunks(query=question, top_k=5, filter_report_id=report_id)
    return [c["chunk"] for c in chunks]


async def explain(
    db: AsyncSession,
    user_id: str,
    report_id: str,
    question: str,
) -> Dict[str, Any]:
    """
    Main explainability entrypoint.
    Returns a validated ExplainabilityOutput dict.
    """
    # ── 1. Gather grounding data ──────────────────────────────────────────────
    metric_facts   = await _get_metric_context(db, user_id)
    report_chunks  = _get_report_context(question, report_id)

    # ── 2. Build context block for the LLM ───────────────────────────────────
    context_parts: List[str] = []

    if metric_facts:
        context_parts.append("PATIENT METRICS:\n" + "\n".join(f"  • {f}" for f in metric_facts))
    else:
        context_parts.append("PATIENT METRICS: No stored metrics found.")

    if report_chunks:
        excerpts = "\n\n---\n\n".join(report_chunks[:3])
        context_parts.append(f"RELEVANT REPORT EXCERPTS:\n{excerpts}")
    else:
        context_parts.append("RELEVANT REPORT EXCERPTS: No matching content found.")

    data_context = "\n\n".join(context_parts)

    # ── 3. No LLM available — return structured fallback ─────────────────────
    if not llm:
        logger.warning("LLM unavailable — returning data-only explanation.")
        supporting = metric_facts[:5] if metric_facts else ["No metric data available."]
        return ExplainabilityOutput(
            question=question,
            explanation=(
                "The LLM service is currently unavailable. "
                "Here is the raw data used by the system to make its assessment."
            ),
            supporting_data=supporting,
            confidence="low",
        ).model_dump()

    # ── 4. Ask the LLM to explain ─────────────────────────────────────────────
    user_message = (
        f"Patient question: {question}\n\n"
        f"Data available to explain the decision:\n{data_context}"
    )

    try:
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,   # low temperature for factual grounding
        )

        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(parse_json_block(raw))

        output = ExplainabilityOutput.model_validate({
            "question":       question,
            "explanation":    parsed.get("explanation", "Explanation unavailable."),
            "supporting_data": parsed.get("supporting_data", metric_facts[:5]),
            "confidence":     parsed.get("confidence", "medium"),
        })
        return output.model_dump()

    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Explainability output invalid (%s) — returning data fallback.", e)

    except Exception as e:
        logger.error("Explainability LLM call failed (%s).", e)

    # ── 5. Fallback: return the raw data with a canned explanation ────────────
    return ExplainabilityOutput(
        question=question,
        explanation=(
            "The assessment was based on the metric values and report content listed below. "
            "Please consult your doctor for a detailed clinical interpretation."
        ),
        supporting_data=(metric_facts[:5] or ["No metric data available."]),
        confidence="low",
    ).model_dump()
