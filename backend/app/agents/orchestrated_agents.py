import json
import logging
from typing import Dict, Any
from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.agents.report_analyzer import analyze_report
from app.agents.llm_client import llm, parse_json_block
from app.schemas.ai import DiagnosisFlagsOutput, InsightOutput

logger = logging.getLogger(__name__)


class ReportAnalyzerAgent(BaseAgent):
    """
    Agent 1 — Extracts structured summary and base risk level from raw report text.
    Output is validated by ReportAnalysisOutput (done inside analyze_report).
    Expects state['report_text'].
    """
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Executing ReportAnalyzerAgent...")
        report_text = state.get("report_text")
        if not report_text:
            raise ValueError("report_text missing from state")

        analysis = await analyze_report(report_text)

        state["summary"]           = analysis.get("summary")
        state["risk_level"]        = analysis.get("risk_level", "Unknown")
        state["abnormalities"]     = analysis.get("abnormalities", [])
        state["suggested_actions"] = analysis.get("suggested_actions", [])

        self.logger.info("ReportAnalyzerAgent done — risk=%s", state["risk_level"])
        return state


class DiagnosisAgent(BaseAgent):
    """
    Agent 2 — Sends extracted abnormalities to the LLM for clinical diagnostic
    reasoning. Output is validated by DiagnosisFlagsOutput.

    Fallback: heuristic keyword matching when the LLM is unavailable or returns
    invalid JSON.
    """
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Executing DiagnosisAgent...")
        abnormalities = state.get("abnormalities", [])

        if not abnormalities:
            state["diagnosis_flags"] = []
            self.logger.info("DiagnosisAgent: no abnormalities — skipping LLM.")
            return state

        prompt = (
            "You are a clinical diagnosis assistant.\n"
            "Given the abnormalities below, return a JSON object with a single key "
            "'flags' containing an array of concise clinical flags a doctor should review.\n\n"
            f"Abnormalities:\n{json.dumps(abnormalities, indent=2)}\n\n"
            'Return ONLY raw JSON. Example: {"flags": ["Hyperglycemia monitoring required."]}'
        )

        flags: list[str] = []
        try:
            resp = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content or "{}"
            parsed = json.loads(parse_json_block(raw))
            output = DiagnosisFlagsOutput.model_validate(parsed)
            flags = output.flags

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.warning("DiagnosisAgent structured output invalid (%s) — using heuristics.", e)
            flags = self._heuristic_flags(abnormalities)

        except Exception as e:
            self.logger.warning("DiagnosisAgent LLM call failed (%s) — using heuristics.", e)
            flags = self._heuristic_flags(abnormalities)

        state["diagnosis_flags"] = flags
        self.logger.info("DiagnosisAgent done — %d flags.", len(flags))
        return state

    @staticmethod
    def _heuristic_flags(abnormalities: list) -> list:
        """Keyword-based fallback when the LLM is unavailable."""
        flags = []
        for ab in abnormalities:
            ab_lower = ab.lower()
            if "glucose" in ab_lower:
                flags.append("Hyperglycemia monitoring required.")
            if "pressure" in ab_lower:
                flags.append("Hypertension protocol recommended.")
            if "cholesterol" in ab_lower or "ldl" in ab_lower:
                flags.append("Lipid management required.")
            if "creatinine" in ab_lower:
                flags.append("Kidney function follow-up needed.")
            if "hemoglobin" in ab_lower or "hb" in ab_lower:
                flags.append("Anaemia assessment recommended.")
        return flags


class InsightsAgent(BaseAgent):
    """
    Agent 3 — Synthesises summary + diagnostic flags into a patient-friendly
    insight paragraph. Output is validated by InsightOutput.

    Fallback: template-based insight when the LLM is unavailable.
    """
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Executing InsightsAgent...")
        summary = state.get("summary", "No summary available.")
        flags   = state.get("diagnosis_flags", [])
        actions = state.get("suggested_actions", [])

        prompt = (
            "You are a patient-facing health insights generator.\n"
            "Using the medical summary and clinical flags below, write a short, warm, "
            "and actionable paragraph of health guidance (2-4 sentences). "
            "Avoid jargon. Be encouraging but honest.\n\n"
            f"Summary: {summary}\n"
            f"Clinical flags: {json.dumps(flags)}\n"
            f"Suggested actions: {json.dumps(actions)}\n\n"
            'Return ONLY a raw JSON object: {"insight": "Your paragraph here."}'
        )

        insight: str = ""
        try:
            resp = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            raw = resp.choices[0].message.content or "{}"
            parsed = json.loads(parse_json_block(raw))
            output = InsightOutput.model_validate(parsed)
            insight = output.insight

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.warning("InsightsAgent structured output invalid (%s) — using fallback.", e)
            insight = self._fallback_insight(summary, flags)

        except Exception as e:
            self.logger.warning("InsightsAgent LLM call failed (%s) — using fallback.", e)
            insight = self._fallback_insight(summary, flags)

        state["final_insight"] = insight
        self.logger.info("InsightsAgent done.")
        return state

    @staticmethod
    def _fallback_insight(summary: str, flags: list) -> str:
        if flags:
            return (
                f"Based on your report ({summary}), the system flagged: "
                f"{'; '.join(flags[:3])}. "
                "Please consult your doctor for a personalised follow-up plan."
            )
        return (
            "Your results appear generally stable. "
            "Continue your routine wellness checks and maintain a healthy lifestyle."
        )


class EmergencyAgent(BaseAgent):
    """
    Agent 4 — Conditional edge triggered only when risk_level == HIGH.
    Dispatches SMS / email alerts via the emergency subsystem.
    """
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Executing EmergencyAgent...")
        risk_level = state.get("risk_level", "").upper()

        if risk_level == "HIGH":
            self.logger.warning("HIGH risk confirmed — dispatching emergency alerts.")
            db      = state.get("db")
            user_id = state.get("user_id")
            if db and user_id:
                from app.agents.emergency_agent import evaluate_and_trigger_emergency
                await evaluate_and_trigger_emergency(
                    user_id=user_id,
                    analysis_result={"risk_level": "HIGH"},
                    db=db,
                )
            else:
                self.logger.error("DB or user_id missing — cannot dispatch alerts.")
            state["emergency_triggered"] = True
        else:
            state["emergency_triggered"] = False

        self.logger.info("EmergencyAgent done.")
        return state
