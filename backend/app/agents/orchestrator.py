"""
AgentOrchestrator — the central brain of CareAI.

Upgrade: instead of a hardcoded pipeline, the LLM planner (llm_orchestrator)
decides which agents run and in what configuration based on the report content.

Fallback guarantee: if LLM planning fails, the full default pipeline runs.
HIGH-risk safety net: EmergencyAgent always runs when risk_level == HIGH,
even if the planner didn't include it.
"""

import logging
from typing import Dict, Any

from app.agents.orchestrated_agents import (
    ReportAnalyzerAgent,
    DiagnosisAgent,
    InsightsAgent,
    EmergencyAgent,
)
from app.agents.report_analyzer import query_report
from app.agents.logger import observe_agent

logger = logging.getLogger(__name__)

# Map of agent name → agent instance (populated in __init__)
_AGENT_REGISTRY: Dict[str, Any] = {}


class AgentOrchestrator:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        _AGENT_REGISTRY["ReportAnalyzerAgent"] = ReportAnalyzerAgent()
        _AGENT_REGISTRY["DiagnosisAgent"]       = DiagnosisAgent()
        _AGENT_REGISTRY["InsightsAgent"]        = InsightsAgent()
        _AGENT_REGISTRY["EmergencyAgent"]       = EmergencyAgent()

    async def execute_report_workflow(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        WORKFLOW 1 — LLM-planned report processing.

        1. Ask the LLM planner which agents to run.
        2. Execute each planned agent in order, wrapped by observe_agent().
        3. Safety net: always run EmergencyAgent if risk_level == HIGH.
        """
        report_id = state.get("report_id", "unknown")
        self.logger.info(">>> LLM-Orchestrated Workflow [report_id=%s]", report_id)

        # ── Step 1: LLM plans the workflow ───────────────────────────────────
        from app.agents.llm_orchestrator import plan_workflow
        plan = await plan_workflow(state.get("report_text", ""))

        state["orchestrator_plan"] = {
            "agents_run": plan.agents_to_run,
            "reasoning":  plan.reasoning,
            "risk_hint":  plan.risk_hint,
        }
        self.logger.info("Plan: %s | hint=%s", plan.agents_to_run, plan.risk_hint)

        # ── Step 2: Execute planned agents in order ───────────────────────────
        for agent_name in plan.agents_to_run:
            agent = _AGENT_REGISTRY.get(agent_name)
            if not agent:
                self.logger.warning("Unknown agent '%s' in plan — skipping.", agent_name)
                continue
            async with observe_agent(report_id, agent_name):
                state = await agent.run(state)

        # ── Step 3: Safety net — HIGH risk always triggers EmergencyAgent ────
        if (
            state.get("risk_level", "").upper() == "HIGH"
            and "EmergencyAgent" not in plan.agents_to_run
        ):
            self.logger.warning("Safety net: HIGH risk — running EmergencyAgent.")
            async with observe_agent(report_id, "EmergencyAgent"):
                state = await _AGENT_REGISTRY["EmergencyAgent"].run(state)

        self.logger.info("<<< Workflow complete [report_id=%s]", report_id)
        return state

    async def execute_query_workflow(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """WORKFLOW 2 — RAG Q&A against a specific report's FAISS vectors."""
        self.logger.info(">>> Query Workflow")

        report_id = state.get("report_id")
        question  = state.get("question")

        if not report_id or not question:
            raise ValueError("report_id and question required for the Query Workflow.")

        state["answer"] = await query_report(report_id, question)
        self.logger.info("<<< Query Workflow complete.")
        return state

    async def process_event(self, event_type: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Global entrypoint routing HTTP events into the agent graph."""
        if event_type == "PROCESS_REPORT":
            return await self.execute_report_workflow(state)
        elif event_type == "USER_QUERY":
            return await self.execute_query_workflow(state)
        else:
            raise ValueError(f"Unknown event_type: {event_type}")


# Warmed singleton — reused across all requests
orchestrator = AgentOrchestrator()
