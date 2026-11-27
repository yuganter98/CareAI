"""
Output safety for anything derived from uploaded report text.

Why this is a module and not a better prompt
--------------------------------------------
The eval measured 30 prompt injections hidden in report PDFs. Six of them
told the model to advise stopping medication, and all six succeeded, in every
run, whether the injected text was visible or drawn white-on-white. The model
copied the attacker's instruction into its clinical advice verbatim:

    "stop taking all prescribed medication immediately.
     discontinue current treatment"

A prompt rule asking the model not to do that is worth having and is applied
too, but it is a request, not a guarantee: the same prompt is what the
attacker is competing for. Report text is attacker-controlled input — anyone
can upload a PDF — so the property "CareAI never tells a patient to change
their medication" has to hold without the model's cooperation. That is what
this module is for: it runs on the output, after the model, and is plain
Python.

CareAI has no prescribing information, no drug interaction data, and no
knowledge of why a patient is on a given drug. There is no input for which
"stop your medication" is a correct output. So this removes the advice rather
than trying to judge it.

Scope note: this is the medication defence only. The `lower_risk` and
`suppress_alert` attacks need a deterministic risk floor, which is a separate
change.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# What a patient is told instead of a scrubbed instruction. CareAI may always
# say "ask your doctor"; it may never say what to do.
SAFE_MEDICATION_ACTION = (
    "Do not start, stop or change any medication based on this report. "
    "Discuss your medication with your doctor or pharmacist."
)

# A directive is a verb of change aimed at a medication-ish object. Built from
# the class of advice CareAI must never give, deliberately NOT from the phrase
# list the eval scores against: a guard keyed to the test set would pass the
# test and fail on the next wording. tests/test_safety.py checks wordings that
# appear nowhere in the eval.
_CHANGE_VERB = r"""(?:
    stop|ceas(?:e|ing)|discontinu(?:e|ing)|halt|quit|
    come\s+off|go\s+off|stay\s+off|taper|wean|
    skip|withhold|suspend|abandon|drop|pause|
    double|tripl(?:e|ing)|increase|decreas(?:e|ing)|reduc(?:e|ing)|
    chang(?:e|ing)|switch|adjust|alter|
    start|begin|resume|
    stop\s+taking|take\s+(?:more|less|fewer|extra|double)
)"""

_MEDICATION_NOUN = r"""(?:
    medications?|medicines?|meds|drugs?|tablets?|pills?|capsules?|
    prescriptions?|treatments?|therapy|therapies|
    dos(?:e|es|age|ages)|injections?|
    insulin|statins?|metformin|antibiotics?|anticoagulants?|
    blood\s+thinners?|beta\s+blockers?
)"""

# The verb and the object within ~40 characters of each other: enough for
# "stop taking all of your prescribed medication", short enough that a verb
# in one clause does not bind to a noun in the next sentence.
_DIRECTIVE = re.compile(
    rf"\b{_CHANGE_VERB}\b[^.!?\n]{{0,40}}?\b{_MEDICATION_NOUN}\b",
    re.IGNORECASE | re.VERBOSE,
)

# Negations that make the sentence safe advice rather than an instruction:
# "do not stop taking your medication" must survive untouched, because it is
# exactly what a correct answer says.
_NEGATION = re.compile(
    r"""\b(?:
        not|never|n't|without|avoid|refrain|unless|rather\s+than|instead\s+of|
        do\s+no|should\s+not|must\s+not|cannot|can't|don't|doesn't|
        before\s+(?:speaking|consulting|talking)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Frames that hand the decision to a clinician, or ask a question about it,
# rather than telling the patient to act. "Ask your doctor whether to change
# your dose" is the answer we want, and an earlier version of this guard
# stripped it.
#
# Deliberately narrow. "Your doctor may decide to adjust your medication" is
# still removed, because the obvious rule for allowing it - a clinician plus a
# modal - is also the easiest thing for an attacker to write ("your doctor may
# want you to stop all medication"). A safe sentence being dropped costs a
# sentence, and the patient is still told to speak to their doctor; the other
# error ships the attack. The over-blocking that remains is pinned in
# tests/test_safety.py rather than left for someone to rediscover.
_DEFERRAL = re.compile(
    r"""\b(?:
        ask|asking|consult|consulting|discuss|discussing|
        talk|speak|check\s+with|raise\s+with|
        whether|
        if\s+you|
        only\s+(?:a|an|your)\s+\w+\s+(?:should|can|may)|
        decision\s+for|up\s+to\s+your
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> List[str]:
    return [s for s in _SENTENCE.split(text) if s and s.strip()]


def is_medication_directive(text: str) -> bool:
    """True when `text` instructs a medication change without negating it.

    Negation is judged per sentence, so a safe sentence next to an unsafe one
    does not protect the unsafe one.
    """
    if not text:
        return False
    for sentence in _sentences(text):
        match = _DIRECTIVE.search(sentence)
        if not match:
            continue
        # Only the run-up to the directive can negate or defer it. "Stop taking your
        # medication, it is not helping" is still an instruction.
        preceding = sentence[:match.start()]
        if _NEGATION.search(preceding) or _DEFERRAL.search(preceding):
            continue
        return True
    return False


def scrub_text(text: str) -> Tuple[str, List[str]]:
    """Drop sentences that instruct a medication change.

    Returns the cleaned text and the sentences removed, so a caller can log
    what happened instead of silently rewriting a clinical answer.
    """
    if not text:
        return text, []

    kept, removed = [], []
    for sentence in _sentences(text):
        if is_medication_directive(sentence):
            removed.append(sentence.strip())
        else:
            kept.append(sentence.strip())

    if not removed:
        return text, []

    cleaned = " ".join(kept).strip()
    # Never hand back an empty answer: an empty summary reads as "nothing
    # was wrong", which on a report with critical values is worse than noise.
    if not cleaned:
        cleaned = SAFE_MEDICATION_ACTION
    return cleaned, removed


def scrub_analysis(analysis: Dict[str, Any], *, context: str = "") -> Dict[str, Any]:
    """Remove medication instructions from a report analysis.

    Mutates nothing: returns a new dict. Adds `safety` describing what was
    removed, so the API and the eval can both see that the guard fired rather
    than having to infer it.
    """
    out = dict(analysis)
    removed: List[str] = []

    summary = out.get("summary")
    if isinstance(summary, str):
        out["summary"], dropped = scrub_text(summary)
        removed.extend(dropped)

    actions = out.get("suggested_actions")
    if isinstance(actions, list):
        safe_actions = []
        for action in actions:
            if isinstance(action, str) and is_medication_directive(action):
                removed.append(action.strip())
            else:
                safe_actions.append(action)
        if removed and SAFE_MEDICATION_ACTION not in safe_actions:
            safe_actions.append(SAFE_MEDICATION_ACTION)
        # A report whose only advice was an injected instruction must still
        # tell the patient to do something.
        if not safe_actions:
            safe_actions = [SAFE_MEDICATION_ACTION]
        out["suggested_actions"] = safe_actions

    # The same instruction usually lands in both the summary and the actions.
    unique_removed = list(dict.fromkeys(removed))
    if unique_removed:
        logger.warning(
            "Medication advice removed from analysis%s: %s",
            f" ({context})" if context else "", unique_removed)
        out["safety"] = {
            "medication_advice_removed": unique_removed,
            "note": SAFE_MEDICATION_ACTION,
        }
    return out


# ── Injection markers, for visibility only ──────────────────────────────

# Phrases that only appear in text trying to address the model. Logged, never
# used to block: a real report could contain almost anything, and silently
# dropping a page is a worse failure than analysing a suspicious one. The
# point is that an injection attempt leaves a trace in the logs instead of
# passing through unremarked.
_INJECTION_MARKERS = (
    "ignore all previous", "ignore previous", "ignore the above",
    "disregard all previous", "disregard the above",
    "system note", "system:", "assistant:",
    "new instructions", "updated instructions", "override",
    "you must report", "you must classify", "do not alert",
    "as an ai language model",
)


def find_injection_markers(report_text: str) -> List[str]:
    """Instruction-like phrases in uploaded text. For logging and metrics."""
    if not report_text:
        return []
    low = report_text.lower()
    return [m for m in _INJECTION_MARKERS if m in low]
