# Porting the report pipeline to LangGraph

The hand-built `AgentOrchestrator` already had the shape of a graph — a
planner, four agents and a conditional safety step — so this was a port, not a
rewrite. The four agents in `orchestrated_agents.py` are **unchanged**.

```
START → planner → [analyzer] → [diagnosis] → [insights] → risk_gate
                                                             │
                                                    emergency / END
```

`app/agents/graph.py` holds the topology, `app/agents/pipeline.py` the entry
point, and `app/agents/orchestrator.py` is deleted.

## How it was verified, and why not with the eval suite

The build plan said to run the full eval on both pipelines and require that no
metric drops. **That check cannot fail.** The eval never touches the
orchestrator: every stage calls `analyze_report`, `extract_report_pages` and
`rag_pipeline` directly. Every metric would come out byte-identical whether
this port were correct or completely broken — a vacuous pass, the same shape
of problem as a CI gate that cannot go red.

What verifies a port is running both implementations over the same inputs and
requiring the same outcome. With the agents replaced by fakes this is
deterministic, needs no API key, and compares the thing a port must not
change: which nodes ran, in what order, and what state came out.

Three-way, before the old module was deleted — the real orchestrator, a
fifteen-line specification of its behaviour, and the compiled graph:

| Plan | real == spec | spec == graph |
| --- | --- | --- |
| `[Analyzer, Diagnosis, Insights]` | yes | yes |
| `[Analyzer]` | yes | yes |
| `[Analyzer, Insights]` (gap in the middle) | yes | yes |
| `[Analyzer, Emergency]` (planner asked) | yes | yes |
| `[Analyzer, "NoSuchAgent", Insights]` | yes | yes |
| `[Analyzer]`, risk HIGH | yes | yes |
| full plan, risk HIGH | yes | yes |

Identical execution order and identical final state in all seven. The
specification, not the deleted module, is now the permanent oracle in
`tests/test_graph.py`: an oracle that *is* the production code disappears with
it, and then "the port matches the old pipeline" asserts nothing.

## What mapped cleanly

- **The agents.** Each `BaseAgent.run(state) -> state` is already a
  LangGraph node: take state, return an update. No agent changed.
- **Observability.** Every node still runs inside `observe_agent`, so the
  `agent_logs` rows and the live WebSocket timeline are byte-identical. The
  port is invisible from outside.
- **The planner's choice.** A for-loop over `plan.agents_to_run` became one
  routing function that walks `AGENT_SEQUENCE` and hands control to the next
  agent in the plan that has not run. The topology stays static while the path
  through it is decided at runtime, and a plan with a gap in the middle needs
  no extra edges.
- **Planner failure.** `plan_workflow` already returns `DEFAULT_PLAN` on any
  failure, so a dead endpoint still runs Analyzer → Diagnosis → Insights.

## What did not

**The database session could not stay in the state.** The old orchestrator put
the live `AsyncSession` into the state dict and deleted it again before
serialising the response. A checkpointed graph cannot: state has to be
serialisable to be written to a checkpoint, and a session is not. `db` travels
in the run's `config` instead, which LangGraph passes to each node and never
persists.

This is a real constraint rather than a workaround. It separates what the run
*is* from what the run is *using*, and the old design only got away with
mixing them because nothing ever tried to save the state. The endpoint got
simpler too: it no longer has to strip `db` out of the response.

**The query workflow is not a graph.** `process_event("USER_QUERY")` routed to
a single call of `query_report`. One node is not a graph, and making it one
would add a layer that explains nothing, so `pipeline.answer_question` is a
plain function.

**Durable checkpointing is not done.** `app/agents/checkpointing.py` wires up
`MemorySaver`, which makes resume work within one server process and is what
the tests exercise. It does not survive a restart. Postgres checkpointing
needs `langgraph-checkpoint-postgres`, which needs `psycopg`, while this
project reaches Postgres through `asyncpg` — a second driver and a second pool
is a change to make deliberately, against a live database. The code path is
there and is preferred when the package is importable; it is **untested here**
and labelled as such rather than claimed.

## One behaviour did change, on purpose

The High-risk safety edge now compares `.strip().upper()` where both the old
orchestrator and `EmergencyAgent` compared `.upper()` alone. A `risk_level` of
`" high "` would have silently suppressed an emergency alert in the old
pipeline. Pydantic normalises the field in the common path, so this was
unlikely rather than impossible — but it is the last check before an alert is
or is not sent, and a safety edge has to fail towards alerting. A test pins
each spelling.

## The invariant worth knowing about

`_route_risk` sends any HIGH-risk state to the emergency node **whatever the
planner said**, including when the planner omitted it and when the planner
failed entirely. A planner is an LLM reading report text an attacker may have
written, and the injection test set contains an attack (`suppress_alert`) that
asks exactly this. The decision is not the model's to make — the same
reasoning as `safety.py` and `risk_floor.py`.

`OrchestratorPlan`'s validator also replaces an empty or all-unknown
`agents_to_run` with the full default pipeline, so "run nothing" is not a plan
the planner can express.

## Numbers

31 graph tests; 306 in the suite. No latency comparison is recorded: the port
adds a routing function and a dict copy per node against three or four LLM
calls that dominate the run by three orders of magnitude, and measuring it
through the API would report the model's variance rather than the graph's.
