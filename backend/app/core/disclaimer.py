"""
The one disclaimer, in one place.

It used to live in `agents/copilot.py` and reach only the Copilot. Every other
answer endpoint - query-report, agent-query, explain, analyze-report,
health-insights - returned AI-generated clinical text with nothing attached,
which is the wrong default for an app that reads medical reports: a patient
has no way to know which endpoint produced the words in front of them.

Two shapes, because the endpoints have two:

- `with_disclaimer` appends to a prose answer.
- `attach_disclaimer` adds a `disclaimer` field to a structured response.
  Appending prose to a JSON object's `summary` would bury it inside content a
  client may well truncate, and it would also flow into anything downstream
  that reads that field - including the safety guards, which would then be
  scanning their own boilerplate.

Both are idempotent, so an endpoint that composes another's output cannot
produce it twice.
"""
from __future__ import annotations

from typing import Any, Dict

DISCLAIMER = (
    "\n\n---\n"
    "⚕️ *Disclaimer: This is AI-generated health guidance based on your "
    "uploaded reports. It is NOT a substitute for professional medical "
    "advice, diagnosis, or treatment. Always consult your doctor for "
    "clinical decisions.*"
)

# The same sentence without the Markdown wrapper, for a JSON field where a
# client decides its own presentation.
DISCLAIMER_TEXT = (
    "This is AI-generated health guidance based on your uploaded reports. "
    "It is not a substitute for professional medical advice, diagnosis, or "
    "treatment. Always consult your doctor for clinical decisions."
)

# Enough of the text to recognise it, whichever form was used.
_MARKER = "not a substitute for professional medical advice"


def with_disclaimer(answer: str) -> str:
    """Append the disclaimer to a prose answer, once."""
    if not isinstance(answer, str) or not answer.strip():
        # An empty answer with a disclaimer stapled on reads as though
        # something was said. Leave it to the caller's error handling.
        return answer
    if _MARKER in answer.lower():
        return answer
    return answer + DISCLAIMER


def attach_disclaimer(payload: Any) -> Any:
    """Add a `disclaimer` field to a structured response, once.

    Accepts a Pydantic model too, since several endpoints return validated
    output objects; those are dumped first, because the models have no such
    field and adding one to each schema would spread the same string across
    five definitions.
    """
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    if not isinstance(payload, dict):
        return payload
    if "disclaimer" in payload:
        return payload
    out = dict(payload)
    out["disclaimer"] = DISCLAIMER_TEXT
    return out
