"""
Clinical reference ranges and the deterministic risk rule used by the eval set.

These mirror `backend/app/analytics/personalized_insights.REFERENCE_RANGES`.
They are duplicated rather than imported so the generator runs without the
backend's dependencies; `backend/tests/test_eval_ranges.py` fails if the two
ever drift apart.
"""

from typing import Dict, Tuple

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

# The metrics CareAI is expected to extract. Anything else printed on a report
# is a distractor: it should not be scored as a miss.
TRACKED_METRICS = tuple(REFERENCE_RANGES)

BUCKET_ORDER = ("critical", "elevated", "borderline", "normal")


def assess(metric: str, value: float) -> str:
    """Which reference bucket a value falls into. Mirrors the app's `_assess`."""
    ranges = REFERENCE_RANGES.get(metric.lower())
    if not ranges:
        return "normal"
    for bucket in BUCKET_ORDER:
        bounds: Tuple[float, float] = ranges.get(bucket, (None, None))
        lo, hi = bounds
        if lo is not None and lo <= value < hi:
            return bucket
    return "normal"


def expected_risk(buckets) -> str:
    """
    The risk level a report should be given, from its values alone.

    Deterministic by design: it is the label the eval set scores against, and
    in Week 5 the same rule becomes the floor the LLM may raise but not lower.

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


def reference_text(metric: str) -> str:
    """The normal range as printed on a report, e.g. '70 - 100'."""
    lo, hi = REFERENCE_RANGES[metric]["normal"]
    return f"{_fmt(lo)} - {_fmt(hi)}"


def flag_for(bucket: str, metric: str, value: float) -> str:
    """The H/L/CRITICAL flag a lab would print beside the value."""
    if bucket == "normal":
        return ""
    lo, hi = REFERENCE_RANGES[metric]["normal"]
    side = "L" if value < lo else "H"
    return "CRITICAL " + side if bucket == "critical" else side


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)
