"""Regression tests for the campaign kit checks, built from real Day 7 outputs."""
from src.rag.campaign import CLAIM_WORDS, numbers_in, unsupported_numbers

SHOULD_FLAG = [  # real, untagged operational claims found in the v1 kits
    "Fresh milk & warm bread are restocked daily.",
    "From checking every single dairy date to baking fresh rolls every morning, we take pride in it.",
    "We have also expanded our artisanal bread selections and partnered with local bakers.",
]

SHOULD_NOT_FLAG = [  # false alarms from the v2 kits: descriptions, not promises
    "We know our neighbors count on us for reliable daily essentials.",
    "A special neighbor offer on fresh staples at [STORE NAME]",
    "Enjoy $3 off your next $20 basket on fresh dairy and bread staples.",
]


def test_flags_real_claims():
    for sentence in SHOULD_FLAG:
        assert CLAIM_WORDS.search(sentence), f"missed a claim: {sentence}"


def test_ignores_descriptions():
    for sentence in SHOULD_NOT_FLAG:
        assert not CLAIM_WORDS.search(sentence), f"false alarm: {sentence}"


def test_numbers_are_normalised():
    assert numbers_in("$12.80") == numbers_in("12.8")       # the Day 7 '12.80' false flag
    assert "3532" in numbers_in("$3,531.54")                # rounding still matches

def test_refs_in_prose_are_not_numbers():
    # High-value kit, why_this_offer: (T5) and (T7) were flagged as the numbers 5 and 7
    copy = ("High-value customers respond strongly to recognition and reciprocity rather than deep discounts alone (T5), "
            "while a $10 discount on a $75 basket sits modestly below 15% to maintain margin discipline (T7) and relieve "
            "price resistance (R4, R8).")
    assert unsupported_numbers(copy, numbers_in("$10 off $75")) == []
    assert unsupported_numbers("Backed by [T12] and [R3, R11].", set()) == []


def test_real_numbers_are_still_flagged():
    assert unsupported_numbers("Save 20% this week (T5).", set()) == ["20"]


def test_rule_constants_are_allowed():
    assert unsupported_numbers("Under 160 characters, a 60-character subject, at most 15% off.", set()) == []
