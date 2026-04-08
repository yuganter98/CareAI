"""
Primary report analysis module.

analyze_report() — takes raw extracted text and returns a validated
ReportAnalysisOutput dict. Every JSON response from the LLM is validated
through Pydantic before it leaves this module.
"""

import json
import logging
from typing import Dict, Any
from pydantic import ValidationError

from app.agents.llm_client import llm, parse_json_block
from app.agents.rag_pipeline import search_similar_chunks
from app.schemas.ai import ReportAnalysisOutput

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are an expert AI medical assistant.
Analyze the provided medical report text and return a structured JSON response ONLY.

{
  "summary": "Simple, plain-language summary of the report",
  "abnormalities": ["List of key abnormalities found, if any"],
  "risk_level": "Low" | "Medium" | "High",
  "suggested_actions": ["List of suggested actions"]
}

Rules:
- risk_level MUST be exactly "Low", "Medium", or "High" — nothing else.
- Return valid JSON only. No markdown fences. No extra text.
- If no abnormalities exist, return an empty array for that key.
""".strip()

# Safe fallback returned when the LLM is unavailable or returns invalid JSON
_FALLBACK = ReportAnalysisOutput(
    summary="Automated analysis could not be completed. Please review the report manually.",
    risk_level="Unknown",
    suggested_actions=["Consult your doctor for a manual review of this report."],
)


async def analyze_report(report_text: str) -> Dict[str, Any]:
    """
    Analyze raw medical report text.
    Returns a validated dict matching ReportAnalysisOutput.
    Never raises — falls back to _FALLBACK on any error.
    """
    if not llm:
        logger.error("LLM client not initialised — returning fallback analysis.")
        return _FALLBACK.model_dump()

    safe_text = report_text[:14000]   # guard against local LLM context limits

    try:
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Medical Report:\n{safe_text}"},
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        json_str = parse_json_block(raw)
        parsed = json.loads(json_str)

        # Pydantic validates + normalises risk_level; invalid fields get safe defaults
        output = ReportAnalysisOutput.model_validate(parsed)
        return output.model_dump()

    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Report analysis output invalid (%s) — returning fallback.", e)
        return _FALLBACK.model_dump()

    except Exception as e:
        logger.error("LLM analysis failed (%s) — returning fallback.", e)
        return _FALLBACK.model_dump()


async def query_report(report_id: str, question: str) -> str:
    """
    RAG-based Q&A: retrieves relevant FAISS chunks for this report
    and answers the question using the LLM.
    """
    if not llm:
        raise ValueError("LLM client not available.")

    chunks = search_similar_chunks(query=question, top_k=5, filter_report_id=str(report_id))

    if not chunks:
        return (
            "I couldn't find relevant information in this report to answer your question.\n\n"
            "*Disclaimer: AI-generated. Not medical advice.*"
        )

    context = "\n\n---\n\n".join([c["chunk"] for c in chunks])

    system_prompt = (
        "You are a helpful AI medical assistant answering questions about a patient's report.\n"
        "Answer strictly from the context below. "
        "If the answer is not in the context, say so explicitly.\n\n"
        f"CONTEXT:\n{context}"
    )

    try:
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
        )
        answer = (response.choices[0].message.content or "").strip()
        return answer + "\n\n*Disclaimer: AI-generated. Not medical advice.*"

    except Exception as e:
        logger.error("RAG query failed: %s", e)
        raise ValueError(f"Failed to answer question: {e}")
