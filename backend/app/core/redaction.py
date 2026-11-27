"""
Strip identifiers out of text before it leaves the server.

Where this is used
------------------
Logs, and anything sent to a tracing backend. A trace is the point: it exists
to be read later, by a third party's web UI, by whoever has that account.
Report text, model answers and the sentences the safety guards remove all
derive from an uploaded medical report, so they can carry the patient's name
as easily as their glucose.

What it does and does not do
----------------------------
It removes what can be identified *deterministically*: email addresses, phone
numbers, labelled identifiers (patient ID, MRN, NHS number, SSN, Aadhaar),
labelled dates of birth, and any string the caller already knows is an
identifier - the account holder's name, the patient name printed on the
report.

**It does not find arbitrary names.** No regex does. A name is a word that
looks like any other word, and "Mr Brown" is indistinguishable from "mr brown
rice" to a pattern. Claiming otherwise would be worse than not redacting,
because it invites trusting the output. Callers that know the name must pass
it in `known`; `redact_for_trace` does that from the user record.

So this is a mitigation, not an anonymiser. The README says so too, because
the difference matters for a medical app: text that has been through this is
safe to log, not safe to publish.

The other half of the job is NOT over-redacting. A trace with the lab values
scrubbed out is useless for debugging - and worse, a value eaten by a phone
number pattern is a silent change to the thing you are trying to inspect.
Every pattern here is bounded so that "Glucose 212 mg/dL", "Hemoglobin 13.1"
and "118/76 mmHg" come through untouched. tests/test_redaction.py pins that
with a list of clinical lines that must survive.
"""
from __future__ import annotations

import re
from typing import Iterable

EMAIL = "[email]"
PHONE = "[phone]"
IDENT = "[id]"
DOB = "[dob]"
NAME = "[name]"

_EMAIL_RE = re.compile(r"\b[\w.%+-]+@[\w-]+\.[A-Za-z]{2,}\b")

# A phone number is only recognised from a *strong* signal: a + country code,
# a bracketed area code, an explicit label, or an unbroken run of 7-15 digits.
#
# The obvious pattern - 7 to 15 digits with optional separators - was written
# first and the tests rejected it, for two reasons worth keeping here because
# both would have corrupted traces silently:
#
#   "Collected 2026-11-24"        -> an ISO date is 8 digits with separators
#   "88 212 450 118 76 13.1"      -> a row of lab values joins into one run
#
# Counting separators to tell these apart is brittle ("020 7946 0958" has two
# spaces, so does a short list of values). Requiring a signal that clinical
# text does not produce is not.
_PHONE_RE = re.compile(
    r"""(?<![\w.])
    (?:
        \+\d{1,3}[\s.-]?\d(?:[\s.-]?\d){5,14}      # +44 7700 900123
      | \(\d{2,4}\)[\s.-]?\d(?:[\s.-]?\d){5,12}    # (020) 7946 0958
      | \d{7,15}                                   # 4471928, unbroken
    )
    (?![\d.])
    """,
    re.VERBOSE)

# Phones written plainly, which only a nearby label distinguishes from a list
# of numbers. The label is kept; the digits are not.
_LABELLED_PHONE_RE = re.compile(
    r"""\b(phone|telephone|tel|mobile|cell|fax|contact\s*(?:no|number)?|call)
        \s*[:#=-]?\s*
        (\+?\d(?:[\s.-]?\d){5,14})""",
    re.IGNORECASE | re.VERBOSE)

# Only *labelled* identifiers. An unlabelled alphanumeric token is as likely
# to be an analyser model or a test code as a patient number, and redacting
# those would quietly corrupt the trace.
_LABELLED_ID_RE = re.compile(
    r"""\b(
        patient\s*(?:id|no|number|identifier)
      | \bmrn\b | medical\s*record\s*(?:no|number)
      | nhs\s*(?:no|number)
      | hospital\s*(?:no|number)
      | ssn | social\s*security(?:\s*number)?
      | aadhaar | aadhar
      | insurance\s*(?:id|no|number)
      | accession\s*(?:no|number)
    )\s*[:#=-]?\s*([A-Za-z0-9][A-Za-z0-9/-]{2,})""",
    re.IGNORECASE | re.VERBOSE)

_DOB_RE = re.compile(
    r"""\b(d\.?o\.?b\.?|date\s+of\s+birth|born(?:\s+on)?)\s*[:#=-]?\s*
        ([0-9]{1,4}[-/. ][0-9]{1,2}[-/. ][0-9]{1,4}
        |[0-9]{1,2}\s+\w+\s+[0-9]{2,4}
        |\w+\s+[0-9]{1,2},?\s+[0-9]{2,4})""",
    re.IGNORECASE | re.VERBOSE)

# A name must be at least this long to be redacted by `known`. Below it, a
# substring match does more harm than good: a user called "Al" or "Jo" would
# have those two letters struck out of every word containing them.
_MIN_NAME = 3


def redact(text: str, known: Iterable[str] = ()) -> str:
    """Remove identifiers from `text`. See the module docstring for limits."""
    if not text:
        return text
    if not isinstance(text, str):
        return text

    out = _EMAIL_RE.sub(EMAIL, text)
    out = _DOB_RE.sub(lambda m: f"{m.group(1)}: {DOB}", out)
    out = _LABELLED_ID_RE.sub(lambda m: f"{m.group(1)}: {IDENT}", out)
    # Labelled first: it catches plainly written numbers that the strict
    # pattern deliberately leaves alone.
    out = _LABELLED_PHONE_RE.sub(lambda m: f"{m.group(1)}: {PHONE}", out)
    out = _PHONE_RE.sub(PHONE, out)
    out = redact_known(out, known)
    return out


def redact_known(text: str, known: Iterable[str]) -> str:
    """Replace strings the caller already knows identify someone.

    Each is matched whole-word and case-insensitively, and a multi-word name
    is also matched by its parts, so "Priya Rao" catches a later "Priya".
    """
    if not text:
        return text
    terms: set[str] = set()
    for item in known or ():
        if not item or not isinstance(item, str):
            continue
        cleaned = item.strip()
        if len(cleaned) >= _MIN_NAME:
            terms.add(cleaned)
        for part in re.split(r"[\s,]+", cleaned):
            if len(part) >= _MIN_NAME:
                terms.add(part)

    # Longest first, so "Priya Rao" is replaced as one unit rather than
    # leaving "[name] [name]".
    for term in sorted(terms, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(term)}\b", NAME, text, flags=re.IGNORECASE)
    return text


def redact_for_trace(value, known: Iterable[str] = ()):
    """Redact a value of any shape on its way to a log or a trace.

    Walks dicts and lists so a whole analysis object can be passed in. Keys
    are left alone - they are field names, not content.
    """
    if isinstance(value, str):
        return redact(value, known)
    if isinstance(value, dict):
        return {k: redact_for_trace(v, known) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_for_trace(v, known) for v in value)
    return value
