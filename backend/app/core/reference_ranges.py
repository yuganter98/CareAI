"""
Clinical reference ranges, and the risk level implied by a set of values.

This is the single definition for the backend. `app/analytics` and
`app/agents/risk_floor.py` both read it from here; `eval/ranges.py` keeps a
copy so the corpus generator runs without the backend's dependencies, and
`tests/test_eval_groundwork.py` fails if the two drift apart.

A note on what this table is and is not
---------------------------------------
These are ordinary adult reference ranges, the same ones the app has used for
its insights feature since before any of the evaluation work. They are not
tuned to anything: `risk_floor` reuses them precisely because they predate it.

They are also not a clinical grading system. Real triage accounts for age,
sex, pregnancy, dialysis, known chronic disease and the trend over time, none
of which CareAI has. A single value crossing a threshold is a reason to show
a warning, never a diagnosis, which is why the floor these feed can only
*raise* a risk level and never settle a clinical question.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

INF = float("inf")

# metric -> {bucket: (low, high)} plus the unit it is reported in.
# A value belongs to the first bucket, checked critical -> normal, whose
# half-open interval [low, high) contains it.
REFERENCE_RANGES: Dict[str, Dict] = {
    "glucose": {
        "normal":     (70,  100),
        "borderline": (100, 126),
        "elevated":   (126, 200),
        "critical":   (200, INF),
        "unit": "mg/dL",
    },
    "hemoglobin": {
        "critical":   (0,   7),
        "elevated":   (7,   11),    # low side reused as "borderline low"
        "borderline": (11,  12),
        "normal":     (12,  17.5),
        "unit": "g/dL",
    },
    "creatinine": {
        "normal":     (0.7, 1.3),
        "borderline": (1.3, 1.8),
        "elevated":   (1.8, 3.0),
        "critical":   (3.0, INF),
        "unit": "mg/dL",
    },
    "blood_pressure_systolic": {
        "normal":     (90,  120),
        "borderline": (120, 130),
        "elevated":   (130, 180),
        "critical":   (180, INF),
        "unit": "mmHg",
    },
    "blood_pressure_diastolic": {
        "normal":     (60,  80),
        "borderline": (80,  90),
        "elevated":   (90,  120),
        "critical":   (120, INF),
        "unit": "mmHg",
    },
}

BUCKET_ORDER = ("critical", "elevated", "borderline", "normal")

# How alarming each bucket is, so callers can take a worst case.
BUCKET_SEVERITY = {"normal": 0, "borderline": 1, "elevated": 2, "critical": 3}

RISK_SEVERITY = {"Low": 0, "Medium": 1, "High": 2}


def assess(metric: str, value: float) -> str:
    """Which reference bucket a value falls into."""
    ranges = REFERENCE_RANGES.get(metric.lower())
    if not ranges:
        return "normal"
    for bucket in BUCKET_ORDER:
        bounds: Tuple[float, float] = ranges.get(bucket, (None, None))
        lo, hi = bounds
        if lo is not None and lo <= value < hi:
            return bucket
    return "normal"


def risk_from_buckets(buckets: Iterable[str]) -> str:
    """
    The risk level a set of values implies.

        any critical value  -> High
        any elevated value  -> Medium
        otherwise           -> Low
    """
    buckets = list(buckets)
    if "critical" in buckets:
        return "High"
    if "elevated" in buckets:
        return "Medium"
    return "Low"
