"""
Is the difference between two retrieval paths real, or is it 80 questions?

A results file gives means. A mean of 38.8% against 30.0% on n=80 looks like a
win and may be nothing. This runs a paired bootstrap over the per-question
scores both paths produced for the *same* questions, and prints the difference
with a 95% confidence interval.

Paired, because the pairing is the point: the same question scored by both
paths removes the variance from some questions simply being harder, which is
the dominant source of noise in a set this size.

    python eval/compare.py eval/results/2026-11-27_week2.json
    python eval/compare.py <file> --metric mrr_at_10 --by-type
"""
import argparse
import json
import random
import statistics
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional

ITERATIONS = 20000
SEED = 7


def load_paths(path: Path) -> Dict[str, Dict[str, dict]]:
    """{path name: {question id: row}} from a results file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    retrieval = data.get("retrieval")
    if not retrieval:
        raise SystemExit(f"{path} has no retrieval stage.")

    out: Dict[str, Dict[str, dict]] = {}
    for name, body in retrieval.items():
        rows = body.get("per_question")
        if not rows:
            raise SystemExit(
                f"'{name}' has no per_question rows. Re-run the retrieval "
                "stage with the current eval/run_eval.py.")
        out[name] = {r["id"]: r for r in rows}
    return out


def paired_bootstrap(a: Dict[str, dict], b: Dict[str, dict], metric: str,
                     question_type: Optional[str] = None,
                     iterations: int = ITERATIONS, seed: int = SEED) -> Optional[dict]:
    """Mean of (b - a) per question, with a bootstrap CI and a two-sided p."""
    ids = [i for i in a if i in b
           and (question_type is None or a[i]["type"] == question_type)]
    # NaN means the metric does not apply to that question (an unanswerable
    # one has no relevant page); excluded rather than counted as zero.
    diffs = [b[i][metric] - a[i][metric] for i in ids
             if a[i][metric] == a[i][metric] and b[i][metric] == b[i][metric]]
    if len(diffs) < 2:
        return None

    observed = statistics.fmean(diffs)
    rnd = random.Random(seed)
    means = sorted(statistics.fmean(rnd.choices(diffs, k=len(diffs)))
                   for _ in range(iterations))
    lo = means[int(0.025 * iterations)]
    hi = means[int(0.975 * iterations)]
    below = sum(1 for m in means if m <= 0) / iterations
    return {
        "n": len(diffs),
        "diff": observed,
        "ci_low": lo,
        "ci_high": hi,
        # The share of resamples on the far side of zero, doubled. A CI that
        # contains zero is the same statement; both are printed because the
        # interval says how large the effect might be and p does not.
        "p": 2 * min(below, 1 - below),
    }


def print_table(result_rows: List[tuple], metric: str, scale: float, unit: str) -> None:
    print(f"\nB minus A, {metric}, paired bootstrap, 95% CI\n")
    print(f"{'comparison':46} {'n':>3} {'diff':>9} {'95% CI':>20} {'p':>6}")
    print("-" * 88)
    for label, r in result_rows:
        if r is None:
            print(f"{label:46}   -  (too few comparable questions)")
            continue
        ci = f"[{r['ci_low'] * scale:+6.1f},{r['ci_high'] * scale:+6.1f}]{unit}"
        flag = "" if r["p"] >= 0.05 else "  *"
        print(f"{label:46} {r['n']:3} {r['diff'] * scale:+8.1f}{unit} {ci:>20} "
              f"{r['p']:6.3f}{flag}")
    print("\n* difference survives at p < 0.05. Everything else is within the "
          "noise of this question set.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path)
    parser.add_argument("--metric", default="recall_at_5",
                        choices=("recall_at_5", "mrr_at_10", "ndcg_at_10"))
    parser.add_argument("--paths", nargs="*",
                        help="limit to these paths (default: every pair)")
    parser.add_argument("--by-type", action="store_true",
                        help="also break each comparison down by question type")
    args = parser.parse_args()

    paths = load_paths(args.results)
    if args.paths:
        missing = [p for p in args.paths if p not in paths]
        if missing:
            raise SystemExit(f"Not in the file: {', '.join(missing)}. "
                             f"Available: {', '.join(sorted(paths))}")
        names = args.paths
    else:
        names = sorted(paths)

    scale, unit = (100.0, "pp") if args.metric == "recall_at_5" else (1.0, "  ")

    rows: List[tuple] = []
    for a, b in combinations(names, 2):
        rows.append((f"{a} -> {b}  [all]",
                     paired_bootstrap(paths[a], paths[b], args.metric)))
        if args.by_type:
            types = sorted({r["type"] for r in paths[a].values()})
            for kind in types:
                rows.append((f"{a} -> {b}  [{kind}]",
                             paired_bootstrap(paths[a], paths[b], args.metric, kind)))

    print_table(rows, args.metric, scale, unit)


if __name__ == "__main__":
    main()
