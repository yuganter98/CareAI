"""
Single shared AsyncOpenAI client for the entire CareAI backend.

All agents import `llm` from here instead of each creating their own client.
This avoids connection-pool waste and ensures one place to swap the model provider.
"""

import logging
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    llm = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or "lm-studio",
        base_url=settings.OPENAI_API_BASE or "http://localhost:1234/v1",
    )
    logger.info("LLM client initialised (base_url=%s)", settings.OPENAI_API_BASE)
except Exception as e:
    logger.error("LLM client init failed: %s", e)
    llm = None


async def complete(**kwargs):
    """`llm.chat.completions.create` with a bounded output and loud truncation.

    Every agent used to send no max_tokens. A provider that reserves budget
    before running a request then has to price it at the model's entire output
    window - 16k tokens for gpt-4o-mini - and refuses outright if that worst
    case exceeds the available credit, however small the real answer would be.
    That is not a billing edge case: it took down a whole eval run while the
    account had credit to spare, and it cost nothing to trigger, because the
    request never ran.

    Bounding it also bounds the bill, which matters for an endpoint that
    analyses user-uploaded files.

    Truncation is logged rather than swallowed. The callers parse JSON out of
    the reply and fall back on a parse error, so a limit set too low would
    surface as an unexplained "Unknown" analysis - and an analysis that failed
    scores like one that defended itself. If this warning appears, raise
    LLM_MAX_TOKENS; do not treat the fallback as a result.
    """
    kwargs.setdefault("max_tokens", settings.LLM_MAX_TOKENS)
    response = await llm.chat.completions.create(**kwargs)
    try:
        if response.choices[0].finish_reason == "length":
            logger.warning(
                "LLM reply hit the %s-token limit and was truncated; the "
                "caller will likely fail to parse it. Raise LLM_MAX_TOKENS.",
                kwargs["max_tokens"])
    except (AttributeError, IndexError, TypeError):
        pass
    return response


def parse_json_block(raw: str) -> str:
    """
    Strip markdown fences and extract the first JSON object or array from a string.
    Used by every agent that calls the LLM and expects JSON back.
    """
    import re
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    return match.group(1) if match else cleaned
