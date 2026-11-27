"""
Check a results file against the floors in eval/gate.toml.

    python eval/check_gate.py eval/results/2026-11-27_baseline.json

Exit 0 when every floor and relation holds, 1 when any fails, 2 when the gate
could not be evaluated at all - a missing metric, an unreadable file, a stage
that did not run. The third case exits non-zero on purpose: a gate that cannot
find its numbers has not passed, and the most likely reason for a metric to go
missing is that someone removed the stage that produced it.

Writes a Markdown table to $GITHUB_STEP_SUMMARY when that is set, so the
result is readable from the pull request without opening the log.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "eval" / "gate.toml"

MISSING = object()


def dig(data: Any, dotted: str) -> Any:
    """Follow a dotted path into nested dicts, or return MISSING."""
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def _fmt(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="a results JSON file from run_eval.py")
    parser.add_argument("--gate", default=str(GATE))
    args = parser.parse_args()

    try:
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"GATE ERROR: cannot read {args.results}: {exc}")
        return 2

    gate = tomllib.loads(Path(args.gate).read_text(encoding="utf-8"))

    rows: list[tuple[str, str, str, str, str]] = []
    failures: list[str] = []
    errors: list[str] = []

    for spec in gate.get("metrics", []):
        value = dig(results, spec["path"])
        floor = spec["floor"]
        if value is MISSING:
            errors.append(f"{spec['name']}: no value at {spec['path']}")
            rows.append((spec["name"], "-", _fmt(floor), "MISSING", spec["path"]))
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"{spec['name']}: {spec['path']} is not a number")
            rows.append((spec["name"], str(value), _fmt(floor), "MISSING", spec["path"]))
            continue
        ok = value >= floor
        if not ok:
            failures.append(
                f"{spec['name']}: {value:.3f} is below the floor {floor:.3f} "
                f"(baseline {spec.get('measured', float('nan')):.3f})")
        rows.append((spec["name"], _fmt(value), _fmt(floor),
                     "PASS" if ok else "FAIL", spec["path"]))

    for rel in gate.get("relations", []):
        left, right = dig(results, rel["left"]), dig(results, rel["right"])
        if MISSING in (left, right) or not all(
                isinstance(v, (int, float)) for v in (left, right)):
            errors.append(f"{rel['name']}: missing {rel['left']} or {rel['right']}")
            rows.append((rel["name"], "-", f"gap >= {rel['min_gap']:.3f}",
                         "MISSING", "relation"))
            continue
        gap = left - right
        ok = gap >= rel["min_gap"]
        if not ok:
            failures.append(
                f"{rel['name']}: gap {gap:.3f} is under the required "
                f"{rel['min_gap']:.3f} ({rel['left']} {left:.3f} vs "
                f"{rel['right']} {right:.3f})")
        rows.append((rel["name"], f"gap {gap:+.3f}",
                     f">= {rel['min_gap']:.3f}", "PASS" if ok else "FAIL",
                     "relation"))

    label = dig(results, "run.label")
    commit = dig(results, "run.git_commit")
    header = f"CareAI quality gate - {args.results}"
    if label is not MISSING:
        header += f" (label {label}"
        header += f", {commit})" if commit is not MISSING else ")"

    print(header)
    print("=" * len(header))
    width = max(len(r[0]) for r in rows) if rows else 10
    for name, value, bound, verdict, _ in rows:
        print(f"  {verdict:8s} {name:<{width}}  {value:>10}  (floor {bound})")

    for problem in failures:
        print(f"\nFAIL: {problem}")
    for problem in errors:
        print(f"\nERROR: {problem}")

    _write_summary(header, rows, failures, errors)

    if errors:
        print("\nThe gate could not be evaluated. That is not a pass: a stage "
              "that stops emitting a metric looks identical to one that was "
              "never run.")
        return 2
    if failures:
        print(f"\n{len(failures)} check(s) failed. If the drop is intended, "
              f"move the floor in eval/gate.toml in a commit that says why.")
        return 1
    print(f"\nAll {len(rows)} checks passed.")
    return 0


def _write_summary(header, rows, failures, errors) -> None:
    """A Markdown table in the PR's checks summary, when running on CI."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    icon = {"PASS": "✅", "FAIL": "❌", "MISSING": "⚠️"}
    lines = [f"## {'❌' if failures or errors else '✅'} {header}", "",
             "| | Check | Value | Bound |", "| --- | --- | --- | --- |"]
    lines += [f"| {icon[v]} | {n} | `{val}` | `{b}` |" for n, val, b, v, _ in rows]
    if failures or errors:
        lines += ["", "### Problems", ""]
        lines += [f"- {p}" for p in failures + errors]
        lines += ["", "A floor is an absolute value. If a drop is intended, "
                  "change it in `eval/gate.toml` and say why in the commit."]
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as exc:        # never fail the gate over its own report
        print(f"(could not write the step summary: {exc})")


if __name__ == "__main__":
    sys.exit(main())
