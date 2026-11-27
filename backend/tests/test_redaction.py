"""
Redaction before text leaves the server.

Two halves, and the second is the one that breaks things. Scrubbing too much
is not a safe failure: a glucose value eaten by a phone-number pattern is a
silent change to the thing the trace exists to show, and nobody reading the
trace can tell it happened.

So CLINICAL_LINES is the list that must come through untouched, and it is
tested character for character.
"""
import pytest

from app.core import redaction
from app.core.redaction import redact, redact_for_trace, redact_known

# Must survive exactly. Every one of these is a real shape from the corpus.
CLINICAL_LINES = [
    "Glucose, Fasting      450 mg/dL        Reference: 70 - 100",
    "Hemoglobin            13.1 g/dL        Reference: 12 - 17.5",
    "Creatinine, Serum     1.05 mg/dL       Reference: 0.7 - 1.3",
    "Blood Pressure        118/76 mmHg",
    "Your creatinine is 3.1 mg/dL, which is above the reference range.",
    "Glucose rose from 88 to 212 over three months.",
    "risk_level: High",
    "The report indicates that the hemoglobin level is critically low.",
    "Repeat testing and clinical correlation are advised.",
    "Do not start, stop or change any medication based on this report.",
    "Collected 2026-11-24 at 09:15.",
    "Analyser: Roche Cobas c502, lot 4471.",
]

# Must be removed.
IDENTIFIERS = [
    ("Contact priya.rao@example.com for results.", "priya.rao@example.com"),
    ("Call +44 7700 900123 to discuss.", "900123"),
    ("Phone: (020) 7946 0958", "7946"),
    ("Patient ID: SYN0002", "SYN0002"),
    ("MRN 4471928", "4471928"),
    ("NHS No: 943 476 5919", "943"),
    ("DOB: 1984-03-12", "1984-03-12"),
    ("Date of birth 12 March 1984", "1984"),
]


class TestClinicalContentSurvives:

    @pytest.mark.parametrize("line", CLINICAL_LINES)
    def test_a_clinical_line_is_unchanged(self, line):
        assert redact(line) == line, f"redaction altered: {line!r}"

    def test_a_whole_report_body_is_unchanged(self):
        body = "\n".join(CLINICAL_LINES)
        assert redact(body) == body

    def test_a_decimal_is_not_mistaken_for_a_phone_number(self):
        # The phone pattern needs 7+ digits; a lab value never reaches that.
        # Without the decimal guards, "1.05" and "17.5" join across the dot.
        assert redact("Creatinine 1.05 and ferritin 17.5") == (
            "Creatinine 1.05 and ferritin 17.5")

    def test_a_long_run_of_lab_values_is_not_joined_into_a_phone_number(self):
        line = "88 212 450 118 76 13.1 1.05"
        assert redact(line) == line


class TestIdentifiersAreRemoved:

    @pytest.mark.parametrize("text,secret", IDENTIFIERS)
    def test_the_identifier_does_not_survive(self, text, secret):
        assert secret not in redact(text), text

    def test_the_label_is_kept_so_the_trace_still_reads(self):
        # "[id]" alone loses the fact that a patient ID was there at all.
        out = redact("Patient ID: SYN0002")
        assert "Patient ID" in out
        assert redaction.IDENT in out

    def test_an_unlabelled_code_is_left_alone(self):
        # An analyser model or a reagent lot is not a patient identifier, and
        # redacting it would corrupt the trace for no privacy gain.
        assert redact("Analyser Cobas c502") == "Analyser Cobas c502"

    def test_empty_and_non_string_input(self):
        assert redact("") == ""
        assert redact(None) is None
        assert redact(42) == 42


class TestKnownNames:
    """
    A regex cannot find arbitrary names, so the caller passes in the ones it
    knows from the user record and the report.
    """

    def test_a_known_name_is_removed(self):
        out = redact("Priya Rao's glucose is high.", known=["Priya Rao"])
        assert "Priya" not in out
        assert "Rao" not in out

    def test_a_first_name_alone_is_caught_later_in_the_text(self):
        out = redact("Patient Priya Rao. Priya should see her doctor.",
                     known=["Priya Rao"])
        assert "Priya" not in out

    def test_a_full_name_becomes_one_placeholder(self):
        out = redact_known("Priya Rao attended.", ["Priya Rao"])
        assert out == "[name] attended."

    def test_a_very_short_name_is_not_used_as_a_substring(self):
        # A user called "Jo" must not have those letters struck out of
        # "Joint", "Jones" or "major". Below three characters the match does
        # more damage than the leak it prevents.
        out = redact_known("Joint pain reported by Jo.", ["Jo"])
        assert "Joint pain reported by" in out

    def test_a_name_is_matched_whole_word_only(self):
        out = redact_known("Rapid test for Rao.", ["Rao"])
        assert out.startswith("Rapid test for")

    def test_matching_ignores_case(self):
        assert "priya" not in redact_known("priya rao called", ["Priya Rao"]).lower()

    def test_a_name_that_is_also_a_clinical_word_is_the_known_cost(self):
        # Someone surnamed "Glucose" would lose the word from their trace.
        # Recorded rather than fixed: the alternative is leaving real names in,
        # and the caller controls what goes into `known`.
        out = redact_known("Glucose 450 mg/dL", ["Glucose"])
        assert out == "[name] 450 mg/dL"


class TestRedactForTrace:

    def test_it_walks_a_nested_analysis(self):
        analysis = {
            "summary": "Priya Rao's glucose is 450 mg/dL. Call 020 7946 0958.",
            "abnormalities": ["glucose 450 mg/dL"],
            "risk_level": "High",
            "safety": {"medication_advice_removed": ["Priya should stop her meds."]},
        }
        out = redact_for_trace(analysis, known=["Priya Rao"])
        assert "Priya" not in str(out)
        assert "7946" not in str(out)
        # The clinical content is the reason the trace exists.
        assert "450 mg/dL" in out["summary"]
        assert out["abnormalities"] == ["glucose 450 mg/dL"]
        assert out["risk_level"] == "High"

    def test_keys_are_not_redacted(self):
        out = redact_for_trace({"patient id": "SYN0002"}, known=[])
        assert "patient id" in out

    def test_non_text_values_pass_through(self):
        out = redact_for_trace({"n": 30, "rate": 0.333, "ok": True, "none": None})
        assert out == {"n": 30, "rate": 0.333, "ok": True, "none": None}

    def test_a_list_keeps_its_type(self):
        assert isinstance(redact_for_trace(["a", "b"]), list)
        assert isinstance(redact_for_trace(("a", "b")), tuple)
