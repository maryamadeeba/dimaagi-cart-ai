"""Offline checks for eval.judge: no Gemini calls, no files from models/ or data/ needed."""
from src.rag import campaign
from eval import judge


def test_normalise_verdict():
    assert judge.normalise_verdict("Supported") == "supported"
    assert judge.normalise_verdict(" PARTIAL ") == "partial"
    assert judge.normalise_verdict("maybe") == "unsupported"


def test_faithfulness_score():
    assert judge.faithfulness(["supported", "supported", "partial", "unsupported"]) == 0.625
    assert judge.faithfulness([]) is None


FAKE_KIT = {
    "segment": "Core · Visiting less",
    "kit": {
        "goal": "GOAL-TEXT",
        "offer": {"headline": "OFFER-HEADLINE", "details": "OFFER-DETAILS", "why_this_offer": "WHY-OFFER",
                  "citations": ["T1"], "discount_dollars": 3, "min_basket_dollars": 25, "non_monetary_perk": "none"},
        "email": {"subject": "EMAIL-SUBJECT", "preview_text": "EMAIL-PREVIEW", "body": "EMAIL-BODY",
                  "call_to_action": "Shop", "citations": ["T1", "R1"]},
        "sms": {"text": "SMS-TEXT", "citations": ["T1"]},
        "social_post": {"platform": "Instagram", "concept": "c", "hook": "SOCIAL-HOOK",
                        "caption": "SOCIAL-CAPTION", "citations": ["T1"]},
    },
    "reviews": [{"ref": "R1", "text": "r" * 1000}],
    "trends": [{"ref": "T1", "publisher": "Klaviyo", "year": 2025, "title": "Report", "page": 3, "text": "t" * 2000}],
}


FAKE_WHY = {
    "segment": "Core · Visiting less",
    "summary": {"reasons": [{"reason": "REASON-TEXT", "explanation": "EXPLANATION-TEXT", "citations": ["R1"]}]},
    "evidence": [{"ref": "R1", "text": "r" * 1000}],
}


def test_kit_output_keeps_every_customer_facing_piece():
    out = judge.kit_output(FAKE_KIT)
    for piece in ("GOAL-TEXT", "OFFER-HEADLINE", "OFFER-DETAILS", "WHY-OFFER", "EMAIL-SUBJECT", "EMAIL-PREVIEW",
                  "EMAIL-BODY", "SMS-TEXT", "SOCIAL-HOOK", "SOCIAL-CAPTION"):
        assert piece in out, piece


def test_kit_sources_use_campaign_char_limits():
    assert judge.REVIEW_CHARS is campaign.REVIEW_CHARS and judge.TREND_CHARS is campaign.TREND_CHARS
    src = judge.kit_sources(FAKE_KIT, {"customers": 163}, "has_bakery: false", why=FAKE_WHY)
    assert "r" * campaign.REVIEW_CHARS in src and "r" * (campaign.REVIEW_CHARS + 1) not in src
    assert "t" * campaign.TREND_CHARS in src and "t" * (campaign.TREND_CHARS + 1) not in src
    assert '"customers": 163' in src and "has_bakery: false" in src


def test_kit_sources_include_reasons_and_writer_rules():
    src = judge.kit_sources(FAKE_KIT, {"customers": 163}, "", why=FAKE_WHY)
    assert "REASONS ANALYSIS GIVEN TO THE WRITER:" in src
    assert campaign.why_block(FAKE_WHY)[0] in src and "REASON-TEXT" in src
    assert "RULES GIVEN TO THE WRITER (claims that restate these are supported):" in src
    assert f"{campaign.SMS_MAX} characters" in src and f"{campaign.SUBJECT_MAX} characters" in src
    assert f"{campaign.MAX_DISCOUNT_RATE:.0%}" in src and "median weekly spend" in src


def test_each_type_prompt_contains_its_task_block():
    for typ in ("why", "kits", "chat"):
        prompt = judge.judge_prompt(typ, "OUTPUT-TEXT", "SOURCES-TEXT")
        assert judge.TASKS[typ] in prompt and "WRITER'S TASK" in prompt
        assert "OUTPUT-TEXT" in prompt and "SOURCES-TEXT" in prompt
        assert "UNSUPPORTED (not partial)" in prompt
    assert "LIKELY causes" in judge.judge_prompt("why", "", "")
    assert "Persuasive wording" in judge.judge_prompt("kits", "", "")
    assert "'other stores'" in judge.judge_prompt("chat", "", "")
