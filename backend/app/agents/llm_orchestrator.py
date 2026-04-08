"""
LLM-Driven Workflow Planner.

Instead of hardcoding the agent execution order, this module asks the LLM
to read a brief excerpt of the report and return a structured JSON plan
specifying which agents to run and why.

Fallback: if the LLM is unavailable or returns invalid JSON, the full default
pipeline (Analyzer → Diagnosis → Insights) runs automatically.
"""

import json
import logging
from pydantic import ValidationError

from app.agents.llm_client import llm, parse_json_block
from app.schemas.ai import OrchestratorPlan

logger = logging.getLogger(__name__)

# ── Default plan used when LLM planning fails ────────────────────────────────
DEFAULT_PLAN = OrchestratorPlan(
    agents_to_run=["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"],
    reasoning="Default pipeline — LLM planning unavailable or failed.",
)

# ── System prompt ────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """
You are an AI medical workflow planner for CareAI.

Given a brief excerpt of a patient's medical report, decide which analysis
agents should run. Return ONLY a raw JSON object — no markdown, no explanation.

Available agents (run in order if selected):
  - "ReportAnalyzerAgent" — ALWAYS include. Extracts summary, abnormalities, risk level.
  - "DiagnosisAgent"      — Include when clinical abnormalities are likely present.
  - "InsightsAgent"       — Include when patient-facing trend guidance is useful.
  - "EmergencyAgent"      — Include ONLY for immediately life-threatening values
                            (e.g. glucose > 400, BP systolic > 180, Hb < 7 g/dL).

Output format:
{
  "agents_to_run": ["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"],
  "reasoning": "One sentence explaining the choice.",
  "risk_hint": "Low" | "Medium" | "High" | null
}
""".strip()


async def plan_workflow(report_text: str) -> OrchestratorPlan:
    """
    Ask the LLM to produce an execution plan for the given report.

    Uses only the first 1 500 chars so planning is fast and cheap.
    Falls back to DEFAULT_PLAN on any failure.
    """
    if not llm:
        logger.warning("LLM client not available — using default pipeline.")
        return DEFAULT_PLAN

    snippet = report_text[:1500]

    try:
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Report excerpt:\n{snippet}"},
            ],
            temperature=0.1,   # deterministic planning
        )

        raw = response.choices[0].message.content or ""
        json_str = parse_json_block(raw)
        parsed = json.loads(json_str)
        plan = OrchestratorPlan.model_validate(parsed)

        logger.info(
            "LLM plan — agents=%s | risk_hint=%s | reason=%s",
            plan.agents_to_run, plan.risk_hint, plan.reasoning,
        )
        return plan

    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("LLM plan validation failed (%s) — using default pipeline.", e)
        return DEFAULT_PLAN
    except Exception as e:
        logger.warning("LLM planning error (%s) — using default pipeline.", e)
        return DEFAULT_PLAN
