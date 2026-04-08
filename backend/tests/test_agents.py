"""
Agent Test — DiagnosisAgent heuristic fallback.
The LLM call is patched to raise an exception, forcing the heuristic
branch so the test runs with zero external dependencies.
"""
import pytest
from unittest.mock import patch

from app.agents.orchestrated_agents import DiagnosisAgent


class TestDiagnosisAgent:

    async def test_heuristic_flags_glucose_and_pressure(self):
        """
        When the LLM is unavailable the agent should fall back to its built-in
        heuristics and still produce meaningful clinical flags for glucose
        and blood pressure abnormalities.
        """
        agent = DiagnosisAgent()
        state = {
            "abnormalities": [
                "High glucose levels detected: 250 mg/dL",
                "Elevated blood pressure: 160/95 mmHg",
            ]
        }

        with patch(
            "app.agents.orchestrated_agents.llm.chat.completions.create",
            side_effect=Exception("LLM unavailable — offline test"),
        ):
            result = await agent.run(state)

        flags = result["diagnosis_flags"]
        assert len(flags) > 0, "Expected at least one flag from heuristic fallback"
        assert any("Hyperglycemia" in f for f in flags)
        assert any("Hypertension" in f for f in flags)

    async def test_empty_abnormalities_skips_llm_and_returns_no_flags(self):
        """
        When there are no abnormalities the agent should short-circuit
        immediately — no LLM call, no flags.
        """
        agent = DiagnosisAgent()
        state = {"abnormalities": []}

        result = await agent.run(state)

        assert result["diagnosis_flags"] == []
