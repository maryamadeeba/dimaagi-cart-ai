"""Offline checks for the Day 8 assistant: no Gemini calls, no files from models/ or data/ needed."""
import time
from pathlib import Path

import pytest

from src.rag import assistant
from src.rag.assistant import REF_PATTERN, SESSION, check_numbers, list_segments, parse_citations, timed


def test_ref_pattern_accepts_real_refs():
    for ref in ("R3", "T12", "S_highvalue", "K_corebasket", "W_highvalue"):
        assert REF_PATTERN.fullmatch(ref), ref


def test_ref_pattern_rejects_numbered_w_refs():
    assert not REF_PATTERN.fullmatch("W1")


def test_ref_pattern_rejects_tool_names_and_bad_refs():
    assert not REF_PATTERN.fullmatch("get_segment_reasons")
    assert not REF_PATTERN.fullmatch("S1")


def test_timed_keeps_name_and_docstring():
    wrapped = timed(list_segments)
    assert wrapped.__name__ == "list_segments"
    assert wrapped.__doc__ and wrapped.__doc__.strip()


def test_timed_adds_to_session_tool_seconds():
    def dummy():
        """Sleep briefly."""
        time.sleep(0.01)

    before = SESSION.tool_seconds
    timed(dummy)()
    assert SESSION.tool_seconds - before >= 0.009


def test_placeholders_are_not_fake_citations():
    answer = "Subject: A special neighbor offer at [STORE NAME]. Book here: [LINK]. 34 customers [S_highvalue]."
    cited, invalid = parse_citations(answer, {"S_highvalue": {}})
    assert cited == ["S_highvalue"]
    assert invalid == []


def test_list_segments_totals_match_segment_sums():
    if not Path("models/segments.json").exists():
        pytest.skip("models/segments.json not built")
    assistant.SESSION.__init__()
    r = list_segments()
    assert r["totals"]["ref"] == "S_all" and REF_PATTERN.fullmatch("S_all")
    assert r["totals"]["customers"] == sum(s["customers"] for s in r["segments"])
    assert r["totals"]["weekly_revenue_at_risk"] == pytest.approx(sum(s["weekly_revenue_at_risk"] for s in r["segments"]), abs=0.01)


NUMBER_REFS = {
    "S_corevisiting": {"label": "Your sales data: Core · Visiting less",
                       "text": '{"customers": 163, "weekly_revenue_at_risk": 2700.75, "share_of_revenue_at_risk": 0.306, '
                               '"revenue_at_risk_per_customer": 16.57}'},
    "S_corebasket": {"label": "Your sales data: Core · Basket changed",
                     "text": '{"customers": 272, "weekly_revenue_at_risk": 3531.54, "share_of_revenue_at_risk": 0.401, '
                             '"revenue_at_risk_per_customer": 12.98}'},
}


def test_check_numbers_flags_number_from_another_segment():
    issues = check_numbers("- Core Visiting less = $12.98 per customer [S_corevisiting]", NUMBER_REFS)
    assert [(u["number"], u["cited"]) for u in issues] == [("$12.98", ["S_corevisiting"])]


def test_check_numbers_accepts_rounding_and_fractions():
    assert check_numbers("$2,701 at risk [S_corevisiting]", NUMBER_REFS) == []
    assert check_numbers("40.1% [S_corebasket]", NUMBER_REFS) == []
    assert check_numbers("They spend $3,531.5 a week [S_corebasket]. Offer at [STORE NAME].", NUMBER_REFS) == []


def test_check_numbers_flags_numbers_without_citations():
    issues = check_numbers("You have 469 customers at risk.", NUMBER_REFS)
    assert [u["number"] for u in issues] == ["469"]


def test_check_numbers_uses_the_citation_after_each_number():
    refs = {**NUMBER_REFS, "S_highvalue": {"label": "", "text": '{"revenue_at_risk_per_customer": 75.87}'}}
    answer = ("* **Why:** $75.87 per week [S_highvalue] (compared to $12.98 for Core visiting less [S_corevisiting] "
              "and $16.57 for Core basket changed [S_corebasket]).")
    assert [(u["number"], u["cited"]) for u in check_numbers(answer, refs)] == [
        ("$12.98", ["S_corevisiting"]), ("$16.57", ["S_corebasket"])]


def test_check_numbers_keeps_a_bullet_with_its_trailing_citation():
    refs = {"K_corevisiting": {"label": "Campaign kit: Core · Visiting less",
                               "text": '{"sms": "[STORE NAME]: Take $3 off your next $20+ grocery basket."}'}}
    answer = ("- **SMS Text:** [STORE NAME]: Take $3 off your next $20+ grocery basket. Show this text "
              "at the register to save. Reply STOP to opt out [K_corevisiting].")
    assert check_numbers(answer, refs) == []


KIT_REFS = {"K_corevisiting": {
    "label": "Campaign kit: Core · Visiting less",
    "text": '{"owner_checklist": ["Audit fluid milk and packaged bread stock daily at 7 AM and refill gaps", '
            '"Assign secondary cashier backup from 4 PM to 7 PM", '
            '"Brief register staff on the $3 discount redemption for $20+ baskets"]}'},
    "S_corevisiting": {"label": "Your sales data: Core · Visiting less", "text": '{"customers": 163}'}}


def test_check_numbers_bullets_inherit_the_lead_in_citation():
    # seen in the installed app: 7, 4, 7, $3 and $20 were flagged although they are all in K_corevisiting
    answer = ("Before sending the campaign to your Core · Visiting less customers [S_corevisiting], complete these "
              "fixes [K_corevisiting]:\n"
              "- Audit fluid milk and packaged bread stock daily at 7 AM and refill gaps.\n"
              "- Assign secondary cashier backup from 4 PM to 7 PM.\n"
              "- Brief register staff on the $3 discount redemption for $20+ baskets.")
    assert check_numbers(answer, KIT_REFS) == []


def test_check_numbers_bullet_number_missing_from_the_lead_in_source_is_still_flagged():
    answer = ("Complete these fixes [K_corevisiting]:\n\n"
              "- Audit milk stock daily at 7 AM.\n"
              "- Offer $5 off baskets over $40.")
    assert [(u["number"], u["cited"]) for u in check_numbers(answer, KIT_REFS)] == [
        ("$5", ["K_corevisiting"]), ("$40", ["K_corevisiting"])]


def test_check_numbers_a_bullet_with_its_own_citation_does_not_inherit():
    answer = "Here are the numbers [K_corevisiting]:\n- 163 customers [S_corevisiting]\n- 4 PM rush [S_corevisiting]"
    assert [(u["number"], u["cited"]) for u in check_numbers(answer, KIT_REFS)] == [("4", ["S_corevisiting"])]


def test_check_numbers_bullets_under_an_uncited_lead_in_are_still_flagged():
    assert [u["number"] for u in check_numbers("Do this:\n- Restock at 7 AM.", KIT_REFS)] == ["7"]

