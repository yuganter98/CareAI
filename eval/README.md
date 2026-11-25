# CareAI evaluation set

Measuring CareAI instead of demoing it. This directory holds the synthetic
corpus and, from Week 1, the test sets and the `make eval` harness.

> **Synthetic data only.** Every patient, name and value here is invented by
> `generate_reports.py`. Never add real patient data to this repository.

## Generating the corpus

```bash
pip install reportlab          # the only extra dependency
python eval/generate_reports.py
```

That writes ~800 reports for 40 patients to `eval/data/` in about 15 seconds.
For a quick look, `--patients 5 --min-reports 3 --max-reports 5`.

`eval/data/` is **not** committed: it is reproducible from the generator and the
seed, and 800 PDFs do not belong in git. The same `--seed` always produces the
same corpus, so anyone who clones the repo can rebuild it byte for byte.

## Why generated, not labelled by hand

The generator knows every value it prints, so it writes the answer key itself.
Labelling 800 reports by hand would take days and still contain mistakes; here
the extraction and risk test sets are correct by construction. Week 1 only has
to hand-check the question set and the risk rule, not the raw values.

## What it produces

```
eval/data/
  manifest.json                     index of every report + risk counts
  reports/SYN0003/SYN0003-R07.pdf   a two-page lab report
  reports/SYN0003/SYN0003-R07.json  every value it prints, and on which page
  reports_messy/…-scan.png          a scanned-looking page 1, for the OCR path
  reports_messy/…-scan.json         the same answers, page-1 values only
```

Each answer file holds:

| Field | Meaning |
| --- | --- |
| `metrics` | one entry per tracked value: `name`, `value`, `unit`, `page`, `bucket`, `flag` |
| `distractors` | values printed on the report that CareAI is not asked to track |
| `expected_risk` | `High` / `Medium` / `Low`, from the rule below |
| `pages`, `file`, `file_type` | what to feed the extraction pipeline |

`page` is what makes page-level citation accuracy measurable: haematology is
printed on page 1 and biochemistry on page 2, so an answer about glucose that
cites page 1 is wrong even when the number is right.

## The risk rule

From `ranges.py`, which mirrors the app's `REFERENCE_RANGES`:

- any **critical** value → `High`
- any **elevated** value → `Medium`
- otherwise → `Low`

It is deterministic on purpose. It is the label the eval scores against, and in
Week 5 the same rule becomes the floor the LLM may raise but never lower, so a
prompt injection cannot talk the system out of flagging a critical value.

`backend/tests/test_eval_groundwork.py` fails if `ranges.py` ever drifts from
the app's own ranges.

## Patient profiles

Each patient follows one of seven trajectories, so trends are real rather than
noise, and some reports are abnormal on purpose:

`healthy`, `prediabetic_worsening`, `diabetic_uncontrolled`,
`anemia_progressing`, `renal_decline`, `hypertensive`, `recovering`

`recovering` starts abnormal and improves, which is what makes "is my
hemoglobin getting better?" a question with a checkable answer.

At the default settings the corpus runs roughly 20% `High`, 55% `Medium`,
25% `Low` — Medium-heavy, as a chronic-condition cohort would be, with enough
`High` reports (about 150) to measure high-risk recall meaningfully.

## Known limitation

Generated PDFs are cleaner than anything a patient photographs, so extraction
scores on them flatter the system. That is what `reports_messy/` is for: rotated,
blurred, speckled renders that go through the Tesseract path instead. Report
both numbers separately and say so in the README; the messy score is the honest
one.
