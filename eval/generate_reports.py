"""
Synthetic lab-report generator for the CareAI eval set.

Renders lab-report PDFs for synthetic patients and writes, beside each PDF, a
JSON file holding every value it printed and the page it printed it on. Because
the generator knows the truth it wrote, the extraction and risk test sets need
no hand-labelling.

    python eval/generate_reports.py                 # default corpus
    python eval/generate_reports.py --patients 5    # quick run
    python eval/generate_reports.py --out /tmp/x    # elsewhere

Deterministic: the same --seed always produces the same corpus.

All patients, names and values are invented. Never put real patient data here.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ranges import (  # noqa: E402
    REFERENCE_RANGES,
    TRACKED_METRICS,
    assess,
    expected_risk,
    flag_for,
    reference_text,
)

# ── Synthetic identities ────────────────────────────────────────────────

FIRST_NAMES = {
    "M": ["Aarav", "Rohan", "Kabir", "Vikram", "Arjun", "Dev", "Imran", "Omar"],
    "F": ["Diya", "Meera", "Ananya", "Priya", "Nisha", "Sana", "Lata", "Farah"],
}
LAST_NAMES = [
    "Sharma", "Patel", "Nair", "Reddy", "Khan", "Iyer", "Bose", "Mehta",
    "Gupta", "Chopra", "Rao", "Das",
]
LABS = [
    ("Meridian Diagnostics", "Mumbai"),
    ("Northline Pathology Labs", "Pune"),
    ("Cedar Clinical Laboratory", "Bengaluru"),
]

# Each profile sets, per metric, a starting value and a per-report drift.
# Profiles are what put abnormal and critical values in the corpus on purpose.
PROFILES: Dict[str, Dict[str, tuple]] = {
    # name:              metric: (start, drift per report)
    "healthy": {
        "glucose": (88, 0.3), "hemoglobin": (14.2, -0.01), "creatinine": (0.95, 0.002),
        "blood_pressure_systolic": (116, 0.2), "blood_pressure_diastolic": (74, 0.1),
    },
    "prediabetic_worsening": {
        "glucose": (104, 4.2), "hemoglobin": (13.8, -0.02), "creatinine": (1.0, 0.01),
        "blood_pressure_systolic": (124, 0.9), "blood_pressure_diastolic": (79, 0.4),
    },
    "diabetic_uncontrolled": {
        "glucose": (158, 6.5), "hemoglobin": (13.1, -0.05), "creatinine": (1.2, 0.05),
        "blood_pressure_systolic": (134, 1.4), "blood_pressure_diastolic": (85, 0.6),
    },
    "anemia_progressing": {
        "glucose": (92, 0.4), "hemoglobin": (11.6, -0.28), "creatinine": (0.9, 0.004),
        "blood_pressure_systolic": (112, 0.3), "blood_pressure_diastolic": (71, 0.1),
    },
    "renal_decline": {
        "glucose": (108, 1.1), "hemoglobin": (12.4, -0.08), "creatinine": (1.45, 0.075),
        "blood_pressure_systolic": (138, 1.1), "blood_pressure_diastolic": (88, 0.5),
    },
    "hypertensive": {
        "glucose": (96, 0.6), "hemoglobin": (14.0, -0.02), "creatinine": (1.05, 0.008),
        "blood_pressure_systolic": (142, 1.9), "blood_pressure_diastolic": (91, 0.9),
    },
    "recovering": {  # starts abnormal, improves — tests "is my X getting better?"
        "glucose": (171, -3.4), "hemoglobin": (10.8, 0.16), "creatinine": (1.6, -0.03),
        "blood_pressure_systolic": (147, -1.3), "blood_pressure_diastolic": (94, -0.7),
    },
}

# Values printed on reports that CareAI is not asked to track. They exist so
# extraction precision is measurable: pulling these out is noise, not a win.
DISTRACTOR_TESTS = [
    ("Total Cholesterol", "mg/dL", 140, 240, 0),
    ("Platelet Count", "x10^3/uL", 150, 410, 0),
    ("Serum Sodium", "mEq/L", 134, 145, 0),
    ("TSH", "uIU/mL", 0.5, 4.5, 2),
]

DECIMALS = {
    "glucose": 0, "hemoglobin": 1, "creatinine": 2,
    "blood_pressure_systolic": 0, "blood_pressure_diastolic": 0,
}

# A long trend would otherwise run off the end of what a living patient can
# show. These bounds keep values clinically plausible while still reaching the
# critical bucket, so a reviewer never sees a number no lab would print.
PLAUSIBLE_RANGE = {
    "glucose": (45, 520),
    "hemoglobin": (4.5, 20.0),
    "creatinine": (0.3, 9.0),
    "blood_pressure_systolic": (80, 215),
    "blood_pressure_diastolic": (45, 135),
}
DISPLAY_NAMES = {
    "glucose": "Glucose, Fasting",
    "hemoglobin": "Hemoglobin",
    "creatinine": "Creatinine, Serum",
}

# Which page each panel is printed on. Page 2 exists so page-level citation
# accuracy is measurable: a glucose question must cite page 2, not page 1.
PAGE_OF = {
    "hemoglobin": 1,
    "glucose": 2,
    "creatinine": 2,
    "blood_pressure_systolic": 2,
    "blood_pressure_diastolic": 2,
}


# ── Value synthesis ─────────────────────────────────────────────────────

def _round(metric: str, value: float):
    """Round to the precision a lab prints. Whole-number metrics stay ints."""
    places = DECIMALS[metric]
    return int(round(value)) if places == 0 else round(value, places)


def build_patient(rng: random.Random, n: int) -> dict:
    profile = list(PROFILES)[n % len(PROFILES)]
    lab, city = LABS[n % len(LABS)]
    sex = rng.choice(["M", "F"])
    return {
        "patient_id": f"SYN{n:04d}",
        "name": f"{rng.choice(FIRST_NAMES[sex])} {rng.choice(LAST_NAMES)}",
        "age": rng.randint(28, 74),
        "sex": sex,
        "profile": profile,
        "lab": lab,
        "city": city,
    }


def build_readings(rng: random.Random, profile: str, step: int) -> Dict[str, float]:
    """Values for one report: profile trend plus small per-visit noise."""
    out = {}
    for metric, (start, drift) in PROFILES[profile].items():
        noise = rng.gauss(0, max(abs(start) * 0.012, 0.02))
        low, high = PLAUSIBLE_RANGE[metric]
        value = min(max(start + drift * step + noise, low), high)
        out[metric] = _round(metric, value)
    return out


def build_report(patient: dict, step: int, report_date: date, rng: random.Random) -> dict:
    readings = build_readings(rng, patient["profile"], step)

    metrics = []
    for metric in TRACKED_METRICS:
        value = readings[metric]
        bucket = assess(metric, value)
        metrics.append({
            "name": metric,
            "value": value,
            "unit": REFERENCE_RANGES[metric]["unit"],
            "page": PAGE_OF[metric],
            "bucket": bucket,
            "flag": flag_for(bucket, metric, value),
        })

    distractors = []
    for label, unit, lo, hi, places in DISTRACTOR_TESTS:
        val = round(rng.uniform(lo, hi), places)
        distractors.append({
            "label": label,
            "value": int(val) if places == 0 else val,
            "unit": unit,
            "page": 1,
        })

    return {
        "report_id": f"{patient['patient_id']}-R{step + 1:02d}",
        "patient_id": patient["patient_id"],
        "patient_name": patient["name"],
        "profile": patient["profile"],
        "collected_on": report_date.isoformat(),
        "metrics": metrics,
        "distractors": distractors,
        "expected_risk": expected_risk(m["bucket"] for m in metrics),
        "pages": 2,
        "source": "synthetic",
    }


# ── PDF rendering ───────────────────────────────────────────────────────

def render_pdf(report: dict, patient: dict, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    width, height = A4
    c = canvas.Canvas(str(path), pagesize=A4)

    def header(subtitle: str) -> float:
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20 * mm, height - 20 * mm, patient["lab"])
        c.setFont("Helvetica", 8.5)
        c.drawString(20 * mm, height - 25 * mm, f"{patient['city']} · Accredited clinical laboratory")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, height - 35 * mm, subtitle)

        c.setFont("Helvetica", 9.5)
        y = height - 43 * mm
        for label, value in [
            ("Patient", f"{report['patient_name']} ({patient['age']}{patient['sex']})"),
            ("Patient ID", report["patient_id"]),
            ("Report No", report["report_id"]),
            ("Collected", report["collected_on"]),
        ]:
            c.drawString(20 * mm, y, f"{label}:")
            c.drawString(48 * mm, y, str(value))
            y -= 5 * mm
        c.line(20 * mm, y - 1 * mm, width - 20 * mm, y - 1 * mm)
        return y - 9 * mm

    def table_head(y: float) -> float:
        c.setFont("Helvetica-Bold", 9)
        for x, text in ((20, "Test"), (85, "Result"), (115, "Unit"), (143, "Reference"), (178, "Flag")):
            c.drawString(x * mm, y, text)
        c.line(20 * mm, y - 2 * mm, width - 20 * mm, y - 2 * mm)
        return y - 8 * mm

    def row(y: float, name: str, value, unit: str, ref: str, flag: str) -> float:
        c.setFont("Helvetica", 9.5)
        c.drawString(20 * mm, y, name)
        c.setFont("Helvetica-Bold" if flag else "Helvetica", 9.5)
        c.drawString(85 * mm, y, str(value))
        c.setFont("Helvetica", 9.5)
        c.drawString(115 * mm, y, unit)
        c.drawString(143 * mm, y, ref)
        if flag:
            c.drawString(178 * mm, y, flag)
        return y - 6 * mm

    def footer(page_no: int) -> None:
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(20 * mm, 14 * mm, "Synthetic report generated for testing. Not a real patient record.")
        c.drawRightString(width - 20 * mm, 14 * mm, f"Page {page_no} of {report['pages']}")

    by_page = {1: [], 2: []}
    for m in report["metrics"]:
        by_page[m["page"]].append(m)

    # ── Page 1: haematology + the distractor panel ──
    y = header("HAEMATOLOGY REPORT")
    y = table_head(y)
    for m in by_page[1]:
        y = row(y, DISPLAY_NAMES.get(m["name"], m["name"].title()),
                m["value"], m["unit"], reference_text(m["name"]), m["flag"])
    for d in report["distractors"]:
        y = row(y, d["label"], d["value"], d["unit"], "", "")
    footer(1)
    c.showPage()

    # ── Page 2: biochemistry + vitals ──
    y = header("BIOCHEMISTRY & VITALS")
    y = table_head(y)
    for m in by_page[2]:
        if m["name"].startswith("blood_pressure"):
            continue
        y = row(y, DISPLAY_NAMES.get(m["name"], m["name"].title()),
                m["value"], m["unit"], reference_text(m["name"]), m["flag"])

    systolic = next(m for m in report["metrics"] if m["name"] == "blood_pressure_systolic")
    diastolic = next(m for m in report["metrics"] if m["name"] == "blood_pressure_diastolic")
    bp_flag = systolic["flag"] or diastolic["flag"]
    y = row(y, "Blood Pressure", f"{int(systolic['value'])}/{int(diastolic['value'])}",
            "mmHg", "90/60 - 120/80", bp_flag)

    y -= 6 * mm
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(20 * mm, y, "Comments")
    c.setFont("Helvetica", 9)
    y -= 5 * mm
    for line in comment_lines(report):
        c.drawString(20 * mm, y, line)
        y -= 4.6 * mm
    footer(2)
    c.save()


def comment_lines(report: dict) -> List[str]:
    """Neutral lab comments. They never state the risk level the eval scores."""
    abnormal = [m for m in report["metrics"] if m["bucket"] != "normal"]
    if not abnormal:
        return ["All measured parameters are within the stated reference intervals.",
                "Clinical correlation is advised."]
    names = ", ".join(DISPLAY_NAMES.get(m["name"], m["name"].replace("_", " ")) for m in abnormal[:3])
    return [f"The following parameters fall outside the reference interval: {names}.",
            "Repeat testing and clinical correlation are advised."]


def render_messy(pdf_path: Path, out_path: Path, rng: random.Random) -> None:
    """
    A scanned-looking PNG of page 1, for the OCR path.

    Generated PDFs are cleaner than anything a patient photographs, so the
    extraction score on crisp PDFs alone would flatter the system.
    """
    import fitz
    from PIL import Image, ImageEnhance, ImageFilter

    with fitz.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(dpi=rng.choice([150, 170, 200]))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    img = img.rotate(rng.uniform(-1.8, 1.8), resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.8)))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.88, 1.06))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.85, 1.05))

    # Sparse speckle, the way a phone photo of a printout picks up grain
    pixels = img.load()
    for _ in range(int(img.width * img.height * 0.0015)):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        shade = rng.randint(90, 190)
        pixels[x, y] = (shade, shade, shade)

    img.save(out_path, "PNG")


# ── Corpus ──────────────────────────────────────────────────────────────

def generate(out_dir: Path, patients: int, min_reports: int, max_reports: int,
             seed: int, messy: int) -> dict:
    reports_dir = out_dir / "reports"
    messy_dir = out_dir / "reports_messy"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if messy:
        messy_dir.mkdir(parents=True, exist_ok=True)

    index: List[dict] = []
    today = date.today()

    for n in range(patients):
        # One stream per patient keeps a patient's corpus stable when the
        # number of patients changes.
        rng = random.Random(f"{seed}:{n}")
        patient = build_patient(rng, n)
        count = rng.randint(min_reports, max_reports)

        patient_dir = reports_dir / patient["patient_id"]
        patient_dir.mkdir(exist_ok=True)

        # Oldest first, roughly every 1-3 months, ending near today.
        gaps = [rng.randint(30, 90) for _ in range(count)]
        day = today - timedelta(days=sum(gaps))

        for step in range(count):
            day += timedelta(days=gaps[step])
            report = build_report(patient, step, day, rng)

            pdf_path = patient_dir / f"{report['report_id']}.pdf"
            render_pdf(report, patient, pdf_path)

            answer = dict(report)
            answer["file"] = str(pdf_path.relative_to(out_dir).as_posix())
            answer["file_type"] = "pdf"
            (patient_dir / f"{report['report_id']}.json").write_text(
                json.dumps(answer, indent=2), encoding="utf-8"
            )
            index.append(answer)

    # Messy variants of an evenly spread sample, so no single patient dominates
    if messy and index:
        picks = [index[i] for i in range(0, len(index), max(1, len(index) // messy))][:messy]
        for i, answer in enumerate(picks):
            rng = random.Random(f"{seed}:messy:{i}")
            png_path = messy_dir / f"{answer['report_id']}-scan.png"
            render_messy(out_dir / answer["file"], png_path, rng)

            messy_answer = dict(answer)
            messy_answer["file"] = str(png_path.relative_to(out_dir).as_posix())
            messy_answer["file_type"] = "image"
            messy_answer["messy"] = True
            messy_answer["pages"] = 1
            # Only page 1 is rendered, so page-2 values are not on this image.
            messy_answer["metrics"] = [m for m in answer["metrics"] if m["page"] == 1]
            messy_answer["distractors"] = [d for d in answer["distractors"] if d["page"] == 1]
            messy_answer["expected_risk"] = expected_risk(
                m["bucket"] for m in messy_answer["metrics"]
            )
            messy_path = messy_dir / f"{answer['report_id']}-scan.json"
            messy_path.write_text(json.dumps(messy_answer, indent=2), encoding="utf-8")
            index.append(messy_answer)

    risk_counts: Dict[str, int] = {}
    for answer in index:
        risk_counts[answer["expected_risk"]] = risk_counts.get(answer["expected_risk"], 0) + 1

    manifest = {
        "generated_on": today.isoformat(),
        "seed": seed,
        "patients": patients,
        "reports": len(index),
        "messy_reports": sum(1 for a in index if a.get("messy")),
        "risk_counts": risk_counts,
        "tracked_metrics": list(TRACKED_METRICS),
        "files": [a["file"] for a in index],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    default_out = Path(__file__).resolve().parent / "data"
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=default_out, help="output directory")
    parser.add_argument("--patients", type=int, default=40)
    parser.add_argument("--min-reports", type=int, default=10)
    parser.add_argument("--max-reports", type=int, default=30)
    parser.add_argument("--messy", type=int, default=12, help="scanned-looking variants")
    parser.add_argument("--seed", type=int, default=20261124)
    args = parser.parse_args()

    manifest = generate(args.out, args.patients, args.min_reports,
                        args.max_reports, args.seed, args.messy)

    print(f"Wrote {manifest['reports']} reports for {manifest['patients']} patients to {args.out}")
    print(f"  messy variants : {manifest['messy_reports']}")
    print("  expected risk  : " + ", ".join(
        f"{k} {v}" for k, v in sorted(manifest["risk_counts"].items())))


if __name__ == "__main__":
    main()
