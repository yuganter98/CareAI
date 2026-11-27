"""
The report pipeline's entry point.

One function, so callers do not have to know whether the pipeline is a graph,
an orchestrator or a for-loop - which is the whole point of the port being
invisible from outside. `ai.py` called `orchestrator.process_event(...)`
before and calls this now.

The compiled graph is built once and reused. Compiling is cheap but not free,
and the previous design already kept a warmed singleton for the same reason.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _compiled():
    from app.agents.checkpointing import build_checkpointer
    from app.agents.graph import build_graph

    return build_graph(checkpointer=build_checkpointer())


async def run_report_pipeline(
    *,
    report_id: str,
    report_text: str,
    user_id: str,
    db: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a report through the agent graph and return the final state.

    `db` travels in the run config, not the state, because a checkpointed
    state must be serialisable and a session is not. The returned state is
    therefore already safe to serialise into an HTTP response - the old
    orchestrator had to strip `db` out of it first.
    """
    config = {
        "configurable": {
            "db": db,
            # One thread per report, so a resumed run continues that report's
            # progress rather than starting a new one.
            "thread_id": f"report:{report_id}",
        }
    }
    state = await _compiled().ainvoke(
        {
            "report_id": report_id,
            "report_text": report_text,
            "user_id": user_id,
            "completed": [],
        },
        config=config,
    )
    return dict(state)


async def answer_question(report_id: str, question: str) -> Dict[str, Any]:
    """The query workflow, which was never a graph and does not need to be.

    The old orchestrator routed USER_QUERY through `process_event` to a single
    call of `query_report`. One node is not a graph; making it one would add a
    layer that explains nothing. Kept here so callers still have one module to
    import.
    """
    from app.agents.report_analyzer import query_report

    if not report_id or not question:
        raise ValueError("report_id and question are both required.")
    return {"answer": await query_report(report_id, question)}
