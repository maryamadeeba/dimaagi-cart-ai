"""Day 7: a cited, multi-channel win-back campaign kit for each at-risk segment.

Needs models/why_summaries.json (run `python -m src.rag.generate` first)
and config/store_profile.yaml (what is true about the store).
Run:
  python -m src.rag.campaign --dry-run     # show the trend evidence only (no Gemini call)
  python -m src.rag.campaign               # build the kits
"""
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from src.rag.gemini import gemini_json
from src.rag.generate import facts, load_segments, merge_results, seg_name
from src.rag.refs import REF_PATTERN, parse_refs, refs_in
from src.rag.retriever import search_trends
from src.console import utf8_console

WHY_PATH = Path("models/why_summaries.json")
PROFILE_PATH = Path("config/store_profile.yaml")
OUT_JSON = Path("models/campaign_kits.json")
OUT_MD = Path("models/campaign_kits.md")          # quotes review IDs, so it stays gitignored
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

TRENDS_PER_QUERY = 3
MAX_TRENDS = 10
TREND_CHARS = 700
REVIEW_CHARS = 300
SMS_MAX, SUBJECT_MAX = 160, 60
LINK_CHARS = 23                 # typical shortened link length
MAX_DISCOUNT_RATE = 0.15        # discount at most 15% of the minimum basket

BASE_TREND_QUERIES = [
    "win-back campaign for lapsed customers: segmentation, message and cadence",
    "email marketing subject lines, timing and re-engagement emails",
    "SMS marketing best practices, frequency and opt-in",
    "social media content that drives engagement for retail brands",
    "loyalty rewards and offers that customers value",
]

# Operational ACTIONS a store would have to really do (restock, inspect, expand...).
# Descriptive words like "fresh", "daily" or "local" are NOT claims on their own: they caused false alarms in detector v1.
CLAIM_WORDS = re.compile(
    r"\b(re-?stock(ed|ing|s)?|replenish\w*|inspect\w*|audit\w*|check(ed|ing|s)?|verif\w*|"
    r"staff(ed|ing)?|expand\w*|partner\w*|upgrad\w*|guarantee\w*|improv\w*|bak(ed|ing)|fix(ed)?)\b",
    re.IGNORECASE)


# ---------- output schema ----------
class Offer(BaseModel):
    headline: str
    details: str
    discount_dollars: float
    min_basket_dollars: float
    non_monetary_perk: str
    why_this_offer: str
    citations: list[str]


class Email(BaseModel):
    subject: str
    preview_text: str
    body: str
    call_to_action: str
    citations: list[str]


class SMS(BaseModel):
    text: str
    citations: list[str]


class SocialPost(BaseModel):
    platform: str
    concept: str
    hook: str
    caption: str
    citations: list[str]


class Step(BaseModel):
    day: int
    channel: str
    action: str


class CampaignKit(BaseModel):
    goal: str
    offer: Offer
    email: Email
    sms: SMS
    social_post: SocialPost
    send_plan: list[Step]
    cadence_citations: list[str]
    owner_checklist: list[str]
    measurement: list[str]
    risks: str


# ---------- inputs ----------
def load_why():
    if not WHY_PATH.exists():
        raise SystemExit(f"❌ {WHY_PATH} not found. Run `python -m src.rag.generate` first.")
    return json.loads(WHY_PATH.read_text(encoding="utf-8"))


def load_profile():
    if not PROFILE_PATH.exists():
        print(f"⚠ {PROFILE_PATH} not found: the model will be told to assume nothing about the store.")
        return {}
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}


def why_block(why):
    """The segment's reasons plus the review text behind each cited R ref."""
    ev = {e["ref"]: e for e in why["evidence"]}
    lines, used = [], []
    for r in why["summary"]["reasons"]:
        refs = [x for c in r["citations"] for x in refs_in(c)]
        used += [x for x in refs if x not in used]
        lines.append(f"- {r['reason'].rstrip('.')} ({', '.join(refs)}): {r['explanation']}")
    lines.append("\nReviews behind these reasons:")
    for ref in used:
        if ref in ev:
            lines.append(f'[{ref}] "{ev[ref]["text"][:REVIEW_CHARS].strip()}"')
    return "\n".join(lines), [ev[x] for x in used if x in ev]


def trend_queries(why):
    reason_queries = [f"{r['reason'].rstrip('.')}: how retailers respond and win customers back"
                      for r in why["summary"]["reasons"][:3]]
    return BASE_TREND_QUERIES + reason_queries


def gather_trends(why):
    results = [search_trends(q, k=TRENDS_PER_QUERY) for q in trend_queries(why)]
    seen, picked = set(), []
    while len(picked) < MAX_TRENDS and any(results):
        for hits in results:
            while hits:
                h = hits.pop(0)
                if h["id"] not in seen:
                    seen.add(h["id"])
                    picked.append(h)
                    break
            if len(picked) >= MAX_TRENDS:
                break
    for i, t in enumerate(picked, 1):
        t["ref"] = f"T{i}"
    return picked


def trend_label(t):
    return f"{t.get('publisher', '')} {t.get('year', '')}, \"{t.get('title', t.get('source', ''))}\", p.{t.get('page', '?')}"


def median_spend(s):
    for k, v in facts(s).items():
        if "median" in k.lower() and isinstance(v, (int, float)):
            return float(v)
    return None


# ---------- prompt ----------
def build_prompt(s, why, why_text, trends, profile):
    trend_lines = "\n".join(f'[{t["ref"]}] {trend_label(t)}: "{t["text"][:TREND_CHARS].strip()}"' for t in trends)
    return f"""You are a marketing strategist for a small, independent grocery store. Write a win-back campaign kit the owner can send as their own store.

STORE PROFILE (the ONLY facts about the store you may state; "false" or "unknown" means do not mention or claim it):
{yaml.safe_dump(profile, sort_keys=False)}
SEGMENT: {seg_name(s)}
SEGMENT FACTS (from the owner's sales data; the ONLY segment numbers you may use):
{json.dumps(facts(s), indent=2)}
Categories this segment cut back on: {", ".join(why.get("lapsed_categories", [])) or "none recorded"}

WHY THEY ARE DRIFTING (from a previous analysis; R refs are Yelp reviews of OTHER grocery stores, a proxy voice):
{why_text}

MARKETING EVIDENCE (T refs are pages from published marketing and retail reports):
{trend_lines}

TASK: Write one campaign kit for this segment: offer, email, SMS, social post, a send plan, an owner checklist, measurement and risks.

Rules:
- Every piece (offer, email, sms, social_post) must cite refs: at least one T ref for the tactic, and an R ref when it addresses a customer complaint. Cite the send plan's cadence in cadence_citations. Cite only refs listed above.
- Address this segment's top reasons directly. Match the tone to the segment: only high-value customers are "most valued"; core customers are "regulars" or "neighbors".
- Only mention departments, services and suppliers the STORE PROFILE marks true. Never invent a bakery, loyalty program, delivery, local suppliers or anything else.
- Never claim a problem is fixed. Any sentence in the email or social post about an improvement (fresher, restocked, checked, faster checkout) must end with [CONFIRM], and the matching action must be in owner_checklist. [CONFIRM] goes only in customer messages, never in owner_checklist.
- SMS: only the offer, how to redeem it, and "Reply STOP to opt out". No improvement claims in SMS. At most 160 characters including the opt-out. Send only to customers who opted in.
- Never reveal tracking details to customers (e.g. "your basket got lighter in dairy"). Say "we've missed you" instead.
- Offer: fill discount_dollars and min_basket_dollars. min_basket_dollars must be ABOVE the segment's median weekly spend so the offer grows the basket. discount_dollars at most {int(MAX_DISCOUNT_RATE * 100)}% of min_basket_dollars. For high-value segments, lead with a non_monetary_perk (recognition or service) and keep the discount modest; otherwise non_monetary_perk may be "none". Say in details that the values are suggestions. The headline may only promise what details describe.
- Numbers: segment numbers only from SEGMENT FACTS; any marketing statistic only if it appears in a cited T ref.
- Email subject: at most 60 characters. Email body: 80 to 150 words, in short paragraphs, warm and plain, signed by the store.
- Use [STORE NAME] for the store's name and [LINK] for any link. No fake urgency, no guilt.
- send_plan: 2 to 4 steps over about 2 weeks, ending with a preference or goodbye step for people who never respond.
- measurement: 3 to 5 metrics the owner can track with their sales data.
"""


# ---------- checks ----------
NUM = r"\d[\d,]*(?:\.\d+)?"


def numbers_in(text):
    """Every number in the text, normalised so 12.80, 12.8 and 12.80000 all match."""
    out = set()
    for n in re.findall(NUM, str(text)):
        n = n.replace(",", "").rstrip(".")
        try:
            f = float(n)
        except ValueError:
            continue
        out.add(f"{f:g}")
        out.add(str(round(f)))
    return out


def sms_send_length(text, profile):
    """Length once placeholders are filled in and [CONFIRM] tags are removed."""
    name = str(profile.get("store_name", "[STORE NAME]"))
    name_len = 20 if name.startswith("[") else len(name)
    t = text.replace("[CONFIRM]", "").replace("[STORE NAME]", "x" * name_len).replace("[LINK]", "x" * LINK_CHARS)
    return len(re.sub(r"\s+", " ", t).strip())


def unflagged_claims(kit):
    """Customer-facing sentences that sound like operational promises but lack [CONFIRM] (heuristic)."""
    texts = [kit["email"]["subject"], kit["email"]["preview_text"], kit["email"]["body"],
             kit["sms"]["text"], kit["social_post"]["hook"], kit["social_post"]["caption"]]
    flagged = []
    for t in texts:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", t):
            if sentence.strip() and CLAIM_WORDS.search(sentence) and "[CONFIRM]" not in sentence:
                flagged.append(sentence.strip()[:90])
    return flagged


def check_offer(kit, s):
    o = kit["offer"]
    median = median_spend(s)
    rate = o["discount_dollars"] / o["min_basket_dollars"] if o["min_basket_dollars"] else 1.0
    above = median is None or o["min_basket_dollars"] > median
    return {"discount": o["discount_dollars"], "min_basket": o["min_basket_dollars"], "median_spend": median,
            "discount_rate": round(rate, 3), "threshold_above_median": above,
            "economics_ok": above and rate <= MAX_DISCOUNT_RATE}


def unsupported_numbers(copy, allowed):
    """Numbers in the copy that no source contains. Refs written in prose ("(T5)", "(R4, R8)") are removed
    first, so their digits aren't read as numbers; numbers from our own rules (160, 60, 15) are allowed."""
    rule_numbers = {str(SMS_MAX), str(SUBJECT_MAX), f"{MAX_DISCOUNT_RATE * 100:g}"}
    return sorted(numbers_in(REF_PATTERN.sub(" ", copy)) - set(allowed) - rule_numbers)


def check_kit(kit, s, review_ev, trends, profile):
    valid = {e["ref"] for e in review_ev} | {t["ref"] for t in trends}
    pieces = {
        "offer": kit["offer"]["citations"],
        "email": kit["email"]["citations"],
        "sms": kit["sms"]["citations"],
        "social_post": kit["social_post"]["citations"],
        "cadence": kit["cadence_citations"],
    }
    cited = {k: parse_refs(v) for k, v in pieces.items()}
    all_cited = [r for refs in cited.values() for r in refs]
    invalid = sorted({r for r in all_cited if r not in valid})

    allowed = set()
    for v in facts(s).values():
        allowed |= numbers_in(v)
    for e in list(review_ev) + list(trends):
        allowed |= numbers_in(e["text"])
    allowed |= numbers_in(f"{kit['offer']['headline']} {kit['offer']['details']} "
                          f"{kit['offer']['discount_dollars']} {kit['offer']['min_basket_dollars']}")
    copy = " ".join([kit["goal"], kit["email"]["subject"], kit["email"]["preview_text"], kit["email"]["body"],
                     kit["email"]["call_to_action"], kit["sms"]["text"], kit["social_post"]["hook"],
                     kit["social_post"]["caption"], kit["offer"]["why_this_offer"], kit["risks"]])
    unsupported = unsupported_numbers(copy, allowed)
    sms_len = sms_send_length(kit["sms"]["text"], profile)
    return {
        "citations": len(all_cited),
        "citation_validity": round(1 - len(invalid) / len(all_cited), 3) if all_cited else 0.0,
        "invalid_citations": invalid,
        "uncited_pieces": [k for k, v in cited.items() if not v],
        "pieces_without_trend_ref": [k for k, v in cited.items() if k != "cadence" and not any(r.startswith("T") for r in v)],
        "sms_send_chars": sms_len,
        "sms_ok": sms_len <= SMS_MAX and "STOP" in kit["sms"]["text"].upper(),
        "subject_chars": len(kit["email"]["subject"]),
        "subject_ok": len(kit["email"]["subject"]) <= SUBJECT_MAX,
        "unsupported_numbers": unsupported,
        "unflagged_claims": unflagged_claims(kit),
        "confirm_flags": sum(str(x).count("[CONFIRM]") for x in [kit["email"]["body"], kit["sms"]["text"], kit["social_post"]["caption"]]),
        "offer": check_offer(kit, s),
    }


# ---------- report ----------
def to_markdown(results):
    lines = ["# Win-back campaign kits", "",
             f"Model: `{MODEL}`. R refs = Yelp reviews of other grocery stores (proxy voice). "
             "T refs = published marketing and retail reports. Offers are suggestions for the owner to adjust. "
             "Remove every [CONFIRM] tag (and confirm the claim is true) before sending.", ""]
    for r in results:
        k, c = r["kit"], r["checks"]
        o = c["offer"]
        econ = (f"${o['discount']:g} off ${o['min_basket']:g} ({o['discount_rate']:.0%} of basket); "
                f"median weekly spend {'$' + format(o['median_spend'], ',.2f') if o['median_spend'] else 'unknown'}; "
                f"threshold above median {'✅' if o['threshold_above_median'] else '❌'}; "
                f"economics {'✅' if o['economics_ok'] else '❌'}")
        lines += [f"## {r['segment']}", "", f"**Goal:** {k['goal']}", "",
                  f"### Offer: {k['offer']['headline']}", k["offer"]["details"], "",
                  f"*Perk:* {k['offer']['non_monetary_perk']}  ", f"*Economics:* {econ}", "",
                  f"*Why this offer:* {k['offer']['why_this_offer']} ({', '.join(k['offer']['citations'])})", "",
                  f"### Email ({c['subject_chars']}-char subject)",
                  f"**Subject:** {k['email']['subject']}  ",
                  f"**Preview:** {k['email']['preview_text']}", "", k["email"]["body"], "",
                  f"**Button:** {k['email']['call_to_action']} ({', '.join(k['email']['citations'])})", "",
                  f"### SMS (~{c['sms_send_chars']} chars when sent)", f"> {k['sms']['text']}", "",
                  f"({', '.join(k['sms']['citations'])})", "",
                  f"### Social post ({k['social_post']['platform']})",
                  f"**Concept:** {k['social_post']['concept']}  ",
                  f"**Hook:** {k['social_post']['hook']}", "", k["social_post"]["caption"], "",
                  f"({', '.join(k['social_post']['citations'])})", "",
                  f"### Send plan ({', '.join(k['cadence_citations'])})", "",
                  "| Day | Channel | Action |", "|---|---|---|"]
        lines += [f"| {st['day']} | {st['channel']} | {st['action']} |" for st in k["send_plan"]]
        lines += ["", "### Before you send (owner checklist)"] + [f"- [ ] {x}" for x in k["owner_checklist"]]
        lines += ["", "### Measure"] + [f"- {x}" for x in k["measurement"]]
        lines += ["", "### Risks", k["risks"], ""]
        if c["unflagged_claims"]:
            lines += ["### ⚠ Claims to review (no [CONFIRM] tag)"] + [f"- \"{x}\"" for x in c["unflagged_claims"]] + [""]
        lines += ["### Sources"]
        lines += [f"- {t['ref']}: {trend_label(t)}" for t in r["trends"]]
        lines += [f"- {e['ref']}: Yelp review `{e['id']}`" for e in r["reviews"]]
        lines += ["", f"*Checks:* {c['citations']} citations, validity {c['citation_validity']:.0%}, "
                      f"uncited pieces {c['uncited_pieces'] or 'none'}, pieces without a trend ref "
                      f"{c['pieces_without_trend_ref'] or 'none'}, SMS ~{c['sms_send_chars']} chars "
                      f"{'✅' if c['sms_ok'] else '❌'}, subject {c['subject_chars']} chars "
                      f"{'✅' if c['subject_ok'] else '❌'}, numbers to verify: {c['unsupported_numbers'] or 'none'}, "
                      f"[CONFIRM] flags {c['confirm_flags']}, unflagged claims {len(c['unflagged_claims'])}", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show trend evidence only, no Gemini call")
    ap.add_argument("--segment", default="", help="only segments whose name contains this text")
    ap.add_argument("--fresh", action="store_true", help="ask Gemini again instead of reusing a cached answer")
    args = ap.parse_args(argv)

    profile = load_profile()
    profiles = {seg_name(s): s for s in load_segments()}
    whys = [w for w in load_why() if args.segment.lower() in w["segment"].lower()]
    print(f"Campaign kits | model: {MODEL} | {len(whys)} segments | store profile: {'yes' if profile else 'none'}")

    results = []
    for why in whys:
        s = profiles.get(why["segment"])
        if s is None:
            print(f"⚠ {why['segment']} not found in segments.json; skipped")
            continue
        why_text, review_ev = why_block(why)
        trends = gather_trends(why)
        print(f"\n=== {why['segment']} | {len(review_ev)} reviews, {len(trends)} trend pages "
              f"from {len({t.get('source') for t in trends})} reports")

        if args.dry_run:
            for t in trends:
                print(f"  [{t['ref']}] {t.get('source')} p.{t.get('page')} | {t['text'][:100].strip()}...")
            continue

        start = time.time()
        kit, cached = gemini_json(build_prompt(s, why, why_text, trends, profile), CampaignKit,
                                  model=MODEL, temperature=0.4, refresh=args.fresh)
        c = check_kit(kit, s, review_ev, trends, profile)
        took = "(cached)" if cached else f"Gemini {time.time() - start:.1f}s"
        print(f"  {took} | validity {c['citation_validity']:.0%} | SMS ~{c['sms_send_chars']} "
              f"{'✅' if c['sms_ok'] else '❌'} | subject {c['subject_chars']} {'✅' if c['subject_ok'] else '❌'} | "
              f"offer economics {'✅' if c['offer']['economics_ok'] else '❌'} | "
              f"unflagged claims {len(c['unflagged_claims'])} | numbers to verify: {c['unsupported_numbers'] or 'none'}")
        print(f"  → Offer: {kit['offer']['headline']}")
        meta = {"model": MODEL, "retrieval": "vector (trend reports)", "generated_at": datetime.now().isoformat(timespec="seconds"),
                "from_cache": cached, "seconds": round(time.time() - start, 1), "queries": trend_queries(why),
                "retrieved": len(trends), "reviews_used": len(review_ev)}
        results.append({"segment": why["segment"], "kit": kit, "checks": c,
                        "trends": trends, "reviews": review_ev, "meta": meta})

    if results:
        results = merge_results(OUT_JSON, results)
        OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        OUT_MD.write_text(to_markdown(results), encoding="utf-8")
        print(f"\n✅ Saved {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    utf8_console()
    main()