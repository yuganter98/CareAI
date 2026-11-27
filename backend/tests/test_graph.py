"""
The LangGraph port, checked against the orchestrator it replaces.

Why a differential test and not the eval suite
----------------------------------------------
The build plan said to run the full eval on both pipelines and require that no
metric drops. That cannot work: the eval never touches the orchestrator. Every
stage calls `analyze_report`, `extract_report_pages` and `rag_pipeline`
directly, so every metric comes out byte-identical whether this port is
correct or completely broken. It would be a vacuous pass - a check that cannot
fail, which this project has already been bitten by twice.

What does verify a port is running both implementations over the same inputs
and requiring the same outcome. The agents are replaced with fakes, so these
tests are deterministic, need no API key, and compare *topology*: which nodes
ran, in what order, and what state came out. That is exactly what a port is
allowed to change nothing about.

The safety invariant gets its own class, because it is the one thing here that
must hold regardless of what the planner says.
"""
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import graph as G
from app.schemas.ai import OrchestratorPlan

pytestmark = pytest.mark.asyncio

REPORT_ID = str(uuid.uuid4())


@asynccontextmanager
async def _no_observe(*args, **kwargs):
    """Stand-in for observe_agent: no DB, no WebSocket, no timing."""
    yield


class FakeAgent:
    """Records that it ran and applies a scripted state change."""

    def __init__(self, name, order, effect=None):
        self.name, self._order, self._effect = name, order, effect or {}

    async def run(self, state):
        self._order.append(self.name)
        state.update(self._effect)
        return state


def _fakes(order, analyzer_effect=None):
    effects = {
        G.ANALYZER: analyzer_effect or {"risk_level": "Low", "summary": "s",
                                       "abnormalities": [], "suggested_actions": []},
        G.DIAGNOSIS: {"diagnosis_flags": ["flag"]},
        G.INSIGHTS: {"final_insight": "insight"},
        G.EMERGENCY: {"emergency_triggered": True},
    }
    return {name: FakeAgent(name, order, effects[name]) for name in effects}


async def _run_old(plan, analyzer_effect=None):
    """The pipeline the graph replaces, written out as a specification.

    This is `AgentOrchestrator.execute_report_workflow` reduced to the
    behaviour that matters: run the planned agents in order, skip names that
    are not agents, then run EmergencyAgent if risk is HIGH and the plan left
    it out.

    It is written here rather than imported because that module is deleted. An
    oracle that *is* the production code disappears with it, and then "the
    port matches the old pipeline" becomes an assertion about nothing. A
    fifteen-line specification outlives the deletion and stays readable.

    Verified three ways before the module was removed - the real
    orchestrator, this specification, and the compiled graph produced an
    identical execution order and an identical final state across all seven
    scenarios, including both High-risk ones. docs/langgraph-migration.md has
    the table.
    """
    order = []
    fakes = _fakes(order, analyzer_effect)
    state = {
        "report_id": REPORT_ID,
        "report_text": "text",
        "orchestrator_plan": {
            "agents_run": plan.agents_to_run,
            "reasoning": plan.reasoning,
            "risk_hint": plan.risk_hint,
        },
    }
    for name in plan.agents_to_run:
        agent = fakes.get(name)
        if agent is None:
            continue                      # "unknown agent - skipping"
        state = await agent.run(state)
    if (str(state.get("risk_level") or "").strip().upper() == "HIGH"
            and G.EMERGENCY not in plan.agents_to_run):
        state = await fakes[G.EMERGENCY].run(state)
    return order, state


async def _run_new(plan, analyzer_effect=None):
    """The compiled graph, with the same fake agents."""
    order = []
    fakes = _fakes(order, analyzer_effect)
    with patch.dict(G._AGENTS, fakes, clear=True), \
         patch("app.agents.graph.observe_agent", _no_observe), \
         patch("app.agents.llm_orchestrator.plan_workflow",
               new=AsyncMock(return_value=plan)):
        compiled = G.build_graph()
        state = await compiled.ainvoke(
            {"report_id": REPORT_ID, "report_text": "text"},
            config={"configurable": {"db": None}})
    return order, dict(state)


# Keys the graph keeps for its own routing, which the old orchestrator had no
# equivalent of. Excluded from the comparison rather than quietly ignored.
BOOKKEEPING = {"completed"}


def _comparable(state):
    return {k: v for k, v in state.items() if k not in BOOKKEEPING}


PLANS = {
    "default": OrchestratorPlan(
        agents_to_run=[G.ANALYZER, G.DIAGNOSIS, G.INSIGHTS],
        reasoning="default", risk_hint="Low"),
    "analyzer only": OrchestratorPlan(
        agents_to_run=[G.ANALYZER], reasoning="minimal", risk_hint="Low"),
    "skips diagnosis": OrchestratorPlan(
        agents_to_run=[G.ANALYZER, G.INSIGHTS], reasoning="skip", risk_hint="Low"),
    "planner asked for emergency": OrchestratorPlan(
        agents_to_run=[G.ANALYZER, G.EMERGENCY], reasoning="urgent", risk_hint="High"),
    "unknown agent in plan": OrchestratorPlan(
        agents_to_run=[G.ANALYZER, "NoSuchAgent", G.INSIGHTS],
        reasoning="typo", risk_hint="Low"),
}


class TestTheSameAsTheOldPipeline:

    @pytest.mark.parametrize("label", list(PLANS))
    async def test_the_same_agents_run_in_the_same_order(self, label):
        plan = PLANS[label]
        old_order, _ = await _run_old(plan)
        new_order, _ = await _run_new(plan)
        assert new_order == old_order, label

    @pytest.mark.parametrize("label", list(PLANS))
    async def test_the_same_state_comes_out(self, label):
        plan = PLANS[label]
        _, old_state = await _run_old(plan)
        _, new_state = await _run_new(plan)
        assert _comparable(new_state) == _comparable(old_state), label

    async def test_an_unknown_agent_is_skipped_not_fatal(self):
        order, _ = await _run_new(PLANS["unknown agent in plan"])
        assert order == [G.ANALYZER, G.INSIGHTS]

    async def test_a_plan_that_skips_the_middle_still_reaches_insights(self):
        # The routing walks the sequence rather than following a hand-wired
        # chain, so a gap in the plan needs no extra edge.
        order, _ = await _run_new(PLANS["skips diagnosis"])
        assert order == [G.ANALYZER, G.INSIGHTS]


class TestTheDeterministicHighRiskEdge:
    """
    The one invariant that does not depend on the planner. A planner is an LLM
    reading report text an attacker may have written, and the injection set
    has an attack (`suppress_alert`) that asks it to skip the alert.
    """

    HIGH = {"risk_level": "High", "summary": "s", "abnormalities": ["glucose 450"],
            "suggested_actions": []}

    async def test_high_risk_runs_emergency_though_the_plan_omits_it(self):
        plan = PLANS["analyzer only"]
        order, state = await _run_new(plan, analyzer_effect=self.HIGH)
        assert G.EMERGENCY in order
        assert state["emergency_triggered"] is True

    async def test_the_old_pipeline_agreed(self):
        order, _ = await _run_old(PLANS["analyzer only"], analyzer_effect=self.HIGH)
        assert G.EMERGENCY in order

    async def test_it_runs_last_not_mid_pipeline(self):
        order, _ = await _run_new(PLANS["default"], analyzer_effect=self.HIGH)
        assert order[-1] == G.EMERGENCY

    async def test_it_runs_once_even_when_also_planned(self):
        # Planned *and* High risk must not dispatch two alerts.
        plan = OrchestratorPlan(agents_to_run=[G.ANALYZER, G.EMERGENCY],
                                reasoning="both", risk_hint="High")
        order, _ = await _run_new(plan, analyzer_effect=self.HIGH)
        assert order.count(G.EMERGENCY) == 1

    async def test_a_low_risk_report_does_not_trigger_it(self):
        order, _ = await _run_new(PLANS["default"])
        assert G.EMERGENCY not in order

    @pytest.mark.parametrize("level", ["High", "HIGH", "high", "  high  "])
    async def test_the_check_is_not_case_or_space_sensitive(self, level):
        order, _ = await _run_new(PLANS["analyzer only"],
                                  analyzer_effect={**self.HIGH, "risk_level": level})
        assert G.EMERGENCY in order, level

    async def test_an_unknown_risk_level_does_not_trigger_it(self):
        # A failed analysis returns "Unknown". Escalating that would page a
        # clinician on every API outage.
        order, _ = await _run_new(
            PLANS["analyzer only"],
            analyzer_effect={**self.HIGH, "risk_level": "Unknown"})
        assert G.EMERGENCY not in order


class TestPlannerFailureFallsBackToTheFullPipeline:

    async def test_a_planner_failure_runs_all_three_agents(self):
        # plan_workflow returns DEFAULT_PLAN on any failure, so a dead
        # endpoint degrades to the full pipeline rather than to nothing.
        from app.agents.llm_orchestrator import DEFAULT_PLAN

        order, _ = await _run_new(DEFAULT_PLAN)
        assert order == [G.ANALYZER, G.DIAGNOSIS, G.INSIGHTS]

    async def test_a_planner_cannot_empty_the_pipeline(self):
        # OrchestratorPlan's validator replaces an empty or all-unknown list
        # with the full default pipeline, so "run nothing" is not a plan the
        # planner can express. Worth pinning: it means a planner talked into
        # returning [] still gets the report analysed.
        plan = OrchestratorPlan(agents_to_run=[], reasoning="empty")
        assert plan.agents_to_run == [G.ANALYZER, G.DIAGNOSIS, G.INSIGHTS]
        order, _ = await _run_new(plan)
        assert order == [G.ANALYZER, G.DIAGNOSIS, G.INSIGHTS]

    async def test_a_plan_of_only_unknown_agents_falls_back(self):
        plan = OrchestratorPlan(agents_to_run=["Nope", "AlsoNope"], reasoning="junk")
        order, _ = await _run_new(plan)
        assert order == [G.ANALYZER, G.DIAGNOSIS, G.INSIGHTS]


class TestStateStaysSerialisable:
    """
    The old orchestrator put the live AsyncSession in the state dict. A
    checkpointed graph cannot: state has to be serialisable to be written to a
    checkpoint. `db` travels in config instead.
    """

    async def test_the_session_never_lands_in_state(self):
        sentinel = object()
        order = []
        fakes = _fakes(order)
        with patch.dict(G._AGENTS, fakes, clear=True), \
             patch("app.agents.graph.observe_agent", _no_observe), \
             patch("app.agents.llm_orchestrator.plan_workflow",
                   new=AsyncMock(return_value=PLANS["default"])):
            compiled = G.build_graph()
            state = await compiled.ainvoke(
                {"report_id": REPORT_ID, "report_text": "text"},
                config={"configurable": {"db": sentinel}})
        assert "db" not in state
        assert sentinel not in state.values()

    async def test_the_agents_still_receive_it(self):
        # EmergencyAgent needs the session to dispatch alerts, so it has to
        # arrive from config even though it is not state.
        seen = {}

        class Watcher(FakeAgent):
            async def run(self, state):
                seen["db"] = state.get("db")
                return await super().run(state)

        sentinel = object()
        order = []
        fakes = _fakes(order)
        fakes[G.ANALYZER] = Watcher(G.ANALYZER, order, {"risk_level": "Low"})
        with patch.dict(G._AGENTS, fakes, clear=True), \
             patch("app.agents.graph.observe_agent", _no_observe), \
             patch("app.agents.llm_orchestrator.plan_workflow",
                   new=AsyncMock(return_value=PLANS["analyzer only"])):
            await G.build_graph().ainvoke(
                {"report_id": REPORT_ID, "report_text": "text"},
                config={"configurable": {"db": sentinel}})
        assert seen["db"] is sentinel


class TestRoutingInIsolation:
    """The routing functions are pure, so they are tested without the graph."""

    def test_route_advances_through_the_plan(self):
        plan = {"agents_run": [G.ANALYZER, G.DIAGNOSIS]}
        assert G._route({"orchestrator_plan": plan, "completed": []}) == G.ANALYZER
        assert G._route({"orchestrator_plan": plan,
                         "completed": [G.ANALYZER]}) == G.DIAGNOSIS
        assert G._route({"orchestrator_plan": plan,
                         "completed": [G.ANALYZER, G.DIAGNOSIS]}) == G.RISK_GATE

    def test_route_ignores_order_in_the_plan(self):
        # Diagnosis needs the Analyzer's abnormalities and Insights needs
        # Diagnosis's flags, so the planner picks the subset, never the order.
        plan = {"agents_run": [G.INSIGHTS, G.ANALYZER]}
        assert G._route({"orchestrator_plan": plan, "completed": []}) == G.ANALYZER

    def test_route_with_no_plan_at_all(self):
        assert G._route({}) == G.RISK_GATE

    def test_risk_route_is_deterministic(self):
        from langgraph.graph import END
        assert G._route_risk({"risk_level": "High"}) == G.EMERGENCY
        assert G._route_risk({"risk_level": "Low"}) == END
        assert G._route_risk({}) == END
        assert G._route_risk({"risk_level": "High",
                              "completed": [G.EMERGENCY]}) == END
