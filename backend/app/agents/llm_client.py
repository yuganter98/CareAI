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


def parse_json_block(raw: str) -> str:
    """
    Strip markdown fences and extract the first JSON object or array from a string.
    Used by every agent that calls the LLM and expects JSON back.
    """
    import re
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    return match.group(1) if match else cleaned
