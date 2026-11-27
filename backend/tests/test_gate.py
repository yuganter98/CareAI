"""
The CI quality gate.

A gate that cannot go red is decoration, and nobody notices a gate that stops
working - it keeps reporting green. So these tests feed it regressions and
require it to fail, rather than only checking that good numbers pass.

The case that matters most is the third one: a *missing* metric must not be
treated as a pass. A stage that stops emitting a number looks exactly like a
stage nobody ran, and the obvious implementation - `results.get(path, 0) >=
floor` or a `try/except` around the lookup - turns a deleted stage into a
green build.
"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_TOML = REPO_ROOT / "eval" / "gate.toml"
CHECK_GATE = REPO_ROOT / "eval" / "check_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_gate", CHECK_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = _load()


def _passing_results():
    """The Week 2 numbers, in the shape run_eval.py writes."""
    def path(recall, mrr=0.230, ndcg=0.285, held=0.281):
        return {"overall": {"n": 80, "recall_at_5": recall,
                            "mrr_at_10": mrr, "ndcg_at_10": ndcg},
                "held_out": {"n": 16, "recall_at_5": held}}
    return {
        "run": {"label": "test", "git_commit": "abc1234"},
        "retrieval": {
            "copilot_path_before": path(0.012, 0.005, 0.008, 0.0),
            "patient_filtered": path(0.300),
            "dense_filtered": path(0.300),
        },
    }


def _run(results, tmp_path):
    """Run the gate as CI does, and return (exit code, stdout)."""
    target = tmp_path / "results.json"
    target.write_text(json.dumps(results), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CHECK_GATE), str(target)],
        capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


class TestTheGateHolds:

    def test_the_baseline_numbers_pass(self, tmp_path):
        code, out = _run(_passing_results(), tmp_path)
        assert code == 0, out
        assert "All 7 checks passed" in out

    def test_the_real_results_file_passes(self):
        # Guards against gate.toml's paths drifting from the harness's output
        # shape - the failure that would otherwise show up as MISSING on CI,
        # long after the change that caused it.
        real = sorted((REPO_ROOT / "eval" / "results").glob("*_citiming.json"))
        if not real:
            pytest.skip("no local retrieval results to check against")
        proc = subprocess.run(
            [sys.executable, str(CHECK_GATE), str(real[-1])],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestTheGateFails:

    def test_a_recall_regression_turns_it_red(self, tmp_path):
        results = copy.deepcopy(_passing_results())
        results["retrieval"]["dense_filtered"]["overall"]["recall_at_5"] = 0.20
        code, out = _run(results, tmp_path)
        assert code == 1, out
        assert "below the floor" in out

    def test_a_drop_inside_the_margin_still_passes(self, tmp_path):
        # 0.28 is under the 0.300 baseline but above the 0.270 floor. The
        # margin exists so a corpus regeneration does not block a PR.
        #
        # Both paths move together, because they are the same retrieval over
        # the same corpus - dropping only one is the over-fetch regression,
        # covered below. Writing this test the lazy way failed for exactly
        # that reason, which is the relation doing its job.
        results = copy.deepcopy(_passing_results())
        for path in ("dense_filtered", "patient_filtered"):
            results["retrieval"][path]["overall"]["recall_at_5"] = 0.28
        code, out = _run(results, tmp_path)
        assert code == 0, out

    def test_the_ownership_bug_coming_back_turns_it_red(self, tmp_path):
        # The original bug: FAISS's global top_k taken before the ownership
        # filter. Recall collapses to the pre-fix path's level, so the
        # relation check catches it as well as the floor.
        results = copy.deepcopy(_passing_results())
        results["retrieval"]["dense_filtered"]["overall"]["recall_at_5"] = 0.012
        code, out = _run(results, tmp_path)
        assert code == 1, out
        assert "beats the pre-fix path" in out

    def test_over_fetch_truncating_turns_it_red(self, tmp_path):
        # dense_filtered below the exhaustive scan means the adaptive fetch
        # loop gave up early. Both stay above their floors, so only the
        # relation catches this one - which is why relations exist.
        results = copy.deepcopy(_passing_results())
        results["retrieval"]["dense_filtered"]["overall"]["recall_at_5"] = 0.28
        results["retrieval"]["patient_filtered"]["overall"]["recall_at_5"] = 0.30
        code, out = _run(results, tmp_path)
        assert code == 1, out
        assert "over-fetch loses nothing" in out

    def test_a_held_out_collapse_turns_it_red(self, tmp_path):
        # The tuning split can be fitted; the held-out split is the check that
        # a change generalises, so it is gated on its own.
        results = copy.deepcopy(_passing_results())
        results["retrieval"]["dense_filtered"]["held_out"]["recall_at_5"] = 0.0
        code, out = _run(results, tmp_path)
        assert code == 1, out
        assert "held-out" in out


class TestAMissingMetricIsNotAPass:

    def test_a_deleted_stage_exits_non_zero(self, tmp_path):
        results = copy.deepcopy(_passing_results())
        del results["retrieval"]
        code, out = _run(results, tmp_path)
        assert code == 2, out
        assert "could not be evaluated" in out

    def test_a_deleted_retrieval_path_exits_non_zero(self, tmp_path):
        # Someone removes copilot_path_before because it "isn't shipped".
        # That is the comparison proving the bug is fixed; losing it quietly
        # would be worse than a red build.
        results = copy.deepcopy(_passing_results())
        del results["retrieval"]["copilot_path_before"]
        code, out = _run(results, tmp_path)
        assert code == 2, out

    def test_a_renamed_metric_exits_non_zero(self, tmp_path):
        results = copy.deepcopy(_passing_results())
        overall = results["retrieval"]["dense_filtered"]["overall"]
        overall["recall5"] = overall.pop("recall_at_5")
        code, out = _run(results, tmp_path)
        assert code == 2, out

    def test_a_null_metric_exits_non_zero(self, tmp_path):
        # None >= 0.27 raises a TypeError rather than comparing false, so an
        # unguarded gate crashes here instead of reporting.
        results = copy.deepcopy(_passing_results())
        results["retrieval"]["dense_filtered"]["overall"]["recall_at_5"] = None
        code, out = _run(results, tmp_path)
        assert code == 2, out

    def test_an_unreadable_file_exits_non_zero(self, tmp_path):
        target = tmp_path / "results.json"
        target.write_text("{not json", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(CHECK_GATE), str(target)],
            capture_output=True, text=True)
        assert proc.returncode == 2
        assert "cannot read" in proc.stdout

    def test_a_missing_file_exits_non_zero(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(CHECK_GATE), str(tmp_path / "nope.json")],
            capture_output=True, text=True)
        assert proc.returncode == 2


class TestTheGateConfig:

    def test_every_floor_sits_below_its_measured_baseline(self):
        import tomllib
        gate = tomllib.loads(GATE_TOML.read_text(encoding="utf-8"))
        for spec in gate["metrics"]:
            assert spec["floor"] <= spec["measured"], spec["name"]
            # A floor far under the baseline is a gate that never fires. 25%
            # of the measured value is already very loose.
            assert spec["floor"] >= spec["measured"] * 0.70, (
                f"{spec['name']}: floor {spec['floor']} is more than 30% "
                f"below the measured {spec['measured']}")

    def test_the_dig_helper_does_not_confuse_missing_with_falsy(self):
        # A metric of 0.0 is a real measurement and must reach the comparison
        # (where it fails); only an absent key is MISSING.
        assert G.dig({"a": {"b": 0.0}}, "a.b") == 0.0
        assert G.dig({"a": {"b": 0.0}}, "a.c") is G.MISSING
        assert G.dig({"a": 5}, "a.b") is G.MISSING
        assert G.dig({}, "a") is G.MISSING
