"""Deterministic verification logic.

Design principle: the LLM does *perception* (reading the label), plain code does
*verification* (comparing values). Compliance decisions should be reproducible
and auditable, so nothing in this module involves a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher

# Statuses
MATCH = "match"
NEEDS_REVIEW = "needs_review"
MISMATCH = "mismatch"
MISSING = "missing"

# 27 CFR Part 16 — mandatory health warning statement, verbatim.
GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)
WARNING_PREFIX = "GOVERNMENT WARNING:"


@dataclass
class FieldResult:
    field: str
    label: str
    status: str
    expected: str | None = None
    found: str | None = None
    note: str | None = None
    diff: list | None = None

    def to_dict(self):
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------- helpers

def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _norm_loose(s: str) -> str:
    """Casefold, collapse whitespace, strip punctuation (keep alphanumerics)."""
    s = _collapse_ws(s).casefold()
    return re.sub(r"[^a-z0-9 ]+", "", s)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_loose(a), _norm_loose(b)).ratio()


def _parse_abv(s: str) -> dict:
    """Pull ABV percentage and/or proof out of free text like
    '45% Alc./Vol. (90 Proof)' or '45' or 'ALC. 45% BY VOL.'."""
    out = {}
    if not s:
        return out
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", s, re.I)
    if m:
        out["abv"] = float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*proof", s, re.I)
    if m:
        out["proof"] = float(m.group(1))
    if "abv" not in out and "proof" not in out:
        # bare number, e.g. application form just says "45"
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", s)
        if m:
            out["abv"] = float(m.group(1))
    return out


_UNIT_TO_ML = {
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0, "millilitre": 1.0,
    "millilitres": 1.0,
    "cl": 10.0, "centiliter": 10.0, "centiliters": 10.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0,
    "litres": 1000.0,
    "oz": 29.5735, "ounce": 29.5735, "ounces": 29.5735, "floz": 29.5735,
}


def _parse_volume_ml(s: str) -> float | None:
    if not s:
        return None
    m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(fl\.?\s*oz\.?|milliliters?|millilitres?"
        r"|centiliters?|liters?|litres?|ounces?|ml|cl|l|oz)\b",
        s, re.I)
    if not m:
        # bare number → assume mL (the overwhelmingly common case on COLA forms)
        m2 = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", s)
        return float(m2.group(1).replace(",", ".")) if m2 else None
    qty = float(m.group(1).replace(",", "."))
    unit = re.sub(r"[.\s]", "", m.group(2).lower())
    return qty * _UNIT_TO_ML.get(unit, 1.0)


# ---------------------------------------------------------------- field checks

def compare_text_field(name: str, label: str, expected: str | None,
                       found: str | None) -> FieldResult:
    expected = _collapse_ws(expected or "")
    if not expected:
        return FieldResult(name, label, MATCH, expected=None, found=found,
                           note="Not provided on application — skipped.")
    if not found or not _collapse_ws(found):
        return FieldResult(name, label, MISSING, expected=expected, found=None,
                           note="Not found on the label.")
    found = _collapse_ws(found)

    if expected == found:
        return FieldResult(name, label, MATCH, expected, found)
    if expected.casefold() == found.casefold():
        return FieldResult(name, label, MATCH, expected, found,
                           note="Same text; differs only in capitalization "
                                "(e.g. stylized caps on the label).")
    if _norm_loose(expected) == _norm_loose(found):
        return FieldResult(name, label, NEEDS_REVIEW, expected, found,
                           note="Same wording; differs in punctuation or "
                                "spacing. Agent judgment recommended.")
    sim = _similarity(expected, found)
    if sim >= 0.85:
        return FieldResult(name, label, NEEDS_REVIEW, expected, found,
                           note=f"Close but not identical ({sim:.0%} similar). "
                                "Agent judgment recommended.")
    return FieldResult(name, label, MISMATCH, expected, found)


def compare_alcohol_content(expected: str | None, found: str | None) -> FieldResult:
    name, label = "alcohol_content", "Alcohol content"
    if not expected or not _collapse_ws(expected):
        return FieldResult(name, label, MATCH, None, found,
                           note="Not provided on application — skipped.")
    if not found or not _collapse_ws(found):
        return FieldResult(name, label, MISSING, expected, None,
                           note="Not found on the label.")
    exp, fnd = _parse_abv(expected), _parse_abv(found)
    if not exp:
        return compare_text_field(name, label, expected, found)
    if not fnd:
        return FieldResult(name, label, NEEDS_REVIEW, expected, found,
                           note="Could not parse a numeric alcohol content "
                                "from the label text.")

    # Compare ABV directly, or derive it from proof (proof = 2 × ABV).
    exp_abv = exp.get("abv", exp["proof"] / 2 if "proof" in exp else None)
    fnd_abv = fnd.get("abv", fnd["proof"] / 2 if "proof" in fnd else None)
    if exp_abv is not None and fnd_abv is not None and abs(exp_abv - fnd_abv) > 0.01:
        return FieldResult(name, label, MISMATCH, expected, found,
                           note=f"Application says {exp_abv:g}% ABV, "
                                f"label shows {fnd_abv:g}%.")
    # Internal consistency: if the label states both ABV and proof, they must agree.
    if "abv" in fnd and "proof" in fnd and abs(fnd["proof"] - 2 * fnd["abv"]) > 0.01:
        return FieldResult(name, label, MISMATCH, expected, found,
                           note=f"Label is internally inconsistent: {fnd['abv']:g}% "
                                f"ABV should be {2 * fnd['abv']:g} proof, label "
                                f"says {fnd['proof']:g} proof.")
    return FieldResult(name, label, MATCH, expected, found)


def compare_net_contents(expected: str | None, found: str | None) -> FieldResult:
    name, label = "net_contents", "Net contents"
    if not expected or not _collapse_ws(expected):
        return FieldResult(name, label, MATCH, None, found,
                           note="Not provided on application — skipped.")
    if not found or not _collapse_ws(found):
        return FieldResult(name, label, MISSING, expected, None,
                           note="Not found on the label.")
    exp_ml, fnd_ml = _parse_volume_ml(expected), _parse_volume_ml(found)
    if exp_ml is None or fnd_ml is None:
        return compare_text_field(name, label, expected, found)
    if abs(exp_ml - fnd_ml) <= max(1.0, 0.005 * exp_ml):  # rounding slack
        return FieldResult(name, label, MATCH, expected, found)
    return FieldResult(name, label, MISMATCH, expected, found,
                       note=f"Application: {exp_ml:g} mL equivalent; "
                            f"label: {fnd_ml:g} mL equivalent.")


def compare_warning(found_text: str | None, prefix_bold: bool | None) -> FieldResult:
    """The health warning must be verbatim (27 CFR 16.21), with
    'GOVERNMENT WARNING' in capital letters and bold type."""
    name, label = "government_warning", "Government warning"
    if not found_text or not _collapse_ws(found_text):
        return FieldResult(name, label, MISSING, GOVERNMENT_WARNING, None,
                           note="No government warning found on the label. "
                                "Mandatory on all alcohol beverages.")
    found = _collapse_ws(found_text)

    # 1) Prefix must be exactly 'GOVERNMENT WARNING:' — capital letters required.
    prefix_ok = found.startswith(WARNING_PREFIX)
    prefix_note = None
    if not prefix_ok:
        if found[:len(WARNING_PREFIX)].casefold() == WARNING_PREFIX.casefold():
            prefix_note = (f"'{found[:len(WARNING_PREFIX)]}' is not in all "
                           "capital letters — 'GOVERNMENT WARNING:' must be in caps.")
        else:
            prefix_note = "Warning does not begin with 'GOVERNMENT WARNING:'."

    # 2) Body must match the statutory text word for word.
    def words(s):
        return re.findall(r"[a-z0-9']+", s.casefold())

    exp_words, fnd_words = words(GOVERNMENT_WARNING), words(found)
    diff = None
    body_ok = exp_words == fnd_words
    if not body_ok:
        sm = SequenceMatcher(None, exp_words, fnd_words)
        diff = [{"op": op,
                 "expected": " ".join(exp_words[i1:i2]),
                 "found": " ".join(fnd_words[j1:j2])}
                for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]

    if not prefix_ok or not body_ok:
        notes = []
        if prefix_note:
            notes.append(prefix_note)
        if not body_ok:
            notes.append("Wording deviates from the statutory text (see diff).")
        return FieldResult(name, label, MISMATCH, GOVERNMENT_WARNING, found,
                           note=" ".join(notes), diff=diff)

    # 3) Bold check is best-effort from a photo.
    if prefix_bold is False:
        return FieldResult(name, label, NEEDS_REVIEW, GOVERNMENT_WARNING, found,
                           note="Text is verbatim, but 'GOVERNMENT WARNING:' does "
                                "not appear to be in bold type. Verify visually.")
    note = None if prefix_bold else \
        "Text is verbatim. Bold type could not be confirmed from the image."
    return FieldResult(name, label, MATCH, GOVERNMENT_WARNING, found, note=note)


# ---------------------------------------------------------------- entry point

def verify(application: dict, extracted: dict) -> dict:
    """application: fields from the COLA form. extracted: fields the model read
    off the label image. Returns per-field results + an overall verdict."""
    gw = extracted.get("government_warning") or {}
    if isinstance(gw, str):  # tolerate a flat string from the extractor
        gw = {"text": gw, "prefix_bold": None}

    results = [
        compare_text_field("brand_name", "Brand name",
                           application.get("brand_name"),
                           extracted.get("brand_name")),
        compare_text_field("class_type", "Class / type",
                           application.get("class_type"),
                           extracted.get("class_type")),
        compare_alcohol_content(application.get("alcohol_content"),
                                extracted.get("alcohol_content")),
        compare_net_contents(application.get("net_contents"),
                             extracted.get("net_contents")),
        compare_warning(gw.get("text"), gw.get("prefix_bold")),
    ]

    statuses = [r.status for r in results]
    if MISMATCH in statuses or MISSING in statuses:
        overall = MISMATCH
    elif NEEDS_REVIEW in statuses:
        overall = NEEDS_REVIEW
    else:
        overall = MATCH

    return {"overall": overall, "results": [r.to_dict() for r in results]}
