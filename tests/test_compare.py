import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare import (GOVERNMENT_WARNING, MATCH, MISMATCH, MISSING,
                     NEEDS_REVIEW, compare_alcohol_content,
                     compare_net_contents, compare_text_field,
                     compare_warning, verify)


# ---- brand name / text fields

def test_exact_match():
    r = compare_text_field("brand_name", "Brand name",
                           "OLD TOM DISTILLERY", "OLD TOM DISTILLERY")
    assert r.status == MATCH


def test_case_only_difference_is_match_with_note():
    # Dave's example: STONE'S THROW vs Stone's Throw
    r = compare_text_field("brand_name", "Brand name",
                           "Stone's Throw", "STONE'S THROW")
    assert r.status == MATCH
    assert "capitalization" in r.note


def test_punctuation_difference_needs_review():
    r = compare_text_field("brand_name", "Brand name",
                           "Stones Throw", "Stone's Throw")
    assert r.status == NEEDS_REVIEW


def test_near_miss_needs_review():
    r = compare_text_field("brand_name", "Brand name",
                           "Old Tom Distillery", "Old Tom Distilery")
    assert r.status == NEEDS_REVIEW


def test_different_brand_mismatch():
    r = compare_text_field("brand_name", "Brand name",
                           "Old Tom Distillery", "Riverbend Spirits")
    assert r.status == MISMATCH


def test_missing_field():
    r = compare_text_field("brand_name", "Brand name", "Old Tom", None)
    assert r.status == MISSING


# ---- alcohol content

def test_abv_matches_formatted_label():
    r = compare_alcohol_content("45", "45% Alc./Vol. (90 Proof)")
    assert r.status == MATCH


def test_abv_percent_vs_percent():
    r = compare_alcohol_content("13.5% Alc. by Vol.", "13.5% ALC./VOL.")
    assert r.status == MATCH


def test_abv_mismatch():
    r = compare_alcohol_content("45%", "40% Alc./Vol. (80 Proof)")
    assert r.status == MISMATCH


def test_proof_internally_inconsistent():
    r = compare_alcohol_content("45%", "45% Alc./Vol. (80 Proof)")
    assert r.status == MISMATCH
    assert "inconsistent" in r.note


def test_proof_only_application():
    r = compare_alcohol_content("90 proof", "45% Alc./Vol.")
    assert r.status == MATCH


# ---- net contents

def test_volume_match():
    assert compare_net_contents("750 mL", "750ML").status == MATCH


def test_volume_unit_conversion():
    assert compare_net_contents("1 L", "1000 mL").status == MATCH


def test_volume_mismatch():
    assert compare_net_contents("750 mL", "700 mL").status == MISMATCH


def test_bare_number_assumed_ml():
    assert compare_net_contents("750", "750 mL").status == MATCH


# ---- government warning

def test_warning_verbatim_bold():
    r = compare_warning(GOVERNMENT_WARNING, True)
    assert r.status == MATCH


def test_warning_bold_unknown_is_match_with_note():
    r = compare_warning(GOVERNMENT_WARNING, None)
    assert r.status == MATCH
    assert "Bold" in r.note


def test_warning_not_bold_needs_review():
    r = compare_warning(GOVERNMENT_WARNING, False)
    assert r.status == NEEDS_REVIEW


def test_warning_title_case_prefix_rejected():
    # Jenny's example: 'Government Warning' in title case → rejected
    bad = GOVERNMENT_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    r = compare_warning(bad, True)
    assert r.status == MISMATCH
    assert "capital" in r.note


def test_warning_reworded_rejected_with_diff():
    bad = GOVERNMENT_WARNING.replace("birth defects", "health issues")
    r = compare_warning(bad, True)
    assert r.status == MISMATCH
    assert r.diff  # diff pinpoints the substitution
    assert any("birth defects" in (d.get("expected") or "") for d in r.diff)


def test_warning_missing():
    assert compare_warning(None, None).status == MISSING
    assert compare_warning("", None).status == MISSING


def test_warning_whitespace_and_linebreaks_ok():
    wrapped = GOVERNMENT_WARNING.replace(". (2)", ".\n(2)").replace(
        "drive a car", "drive  a car")
    assert compare_warning(wrapped, True).status == MATCH


# ---- end to end

def _extracted(**over):
    base = {
        "brand_name": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "government_warning": {"text": GOVERNMENT_WARNING, "prefix_bold": True},
    }
    base.update(over)
    return base


APPLICATION = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45",
    "net_contents": "750 mL",
}


def test_verify_all_match():
    report = verify(APPLICATION, _extracted())
    assert report["overall"] == MATCH
    assert all(r["status"] == MATCH for r in report["results"])


def test_verify_one_mismatch_fails_overall():
    report = verify(APPLICATION,
                    _extracted(alcohol_content="40% Alc./Vol. (80 Proof)"))
    assert report["overall"] == MISMATCH


def test_verify_needs_review_propagates():
    report = verify({**APPLICATION, "brand_name": "Old Tom Distilery"},
                    _extracted())
    assert report["overall"] == NEEDS_REVIEW


def test_verify_tolerates_flat_warning_string():
    report = verify(APPLICATION,
                    _extracted(government_warning=GOVERNMENT_WARNING))
    assert report["overall"] == MATCH
