"""
Where a graph run's progress is saved.

A checkpointer lets a failed run resume from its last completed node instead
of starting over, which matters here because a report run makes three or four
LLM calls and the expensive one is the first.

What is actually wired up
-------------------------
`MemorySaver`, which is per-process. It makes resume work within one server
process and is what the tests exercise. It does **not** survive a restart, so
it is not the durable checkpointing the build plan asks for.

Postgres checkpointing is the real answer and is deliberately not claimed to
work here. `langgraph-checkpoint-postgres` needs `psycopg`, while this project
talks to Postgres through `asyncpg`; adding a second driver and a second
connection pool is a change worth making on purpose, with a live database to
test against. Writing the import and asserting it works without ever running
it would be the kind of untested claim this project has been careful to avoid
- see eval/README.md on a preflight that passed while every real call failed.

So `build_checkpointer` prefers Postgres when the package is importable and a
DATABASE_URL is set, falls back to memory, and says in the log which one it
got. The selection logic is tested; the Postgres path is not, and the README
says so.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_checkpointer(prefer_durable: bool = True) -> Optional[Any]:
    """A checkpointer for the report graph, or None if none can be made.

    Returns None rather than raising: a graph without a checkpointer still
    runs, it simply cannot resume. Losing the ability to resume is not a
    reason to refuse to analyse a report.
    """
    if prefer_durable and getattr(settings, "DATABASE_URL", None):
        saver = _try_postgres()
        if saver is not None:
            return saver

    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:            # langgraph without the checkpoint extra
        logger.warning("No checkpointer available; graph runs cannot resume.")
        return None

    logger.info("Graph checkpointing: in-memory (per process, not durable).")
    return MemorySaver()


def _try_postgres() -> Optional[Any]:
    """Postgres checkpointing, if the optional package is installed.

    Untested in this repository: it needs psycopg and a live database. If you
    enable it, verify a resume end to end before relying on it.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        logger.debug("langgraph-checkpoint-postgres not installed; "
                     "falling back to in-memory checkpointing.")
        return None

    try:
        # psycopg expects postgresql://, while this app's URL carries the
        # asyncpg driver for SQLAlchemy.
        url = str(settings.DATABASE_URL).replace("+asyncpg", "")
        saver = PostgresSaver.from_conn_string(url)
        logger.info("Graph checkpointing: Postgres.")
        return saver
    except Exception as exc:        # a bad URL must not stop report analysis
        logger.warning("Postgres checkpointer unavailable (%s); "
                       "falling back to in-memory.", exc)
        return None
