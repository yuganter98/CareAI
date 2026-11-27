"""
The disclaimer, on every answer endpoint.

It used to live in copilot.py and reach only the Copilot, so five other
endpoints returned AI-generated clinical text with nothing attached. A patient
cannot tell which endpoint produced the words in front of them.

The idempotence tests are not decoration: copilot_chat appends the disclaimer
itself and the endpoint wraps it again, so a non-idempotent implementation
ships two of them.
"""
import pytest

from app.core.disclaimer import (DISCLAIMER, DISCLAIMER_TEXT,
                                 attach_disclaimer, with_disclaimer)


class TestProseAnswers:

    def test_it_is_appended(self):
        out = with_disclaimer("Your glucose is 212 mg/dL.")
        assert out.startswith("Your glucose is 212 mg/dL.")
        # The rendered text says "NOT a substitute"; match case-insensitively.
        assert "not a substitute for professional medical advice" in out.lower()

    def test_appending_twice_adds_one(self):
        once = with_disclaimer("Your glucose is high.")
        assert with_disclaimer(once) == once

    def test_an_answer_that_already_carries_it_is_untouched(self):
        # copilot_chat appends it before the endpoint sees the answer.
        already = "Your glucose is high." + DISCLAIMER
        assert with_disclaimer(already) == already

    def test_an_empty_answer_gets_nothing(self):
        # A disclaimer alone reads as though something was said.
        assert with_disclaimer("") == ""
        assert with_disclaimer("   ") == "   "

    def test_a_non_string_passes_through(self):
        assert with_disclaimer(None) is None
        assert with_disclaimer({"answer": "x"}) == {"answer": "x"}


class TestStructuredResponses:

    def test_a_field_is_added_rather_than_prose_appended(self):
        # Appending to `summary` would bury it in content a client may
        # truncate, and it would flow into the safety guards, which would
        # then be scanning their own boilerplate.
        analysis = {"summary": "Creatinine is high.", "risk_level": "High"}
        out = attach_disclaimer(analysis)
        assert out["disclaimer"] == DISCLAIMER_TEXT
        assert out["summary"] == "Creatinine is high."

    def test_the_input_is_not_mutated(self):
        analysis = {"summary": "x"}
        attach_disclaimer(analysis)
        assert "disclaimer" not in analysis

    def test_attaching_twice_keeps_one(self):
        out = attach_disclaimer(attach_disclaimer({"summary": "x"}))
        assert out["disclaimer"] == DISCLAIMER_TEXT

    def test_an_existing_disclaimer_is_not_overwritten(self):
        out = attach_disclaimer({"summary": "x", "disclaimer": "custom"})
        assert out["disclaimer"] == "custom"

    def test_a_pydantic_model_is_dumped_first(self):
        from app.schemas.ai import ReportAnalysisOutput
        model = ReportAnalysisOutput(
            summary="Creatinine is high.", abnormalities=["creatinine 3.1"],
            risk_level="High", suggested_actions=["See your doctor."])
        out = attach_disclaimer(model)
        assert isinstance(out, dict)
        assert out["risk_level"] == "High"
        # The schema carries its own default, which is now the shared text.
        assert out["disclaimer"] == DISCLAIMER_TEXT

    def test_the_schemas_do_not_carry_their_own_wording(self):
        # Three schemas defaulted to a weaker line - "AI-generated analysis.
        # Not medical advice." - with no "consult your doctor" in it. Four
        # different disclaimers were reaching patients depending on which
        # endpoint answered.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1]
                  / "app" / "schemas" / "ai.py").read_text(encoding="utf-8")
        assert "Not medical advice." not in source
        assert source.count("disclaimer: str = DISCLAIMER_TEXT") == 3

    def test_a_non_dict_passes_through(self):
        assert attach_disclaimer("text") == "text"
        assert attach_disclaimer(None) is None
        assert attach_disclaimer([1, 2]) == [1, 2]


class TestEveryAnswerEndpointIsCovered:

    def test_no_answer_endpoint_returns_undisclaimed_output(self):
        # A structural check: if someone adds an endpoint that returns an
        # answer and forgets the disclaimer, the count here drifts. Crude,
        # but it fails loudly on the thing that is easy to forget.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1]
                  / "app" / "api" / "endpoints" / "ai.py").read_text(encoding="utf-8")
        covered = source.count("with_disclaimer(") + source.count("attach_disclaimer(")
        # 7 call sites. The import line has no parenthesis, so it is
        # not counted.
        assert covered >= 7, (
            f"only {covered} disclaimer call sites in ai.py; a new answer "
            f"endpoint may be returning clinical text without one")

    def test_the_copilot_agent_uses_the_shared_definition(self):
        # It kept a private copy, which is how five endpoints ended up
        # without one.
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1]
                  / "app" / "agents" / "copilot.py").read_text(encoding="utf-8")
        assert "DISCLAIMER = (" not in source
        assert "from app.core.disclaimer import" in source
