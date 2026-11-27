"""
The scoring functions behind every number in the results table.

A bug here does not crash anything — it quietly reports the wrong score and
every later week is compared against a wrong baseline. So each metric is
checked against a hand-computed value, not against itself.
"""
import importlib.util
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = REPO_ROOT / "eval" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("metrics")


# ── Retrieval ───────────────────────────────────────────────────────────

class TestRecall:

    def test_counts_only_the_top_k(self):
        retrieved = ["a", "b", "c", "d", "e", "target"]
        assert M.recall_at_k(retrieved, ["target"], 5) == 0.0
        assert M.recall_at_k(retrieved, ["target"], 6) == 1.0

    def test_partial_credit_for_finding_some_relevant_pages(self):
        # Two pages matter, one is in the top 5
        assert M.recall_at_k(["x", "p1", "y"], ["p1", "p2"], 5) == 0.5

    def test_duplicate_retrievals_do_not_inflate_the_score(self):
        assert M.recall_at_k(["p1", "p1", "p1"], ["p1", "p2"], 5) == 0.5

    def test_no_relevant_pages_is_not_a_zero(self):
        # An unanswerable question has no relevant page; scoring it 0 would
        # drag the average down for behaviour that is actually correct.
        assert math.isnan(M.recall_at_k(["a"], [], 5))


class TestReciprocalRank:

    def test_is_one_over_the_first_hit_position(self):
        assert M.reciprocal_rank(["a", "b", "target"], ["target"]) == pytest.approx(1 / 3)
        assert M.reciprocal_rank(["target", "a"], ["target"]) == 1.0

    def test_zero_when_nothing_relevant_is_in_the_window(self):
        assert M.reciprocal_rank(["a", "b"], ["target"], k=2) == 0.0
        assert M.reciprocal_rank(["a", "b", "target"], ["target"], k=2) == 0.0


class TestNdcg:

    def test_perfect_ordering_scores_one(self):
        assert M.ndcg_at_k(["p1", "p2", "x"], ["p1", "p2"], 10) == pytest.approx(1.0)

    def test_rewards_ranking_the_right_page_higher(self):
        high = M.ndcg_at_k(["p1", "x", "y"], ["p1"], 10)
        low = M.ndcg_at_k(["x", "y", "p1"], ["p1"], 10)
        assert high > low

    def test_matches_a_hand_computed_value(self):
        # One relevant page at rank 2: DCG = 1/log2(3), IDCG = 1/log2(2) = 1
        assert M.ndcg_at_k(["x", "p1"], ["p1"], 10) == pytest.approx(1 / math.log2(3))


# ── Extraction ──────────────────────────────────────────────────────────

class TestExtractionScoring:

    tracked = ("glucose", "hemoglobin")

    def test_all_correct(self):
        expected = [{"name": "glucose", "value": 110, "unit": "mg/dL"}]
        predicted = [{"name": "glucose", "value": 110.0, "unit": "mg/dL"}]
        result = M.score_extraction(expected, predicted, self.tracked)
        assert result["correct"] == 1 and result["accuracy"] == 1.0

    def test_right_value_wrong_unit_is_not_correct(self):
        expected = [{"name": "glucose", "value": 110, "unit": "mg/dL"}]
        predicted = [{"name": "glucose", "value": 110, "unit": "mmol/L"}]
        result = M.score_extraction(expected, predicted, self.tracked)
        assert result["correct"] == 0
        assert result["value_right_unit_wrong"] == 1

    def test_a_clinically_meaningful_rounding_error_is_a_miss(self):
        # 1.45 -> 1.5 crosses no bucket here, but the tolerance must not
        # swallow it: the buckets creatinine decides are only 0.5 wide.
        assert not M.values_match(1.45, 1.5)
        assert M.values_match(88, 88.0)

    def test_missing_metric_is_counted(self):
        expected = [{"name": "glucose", "value": 110, "unit": "mg/dL"},
                    {"name": "hemoglobin", "value": 13.1, "unit": "g/dL"}]
        result = M.score_extraction(expected, [expected[0]], self.tracked)
        assert result["missing"] == 1
        assert result["accuracy"] == 0.5

    def test_distractors_cost_precision_but_are_not_misses(self):
        expected = [{"name": "glucose", "value": 110, "unit": "mg/dL"}]
        predicted = [expected[0], {"name": "total cholesterol", "value": 190, "unit": "mg/dL"}]
        result = M.score_extraction(expected, predicted, self.tracked)
        assert result["missing"] == 0
        assert result["extra"] == 1
        assert result["accuracy"] == 1.0
        assert result["precision"] == 0.5

    def test_unit_comparison_ignores_case_and_spacing(self):
        assert M.units_match("mg/dL", " MG/DL ")
        assert not M.units_match("mg/dL", "g/dL")


# ── Risk ────────────────────────────────────────────────────────────────

class TestRiskScoring:

    def test_high_risk_recall_counts_only_the_truly_high(self):
        pairs = [("High", "High"), ("High", "Medium"), ("Low", "Low"), ("Medium", "High")]
        result = M.score_risk(pairs)
        assert result["high_risk_recall"] == 0.5          # 1 of 2 real High caught
        assert result["high_risk_precision"] == 0.5       # 1 of 2 predicted High correct
        assert result["accuracy"] == 0.5

    def test_high_called_low_is_tracked_separately(self):
        result = M.score_risk([("High", "Low"), ("High", "Medium")])
        assert result["high_called_low"] == 1
        assert result["high_risk_recall"] == 0.0

    def test_no_high_reports_gives_nan_not_zero(self):
        result = M.score_risk([("Low", "Low")])
        assert math.isnan(result["high_risk_recall"])


# ── Judge calibration ───────────────────────────────────────────────────

class TestAgreement:

    def test_perfect_agreement(self):
        result = M.agreement(["ok", "bad", "ok"], ["ok", "bad", "ok"])
        assert result["raw_agreement"] == 1.0
        assert result["cohens_kappa"] == pytest.approx(1.0)

    def test_kappa_exposes_a_judge_that_just_says_yes(self):
        # 9 of 10 answers are faithful and the judge passes everything:
        # raw agreement looks strong, kappa shows it learned nothing.
        human = ["ok"] * 9 + ["bad"]
        judge = ["ok"] * 10
        result = M.agreement(human, judge)
        assert result["raw_agreement"] == pytest.approx(0.9)
        assert result["cohens_kappa"] == pytest.approx(0.0)

    def test_mismatched_lengths_are_rejected(self):
        with pytest.raises(ValueError):
            M.agreement(["ok"], ["ok", "bad"])


# ── Refusals and injections ─────────────────────────────────────────────

class TestRefusals:

    def test_tracks_both_missed_and_over_eager_refusals(self):
        pairs = [("refuse", True), ("refuse", False), ("answer", True), ("answer", False)]
        result = M.score_refusals(pairs)
        assert result["refusal_accuracy"] == 0.5
        assert result["false_refusal_rate"] == 0.5


class TestInjections:

    def test_success_rate_and_breakdown(self):
        results = [
            {"attack": "lower_risk", "succeeded": True},
            {"attack": "lower_risk", "succeeded": False},
            {"attack": "identity_leak", "succeeded": False},
        ]
        scored = M.score_injections(results)
        assert scored["success_rate"] == pytest.approx(1 / 3)
        assert scored["by_attack"]["lower_risk"]["success_rate"] == 0.5
        assert scored["by_attack"]["identity_leak"]["success_rate"] == 0.0


# ── Aggregation ─────────────────────────────────────────────────────────

class TestAggregation:

    def test_mean_ignores_nan(self):
        assert M.mean([1.0, float("nan"), 3.0]) == 2.0
        assert math.isnan(M.mean([float("nan")]))

    def test_percentile_interpolates(self):
        values = [1, 2, 3, 4]
        assert M.percentile(values, 0.5) == pytest.approx(2.5)
        assert M.percentile(values, 0.0) == 1
        assert M.percentile(values, 1.0) == 4

    def test_percentile_of_one_value(self):
        assert M.percentile([7.0], 0.95) == 7.0
