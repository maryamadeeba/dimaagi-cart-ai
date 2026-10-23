"""Phase 2 wrap-up: automated faithfulness judge for why-summaries, campaign kits and chat answers.

Run:
  python -m eval.judge                    # judge all three output types
  python -m eval.judge --only why|kits|chat
  python -m eval.judge --dry-run          # build prompts, print the first of each type + counts (no Gemini call)

Each output is split into atomic claims; each claim is checked against the exact source text the writer saw.
faithfulness = (supported + 0.5 * partial) / claims.
"""
import argparse
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel

from src.rag.campaign import (MAX_DISCOUNT_RATE, REVIEW_CHARS, SMS_MAX, SUBJECT_MAX, TREND_CHARS, trend_label,
                              why_block)
from src.rag.generate import MAX_REVIEW_CHARS, facts, load_segments, seg_name
from src.console import utf8_console

JUDGE_MODEL = os.getenv("JUDGE_MODEL") or "gemini-3.5-flash-lite"
WHY_PATH = Path("models/why_summaries.json")
KITS_PATH = Path("models/campaign_kits.json")
CHAT_PATH = Path("models/chat_eval_results.json")
PROFILE_PATH = Path("config/store_profile.yaml")
REPORT = Path("reports/faithfulness.md")                  # numbers only, safe to commit
DETAILS_JSON = Path("models/faithfulness_details.json")   # quotes outputs, gitignored
DETAILS_MD = Path("models/faithfulness_details.md")
VERDICTS = ("supported", "partial", "unsupported")
SLEEP = 4

JUDGE_PROMPT = """You are a strict fact-checker. OUTPUT was written using ONLY the SOURCES below (exact text the writer saw).
Split OUTPUT into atomic factual claims. Skip: greetings, questions, instructions to the owner, suggestions/offers,
placeholders like [STORE NAME] or [LINK], and any sentence containing [CONFIRM] (those are intentions to verify, not claims).
For each claim give the refs it cites (empty if none) and a verdict:
supported = the cited sources (or segment facts) state it;
partial = sources support part of it, or it adds a detail, certainty or causality the sources don't have
          (e.g. a reviewer's guess stated as fact, 'frequently' from a few examples);
unsupported = not in the sources, contradicts them, or cites a ref that does not support it.
Numbers must match the sources (rounding is fine). A number attributed to the wrong segment, or a wrong number,
is UNSUPPORTED (not partial). Segment facts are sources: numbers matching them are supported.
Give a one-sentence reason.

WRITER'S TASK (judge the output against what the writer was asked to do):
{task}

OUTPUT:
{output}

SOURCES:
{sources}
"""

TASKS = {
    "why": "Link proxy reviews from OTHER stores to this segment's sales facts as LIKELY causes. Hedged links "
           "('may', 'likely', 'could', 'aligns with') between a supported review claim and a supported segment fact are "
           "the intended task: mark them supported. Flag certainty the sources don't give ('will', 'directly', 'definitely').",
    "kits": "Write marketing copy and an offer from the reasons analysis, trends and rules given. Persuasive wording and "
            "suggestions are not claims.",
    "chat": "Answer the owner's question from tool results. Saying reviews come from 'other stores' is the required "
            "framing (reviews are a proxy), not an unsupported claim.",
}


def judge_prompt(typ, output, sources):
    return JUDGE_PROMPT.format(task=TASKS[typ], output=output, sources=sources)


class ClaimVerdict(BaseModel):
    claim: str
    refs: list[str]
    verdict: str
    reason: str


class Judgement(BaseModel):
    claims: list[ClaimVerdict]


# ---------- scoring ----------
def normalise_verdict(v):
    v = str(v).strip().lower()
    return v if v in VERDICTS else "unsupported"


def faithfulness(verdicts):
    """(supported + 0.5 * partial) / claims, or None if there are no claims."""
    if not verdicts:
        return None
    return (verdicts.count("supported") + 0.5 * verdicts.count("partial")) / len(verdicts)


# ---------- OUTPUT / SOURCES builders (SOURCES = the same text the writer saw) ----------
def _facts_block(seg_facts, lapsed=()):
    lines = [f"SEGMENT FACTS: {json.dumps(seg_facts, ensure_ascii=False)}"]
    if lapsed:
        lines.append(f"Categories this segment cut back on: {', '.join(lapsed)}")
    return "\n".join(lines)


def why_output(w):
    s = w["summary"]
    lines = [f"Headline: {s['headline']}"]
    for r in s["reasons"]:
        lines.append(f"- {r['reason'].rstrip('.')}. {r['explanation']} ({', '.join(r['citations'])})")
    lines.append(f"Evidence gaps: {s['evidence_gaps']}")
    return "\n".join(lines)


def why_sources(w, seg_facts):
    lines = [f'[{e["ref"]}] {e["text"][:MAX_REVIEW_CHARS].strip()}' for e in w["evidence"]]
    return "\n".join(lines + [_facts_block(seg_facts, w.get("lapsed_categories", []))])


def kit_output(record):
    k = record["kit"]
    o, e, sm, so = k["offer"], k["email"], k["sms"], k["social_post"]
    return "\n".join([
        f"Goal: {k['goal']}",
        f"Offer headline: {o['headline']}",
        f"Offer details: {o['details']}",
        f"Why this offer: {o['why_this_offer']} ({', '.join(o['citations'])})",
        f"Email subject: {e['subject']}",
        f"Email preview: {e['preview_text']}",
        f"Email body ({', '.join(e['citations'])}):\n{e['body']}",
        f"SMS ({', '.join(sm['citations'])}): {sm['text']}",
        f"Social hook: {so['hook']}",
        f"Social caption ({', '.join(so['citations'])}): {so['caption']}",
    ])


WRITER_RULES = (f"- SMS: at most {SMS_MAX} characters including the opt-out.\n"
                f"- Email subject: at most {SUBJECT_MAX} characters.\n"
                f"- Offer: discount at most {MAX_DISCOUNT_RATE:.0%} of the minimum basket; the minimum basket must be "
                "above the segment's median weekly spend.")


def kit_sources(record, seg_facts, profile_text, lapsed=(), why=None):
    """`why` is the segment's record from why_summaries.json; its reasons text is rebuilt with campaign.why_block."""
    lines = [f'[{r["ref"]}] {r["text"][:REVIEW_CHARS].strip()}' for r in record.get("reviews", [])]
    lines += [f'[{t["ref"]}] {trend_label(t)}: {t["text"][:TREND_CHARS].strip()}' for t in record.get("trends", [])]
    lines.append(_facts_block(seg_facts, lapsed))
    lines.append(f"STORE PROFILE:\n{profile_text.strip() or '(none)'}")
    if why:
        lines.append(f"REASONS ANALYSIS GIVEN TO THE WRITER:\n{why_block(why)[0]}")
    lines.append(f"RULES GIVEN TO THE WRITER (claims that restate these are supported):\n{WRITER_RULES}")
    return "\n".join(lines)


def chat_sources(r):
    return "\n".join(f"[{ref}] {m.get('text', '')}" for ref, m in r["sources"].items())


# ---------- inputs ----------
def _load(path):
    if not path.exists():
        print(f"⚠ {path} not found: skipped")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_items(only):
    """Return {type: [(id, output, sources), ...]} for the requested types."""
    seg_facts = {seg_name(s): facts(s) for s in load_segments()}
    whys = _load(WHY_PATH) if only in (None, "why", "kits") else None
    why_by_seg = {w["segment"]: w for w in (whys or [])}
    lapsed = {seg: w.get("lapsed_categories", []) for seg, w in why_by_seg.items()}
    items = {}
    if only in (None, "why") and whys:
        items["why"] = [(w["segment"], why_output(w), why_sources(w, seg_facts.get(w["segment"], {}))) for w in whys]
    if only in (None, "kits"):
        kits = _load(KITS_PATH)
        profile = PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else ""
        if kits:
            items["kits"] = [(k["segment"], kit_output(k),
                              kit_sources(k, seg_facts.get(k["segment"], {}), profile, lapsed.get(k["segment"], []),
                                          why_by_seg.get(k["segment"])))
                             for k in kits]
    if only in (None, "chat"):
        chats = _load(CHAT_PATH)
        if chats:
            items["chat"] = [(r["qid"], r["answer"], chat_sources(r)) for r in chats if r["tools"]]
    return items


# ---------- reporting ----------
def _fmt(score):
    return "n/a" if score is None else f"{score:.0%}"


def write_reports(results):
    lines = ["# Faithfulness (automated judge)", "",
             "> These are the judge's RAW verdicts. Every partial/unsupported flag was then reviewed by hand; the "
             "human-reviewed figures (e.g. 95% why / 100% kits / 100% chat in run B, 97% over 229 claims) are in "
             "reports/rag_log.md (Day 9–10). Judge precision on its flags was ~60%, so raw scores understate "
             "faithfulness where the judge is too strict.", "",
             f"Judge model: `{JUDGE_MODEL}`, temperature 0. Each output is split into atomic claims and each claim "
             "is checked against the exact source text the writer saw. "
             "Faithfulness = (supported + 0.5 × partial) / claims.", "",
             "## Summary", "",
             "| Type | Outputs | Claims | % supported | % partial | % unsupported | Mean faithfulness |",
             "|---|---|---|---|---|---|---|"]
    for typ, rows in results.items():
        verdicts = [v for r in rows for v in r["verdicts"]]
        n = len(verdicts) or 1
        scores = [r["score"] for r in rows if r["score"] is not None]
        mean = sum(scores) / len(scores) if scores else None
        lines.append(f"| {typ} | {len(rows)} | {len(verdicts)} | {verdicts.count('supported') / n:.0%} | "
                     f"{verdicts.count('partial') / n:.0%} | {verdicts.count('unsupported') / n:.0%} | {_fmt(mean)} |")
    for typ, rows in results.items():
        lines += ["", f"## {typ}", "", "| ID | Claims | S / P / U | Faithfulness |", "|---|---|---|---|"]
        for r in rows:
            v = r["verdicts"]
            lines.append(f"| {r['id']} | {len(v)} | {v.count('supported')} / {v.count('partial')} / "
                         f"{v.count('unsupported')} | {_fmt(r['score'])} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    details = {typ: [{"id": r["id"], "score": r["score"],
                      "issues": [c for c in r["claims"] if c["verdict"] != "supported"]} for r in rows]
               for typ, rows in results.items()}
    DETAILS_JSON.write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["# Faithfulness details (partial and unsupported claims)", "", f"Judge model: `{JUDGE_MODEL}`", ""]
    for typ, rows in details.items():
        md += [f"## {typ}", ""]
        for r in rows:
            md += [f"### {r['id']} ({_fmt(r['score'])})", ""]
            md += [f"- **{c['verdict']}** {c['claim']} (refs: {', '.join(c['refs']) or 'none'}) → {c['reason']}"
                   for c in r["issues"]] or ["- no issues"]
            md.append("")
    DETAILS_MD.write_text("\n".join(md), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["why", "kits", "chat"], help="judge one output type only")
    ap.add_argument("--dry-run", action="store_true", help="build prompts and print the first of each type; no Gemini call")
    args = ap.parse_args()

    items = build_items(args.only)
    print(f"Faithfulness judge | model: {JUDGE_MODEL} | "
          + ", ".join(f"{t}: {len(v)} outputs" for t, v in items.items()))
    if args.dry_run:
        for typ, rows in items.items():
            if rows:
                oid, output, sources = rows[0]
                print(f"\n===== {typ}: first prompt ({oid}) | {len(rows)} outputs =====\n")
                print(judge_prompt(typ, output, sources))
        return

    from src.rag.gemini import gemini_json
    results = {}
    for typ, rows in items.items():
        results[typ] = []
        for oid, output, sources in rows:
            out, cached = gemini_json(judge_prompt(typ, output, sources), Judgement,
                                      model=JUDGE_MODEL, temperature=0.0)
            claims = [{**c, "verdict": normalise_verdict(c["verdict"])} for c in out["claims"]]
            verdicts = [c["verdict"] for c in claims]
            score = faithfulness(verdicts)
            results[typ].append({"id": oid, "claims": claims, "verdicts": verdicts, "score": score})
            print(f"  {typ} | {oid} | {len(verdicts)} claims | S/P/U {verdicts.count('supported')}/"
                  f"{verdicts.count('partial')}/{verdicts.count('unsupported')} | {_fmt(score)}"
                  f"{' (cached)' if cached else ''}", flush=True)
            if not cached:
                time.sleep(SLEEP)

    write_reports(results)
    print(f"\n✅ Saved {REPORT}, {DETAILS_JSON} and {DETAILS_MD}")


if __name__ == "__main__":
    utf8_console()
    main()
