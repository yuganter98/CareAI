"""
The report pipeline as a LangGraph StateGraph.

This is a port, not a rewrite. The four agents in `orchestrated_agents.py` are
unchanged and still do the work; this module supplies the topology the
hand-built orchestrator expressed as a for-loop and two `if`s.

What the graph is
-----------------
    START -> planner -> [analyzer] -> [diagnosis] -> [insights] -> risk_gate
                                                                     |
                                                            emergency / END

The planner picks which agents run, through conditional edges: `_route` looks
at the plan and hands control to the next agent in it that has not run yet,
skipping the rest. The topology stays static and readable while the path
through it is decided at runtime.

Two invariants carried over deliberately, because they are the reason this
pipeline is safe rather than merely configurable:

1. **The High-risk edge is deterministic.** `risk_gate` routes to the
   emergency node whenever `risk_level` is HIGH, whatever the planner said -
   including when the planner omitted it, and when the planner failed
   entirely. A planner is an LLM reading attacker-influenced report text; the
   alert is not its decision to make. This is the same reasoning as
   `safety.py` and `risk_floor.py`: the guarantee lives outside the model.

2. **Planner failure runs the full pipeline.** `plan_workflow` already
   returns DEFAULT_PLAN on any failure, so a dead endpoint degrades to
   Analyzer -> Diagnosis -> Insights rather than to nothing.

What did not map cleanly
------------------------
The old orchestrator put the live `AsyncSession` into the state dict and
deleted it again before serialising the response. A checkpointed graph cannot
do that: state has to be serialisable to be written to a checkpoint, and a
database session is not. So `db` travels in the run's `config` instead, which
LangGraph passes to each node beside the state and never persists.

That is a real constraint rather than a workaround - it separates what the run
*is* from what the run is *using*, and the old design only got away with
mixing them because nothing ever tried to save the state.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.logger import observe_agent
from app.agents.orchestrated_agents import (
    DiagnosisAgent,
    EmergencyAgent,
    InsightsAgent,
    ReportAnalyzerAgent,
)

logger = logging.getLogger(__name__)

# Node names. These double as the agent-registry keys and the names the
# planner emits, so a typo surfaces as an unknown-agent warning rather than a
# silently skipped step.
ANALYZER = "ReportAnalyzerAgent"
DIAGNOSIS = "DiagnosisAgent"
INSIGHTS = "InsightsAgent"
EMERGENCY = "EmergencyAgent"
PLANNER = "planner"
RISK_GATE = "risk_gate"

# The order agents run in when the plan includes them. The planner chooses the
# subset, never the order: Diagnosis needs the Analyzer's abnormalities and
# Insights needs Diagnosis's flags, so a plan that reordered them would simply
# produce empty inputs.
AGENT_SEQUENCE = (ANALYZER, DIAGNOSIS, INSIGHTS)


class CareState(TypedDict, total=False):
    """Everything the graph carries between nodes.

    Serialisable by construction - see the module docstring on why `db` is
    not here. `total=False` because a run starts with only report_id and
    report_text and the nodes fill the rest in.
    """
    report_id: str
    report_text: str
    user_id: str

    # ReportAnalyzerAgent
    summary: str
    risk_level: str
    abnormalities: List[str]
    suggested_actions: List[str]

    # DiagnosisAgent / InsightsAgent
    diagnosis_flags: List[str]
    final_insight: str

    # EmergencyAgent
    emergency_triggered: bool

    # Bookkeeping: the plan, and which nodes have actually run. `completed`
    # is what `_route` uses to advance, so it is state rather than a local.
    orchestrator_plan: Dict[str, Any]
    completed: List[str]


_AGENTS = {
    ANALYZER: ReportAnalyzerAgent(),
    DIAGNOSIS: DiagnosisAgent(),
    INSIGHTS: InsightsAgent(),
    EMERGENCY: EmergencyAgent(),
}


def _db_from(config: Optional[Dict[str, Any]]):
    """The request's DB session, which travels in config, not in state."""
    return ((config or {}).get("configurable") or {}).get("db")


async def _run_agent(name: str, state: CareState, config) -> Dict[str, Any]:
    """Run one agent as a node, with the existing observability wrapper.

    `observe_agent` is what feeds the live WebSocket timeline and the
    agent_logs table, so every node keeps it: the point of the port is that
    nothing downstream notices the pipeline changed shape.
    """
    agent = _AGENTS[name]
    # The agents take a plain dict and mutate it, which is exactly what a
    # LangGraph node returns as its update. `db` is put back for the agent's
    # benefit and is not part of the returned update, so it never reaches a
    # checkpoint.
    working: Dict[str, Any] = dict(state)
    db = _db_from(config)
    if db is not None:
        working["db"] = db

    report_id = str(state.get("report_id") or "unknown")
    async with observe_agent(report_id, name):
        updated = await agent.run(working)

    updated.pop("db", None)
    update = {k: v for k, v in updated.items() if k != "completed"}
    update["completed"] = list(state.get("completed") or ()) + [name]
    return update


# ── Nodes ───────────────────────────────────────────────────────────────

async def planner_node(state: CareState, config=None) -> Dict[str, Any]:
    """Ask the LLM which agents to run; fall back to the full pipeline."""
    from app.agents.llm_orchestrator import plan_workflow

    plan = await plan_workflow(state.get("report_text", ""))
    logger.info("Plan: %s | hint=%s", plan.agents_to_run, plan.risk_hint)
    return {
        "orchestrator_plan": {
            "agents_run": plan.agents_to_run,
            "reasoning": plan.reasoning,
            "risk_hint": plan.risk_hint,
        },
        "completed": list(state.get("completed") or ()),
    }


async def analyzer_node(state: CareState, config=None) -> Dict[str, Any]:
    return await _run_agent(ANALYZER, state, config)


async def diagnosis_node(state: CareState, config=None) -> Dict[str, Any]:
    return await _run_agent(DIAGNOSIS, state, config)


async def insights_node(state: CareState, config=None) -> Dict[str, Any]:
    return await _run_agent(INSIGHTS, state, config)


async def emergency_node(state: CareState, config=None) -> Dict[str, Any]:
    return await _run_agent(EMERGENCY, state, config)


def risk_gate_node(state: CareState, config=None) -> Dict[str, Any]:
    """A no-op node that exists to give the safety edge somewhere to hang.

    The decision itself is in `_route_risk`; keeping the node empty means the
    routing rule is one function with no side effects, which is what makes it
    testable without running the pipeline.
    """
    return {}


# ── Edges ───────────────────────────────────────────────────────────────

def _planned(state: CareState) -> List[str]:
    plan = state.get("orchestrator_plan") or {}
    agents = plan.get("agents_run") or []
    return [a for a in agents if isinstance(a, str)]


def _route(state: CareState) -> str:
    """The next agent in the plan that has not run, else the risk gate."""
    planned = _planned(state)
    done = set(state.get("completed") or ())
    for name in AGENT_SEQUENCE:
        if name in planned and name not in done:
            return name
    # Unknown names in a plan are ignored rather than fatal, matching the old
    # orchestrator's "unknown agent — skipping" behaviour.
    unknown = [a for a in planned if a not in AGENT_SEQUENCE and a != EMERGENCY]
    if unknown:
        logger.warning("Unknown agent(s) in plan, ignored: %s", unknown)
    return RISK_GATE


def _route_risk(state: CareState) -> str:
    """The deterministic safety edge.

    HIGH risk goes to the emergency node whatever the plan said. A planner is
    an LLM reading report text that an attacker may have written; suppressing
    an alert is not a decision it gets to make. The injection test set has an
    attack that tries exactly this (`suppress_alert`).

    The emergency node is also reached when the planner *did* ask for it, so
    an explicitly planned alert on a non-HIGH report still runs - the agent
    itself then decides, as it always did, that nothing is dispatched unless
    risk is HIGH.
    """
    # .strip() as well as .upper(): the old pipeline compared
    # `state.get("risk_level", "").upper()` and so would have let a stray
    # space suppress an alert. A safety edge has to fail towards alerting.
    if str(state.get("risk_level") or "").strip().upper() == "HIGH":
        if EMERGENCY not in set(state.get("completed") or ()):
            return EMERGENCY
        return END
    if EMERGENCY in _planned(state) and EMERGENCY not in set(
            state.get("completed") or ()):
        return EMERGENCY
    return END


def build_graph(checkpointer=None):
    """Compile the report pipeline.

    `checkpointer` is optional so the graph is usable in tests and in a
    request without a database. See `checkpointing.py` for how one is chosen.
    """
    graph = StateGraph(CareState)

    graph.add_node(PLANNER, planner_node)
    graph.add_node(ANALYZER, analyzer_node)
    graph.add_node(DIAGNOSIS, diagnosis_node)
    graph.add_node(INSIGHTS, insights_node)
    graph.add_node(RISK_GATE, risk_gate_node)
    graph.add_node(EMERGENCY, emergency_node)

    graph.add_edge(START, PLANNER)

    # Every agent returns to the router, which walks the plan in order. One
    # routing function rather than a hand-wired chain, so a plan that skips
    # the middle of the sequence needs no extra edges.
    routes = {ANALYZER: ANALYZER, DIAGNOSIS: DIAGNOSIS,
              INSIGHTS: INSIGHTS, RISK_GATE: RISK_GATE}
    for node in (PLANNER, ANALYZER, DIAGNOSIS, INSIGHTS):
        graph.add_conditional_edges(node, _route, routes)

    graph.add_conditional_edges(RISK_GATE, _route_risk,
                                {EMERGENCY: EMERGENCY, END: END})
    graph.add_edge(EMERGENCY, END)

    return graph.compile(checkpointer=checkpointer) if checkpointer else graph.compile()
