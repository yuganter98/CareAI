"""
extract_metrics() was split out of extract_and_store_metrics() so the eval
harness can score the real prompt without a database. These cover the split:
parsing behaviour, and that the storing path still stores.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics import metrics_extractor as me


def _llm_returning(content: str):
    """A stand-in chat completion that replies with `content`."""
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


class TestExtractMetrics:

    async def test_parses_a_clean_json_reply(self):
        reply = '{"metrics": [{"name": "Glucose", "value": 212, "unit": "mg/dL"}]}'
        with patch.object(me, "openai_client", _llm_returning(reply)):
            out = await me.extract_metrics("Glucose 212 mg/dL")
        assert out == [{"name": "glucose", "value": 212.0, "unit": "mg/dL"}]

    async def test_tolerates_prose_around_the_json(self):
        reply = 'Sure!\n```json\n{"metrics": [{"name": "hemoglobin", "value": "11.2", "unit": "g/dL"}]}\n```'
        with patch.object(me, "openai_client", _llm_returning(reply)):
            out = await me.extract_metrics("...")
        assert out == [{"name": "hemoglobin", "value": 11.2, "unit": "g/dL"}]

    async def test_drops_entries_whose_value_is_not_a_number(self):
        reply = ('{"metrics": [{"name": "glucose", "value": "not measured", "unit": "mg/dL"},'
                 ' {"name": "creatinine", "value": 1.1, "unit": "mg/dL"}]}')
        with patch.object(me, "openai_client", _llm_returning(reply)):
            out = await me.extract_metrics("...")
        assert [m["name"] for m in out] == ["creatinine"]

    async def test_malformed_json_returns_nothing_rather_than_raising(self):
        with patch.object(me, "openai_client", _llm_returning("the model rambled")):
            out = await me.extract_metrics("...")
        assert out == []

    async def test_no_llm_configured_returns_nothing(self):
        with patch.object(me, "openai_client", None):
            assert await me.extract_metrics("...") == []


class TestExtractAndStore:

    async def test_stores_one_row_per_extracted_metric(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        extracted = [
            {"name": "glucose", "value": 212.0, "unit": "mg/dL"},
            {"name": "hemoglobin", "value": 11.2, "unit": "g/dL"},
        ]
        with patch.object(me, "extract_metrics", AsyncMock(return_value=extracted)):
            stored = await me.extract_and_store_metrics(
                db, "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222", "report text")

        assert len(stored) == 2
        assert db.add.call_count == 2
        db.commit.assert_awaited_once()
        assert {m.metric_name for m in stored} == {"glucose", "hemoglobin"}

    async def test_nothing_extracted_means_no_commit(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        with patch.object(me, "extract_metrics", AsyncMock(return_value=[])):
            stored = await me.extract_and_store_metrics(
                db, "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222", "report text")

        assert stored == []
        db.commit.assert_not_awaited()
