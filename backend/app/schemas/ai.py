"""
Pydantic schemas for every LLM response in the CareAI system.

Every LLM call must:
  1. Parse the raw string into JSON
  2. Validate with the appropriate schema below
  3. Fall back to the schema's safe default if validation fails

This guarantees consistent, typed outputs throughout the pipeline.
"""

from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator


# ─────────────────────────────────────────────────────────
#  1. Report Analysis  (ReportAnalyzerAgent)
# ─────────────────────────────────────────────────────────

class ReportAnalysisOutput(BaseModel):
    summary: str = "Analysis unavailable."
    abnormalities: List[str] = []
    risk_level: Literal["Low", "Medium", "High", "Unknown"] = "Unknown"
    suggested_actions: List[str] = []
    disclaimer: str = "AI-generated analysis. Not medical advice."

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk(cls, v: object) -> str:
        if isinstance(v, str):
            normalized = v.strip().capitalize()
            if normalized in ("Low", "Medium", "High"):
                return normalized
        return "Unknown"

    @field_validator("abnormalities", "suggested_actions", mode="before")
    @classmethod
    def ensure_list(cls, v: object) -> list:
        if isinstance(v, list):
            return [str(i) for i in v]
        if isinstance(v, str):
            return [v]
        return []


# ─────────────────────────────────────────────────────────
#  2. Diagnosis  (DiagnosisAgent)
# ─────────────────────────────────────────────────────────

class DiagnosisFlagsOutput(BaseModel):
    flags: List[str] = []

    @field_validator("flags", mode="before")
    @classmethod
    def ensure_list(cls, v: object) -> list:
        if isinstance(v, list):
            return [str(i) for i in v]
        if isinstance(v, str):
            return [v]
        return []


# ─────────────────────────────────────────────────────────
#  3. Insights  (InsightsAgent)
# ─────────────────────────────────────────────────────────

class InsightOutput(BaseModel):
    insight: str = "No insight available."


# ─────────────────────────────────────────────────────────
#  4. LLM Orchestrator Plan
# ─────────────────────────────────────────────────────────

VALID_AGENTS = {"ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent", "EmergencyAgent"}

class OrchestratorPlan(BaseModel):
    agents_to_run: List[str] = ["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"]
    reasoning: str = "Default pipeline."
    risk_hint: Optional[Literal["Low", "Medium", "High"]] = None

    @field_validator("agents_to_run", mode="before")
    @classmethod
    def validate_agents(cls, v: object) -> list:
        if not isinstance(v, list):
            return ["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"]
        # Strip unknown agents, keep order
        valid = [a for a in v if a in VALID_AGENTS]
        if not valid:
            return ["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"]
        # ReportAnalyzerAgent must always be first
        if valid[0] != "ReportAnalyzerAgent":
            valid = ["ReportAnalyzerAgent"] + [a for a in valid if a != "ReportAnalyzerAgent"]
        return valid


# ─────────────────────────────────────────────────────────
#  5. Personalized Insights
# ─────────────────────────────────────────────────────────

class MetricInsight(BaseModel):
    metric: str
    trend: Literal["increasing", "decreasing", "stable", "unknown"] = "unknown"
    current_value: Optional[float] = None
    unit: Optional[str] = None
    assessment: Literal["normal", "borderline", "elevated", "critical"] = "normal"
    recommendation: str = ""


class PersonalizedInsightOutput(BaseModel):
    insights: List[str] = []
    metrics: List[MetricInsight] = []
    summary: str = ""
    disclaimer: str = "AI-generated health insight. Not medical advice."

    @field_validator("insights", mode="before")
    @classmethod
    def ensure_list(cls, v: object) -> list:
        if isinstance(v, list):
            return [str(i) for i in v]
        return []


# ─────────────────────────────────────────────────────────
#  6. Explainability
# ─────────────────────────────────────────────────────────

class ExplainabilityOutput(BaseModel):
    question: str
    explanation: str = "Explanation unavailable."
    supporting_data: List[str] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    disclaimer: str = "AI-generated explanation. Not medical advice."
