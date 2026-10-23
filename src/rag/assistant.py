"""Day 8: Dimaagi Cart assistant chat. Gemini picks tools (function calling) to answer the owner's questions with citations.

Run:
  python -m src.rag.assistant                                          # interactive chat, keeps context (type 'exit' to quit)
  python -m src.rag.assistant "Why are my high-value customers leaving?"  # one question, no memory
"""
import functools
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.rag.generate import facts, lapsed_categories, load_segments, seg_name, stars, theme
from src.rag.refs import PLACEHOLDERS, REF_PATTERN, parse_citations, refs_in  # noqa: F401 (re-exported)
from src.rag.hybrid import search as hybrid_search
from src.rag.retriever import search_trends as _search_trends
from src.console import utf8_console

CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.5-flash-lite")
CHAT_RETRIEVAL = os.getenv("CHAT_RETRIEVAL", "hybrid")      # fast: 0.12s vs 1.7s with reranking (Day 6)
WHY_PATH = Path("models/why_summaries.json")
KITS_PATH = Path("models/campaign_kits.json")
REVIEWS_PER_SEARCH = 5
TRENDS_PER_SEARCH = 4
MAX_TOOL_CALLS = 6
CALL_TIMEOUT_MS = 60_000                                     # a stalled Gemini call fails after 60s and is retried
RETRYABLE = ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE", "timed out", "Timeout")

SYSTEM = """You are Dimaagi, the Dimaagi Cart assistant for the owner of a small independent grocery store. You help them understand which customers are drifting away, why, and what to do about it.

Rules:
- For ANY question about their customers, segments, reviews, marketing evidence or campaigns, call tools first. Never answer those from general knowledge.
- Pick the right tool: list_segments for who, how many and how much is at risk; get_segment_reasons for why a segment is leaving; search_reviews for what shoppers say about a topic; search_marketing_trends for tactics, benchmarks and best practices; get_campaign_kit for what to send and what to fix first. Combine tools when the question needs it.
- If it's unclear WHICH segment the owner means (e.g. "them" with no earlier context), do not guess: ask a short question listing the segment names (call list_segments to get them).
- When you list items from one source, cite it on the lead-in line or on each item.
- Cite every factual claim with the ref from the tool result in square brackets, e.g. [S_highvalue], [R3], [T2], [K_highvalue], [W_highvalue]. Cite evidence gaps and reasons-analysis statements with the W_ ref. Use only refs that tools returned, and use the ref of the SAME segment the claim is about. Never put tool names or anything else in square brackets.
- For each reason from get_segment_reasons, cite that reason's own R refs (its "sources"). Use the W_ ref ONLY for evidence gaps and statements about what the analysis could not confirm. Use S_ refs only for numbers and lapsed categories from sales data.
- Every number about the owner's customers (counts, revenue at risk, spend) must come from a segment tool and be followed by that segment's S_ ref. Marketing statistics only from T refs.
- Never calculate totals or percentages yourself: use the numbers tools return (e.g. totals with [S_all]).
- Search results are examples, not counts: never say a complaint is common, frequent or typical based on search results. Say 'several reviews mention...' instead.
- Reviews are from OTHER grocery stores (a proxy voice): say "shoppers at other stores complain...", never "your customers said...".
- If the tools return nothing relevant, say so plainly. Don't guess.
- If a question is outside this scope (weather, general chat, coding), do not call tools; say briefly what you can help with.
- Answer in plain English for a busy shop owner: at most 150 words, short bullets when listing.
"""


# ---------- session: refs issued by tools, and which tools were called ----------
class Session:
    def __init__(self):
        self.refs, self.counts, self.tool_log = {}, {"R": 0, "T": 0}, []
        self.tool_seconds = 0.0

    def ref(self, kind, key, label, fixed=None, text=""):
        """Return the ref for a source, creating it once. `fixed` gives a self-describing ref (S_/K_/W_).
        `text` is the exact source text the model was shown, kept so a judge can check answers later."""
        for r, m in self.refs.items():
            if m["key"] == key:
                return r
        if fixed:
            r = fixed
        else:
            self.counts[kind] += 1
            r = f"{kind}{self.counts[kind]}"
        self.refs[r] = {"key": key, "label": label, "text": text}
        return r

    def log(self, tool, args):
        self.tool_log.append({"tool": tool, "args": args})


SESSION = Session()


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _slug(s):
    """'High-value · at risk' -> 'highvalue', 'Core · Basket changed' -> 'corebasket'."""
    return "".join(re.findall(r"[a-z]+", seg_name(s).lower())[:2])


def find_segment(name):
    """Match 'high value', 'core visiting less', etc. to a segment profile."""
    segs = load_segments()
    n = _norm(name)
    for s in segs:
        sn = _norm(seg_name(s))
        if n and (n in sn or sn in n):
            return s
    words = set(re.findall(r"[a-z]+", name.lower()))
    scored = [(len(words & set(re.findall(r"[a-z]+", seg_name(s).lower()))), s) for s in segs]
    best = max(scored, key=lambda x: x[0], default=(0, None))
    return best[1] if best[0] > 0 else None


def _segment_numbers(s):
    """Segment facts plus share of revenue at risk and revenue at risk per customer, computed in code."""
    total_revenue = sum(x["weekly_revenue_at_risk"] for x in load_segments())
    return {**facts(s),
            "share_of_revenue_at_risk": round(s["weekly_revenue_at_risk"] / total_revenue, 3) if total_revenue else 0.0,
            "revenue_at_risk_per_customer": round(s["weekly_revenue_at_risk"] / s["customers"], 2) if s["customers"] else 0.0}


def _segment_ref(s):
    text = json.dumps({**_segment_numbers(s), "lapsed_categories": lapsed_categories(s)}, ensure_ascii=False)
    return SESSION.ref("S", f"seg:{seg_name(s)}", f"Your sales data: {seg_name(s)}", fixed=f"S_{_slug(s)}", text=text)


def _no_segment(segment):
    return {"error": f"No segment matches '{segment}'.", "available": [seg_name(x) for x in load_segments()]}


# ---------- tools (Gemini reads these docstrings to decide which to call) ----------
def list_segments() -> dict:
    """List the at-risk customer segments from the owner's sales data: size, weekly revenue at risk,
    median weekly spend, main reason (visiting less or basket changed), the product categories they cut back on,
    each segment's share of revenue at risk and revenue at risk per customer, plus totals across all segments.
    Use for overview questions: who is leaving, how many, how much money is at risk, which group matters most.
    For "which group to focus on", weigh both total revenue at risk and value per customer."""
    SESSION.log("list_segments", {})
    segs = load_segments()
    segments = [{"ref": _segment_ref(s), "segment": seg_name(s), "main_reason": theme(s),
                 "lapsed_categories": lapsed_categories(s), **_segment_numbers(s)} for s in segs]
    totals = {"customers": sum(s["customers"] for s in segs),
              "weekly_revenue_at_risk": round(sum(s["weekly_revenue_at_risk"] for s in segs), 2)}
    totals["ref"] = SESSION.ref("S", "seg:all", "Your sales data: all at-risk segments", fixed="S_all",
                                text=json.dumps(totals))
    return {"segments": segments, "totals": totals}


def get_segment_reasons(segment: str) -> dict:
    """Explain WHY one at-risk segment is drifting away: likely reasons backed by customer reviews, plus evidence gaps.
    `segment` is the segment's name or a description, e.g. 'high-value' or 'core visiting less'."""
    SESSION.log("get_segment_reasons", {"segment": segment})
    s = find_segment(segment)
    if s is None:
        return _no_segment(segment)
    if not WHY_PATH.exists():
        return {"error": "Reasons not generated yet (run python -m src.rag.generate)."}
    why = next((w for w in json.loads(WHY_PATH.read_text(encoding="utf-8")) if w["segment"] == seg_name(s)), None)
    if why is None:
        return {"error": f"No reasons generated for {seg_name(s)}."}
    ev = {e["ref"]: e for e in why["evidence"]}
    reasons, reviews = [], {}
    for r in why["summary"]["reasons"]:
        sources = []
        for old in [x for c in r["citations"] for x in refs_in(c)]:
            e = ev.get(old)
            if not e:
                continue
            new = SESSION.ref("R", e["id"], f"Yelp review {e['id']} ({stars(e) or '?'}★, another store)",
                              text=e["text"][:300])
            sources.append(new)
            reviews[new] = {"stars": stars(e), "text": e["text"][:300]}
        reasons.append({"reason": r["reason"], "explanation": r["explanation"], "sources": sources})
    analysis = {"headline": why["summary"]["headline"], "reasons": reasons,
                "evidence_gaps": why["summary"]["evidence_gaps"]}
    return {"segment": seg_name(s), "segment_ref": _segment_ref(s),
            "analysis_ref": SESSION.ref("W", f"why:{seg_name(s)}",
                                        f"Reasons analysis: {seg_name(s)} (models/why_summaries.md)",
                                        fixed=f"W_{_slug(s)}", text=json.dumps(analysis, ensure_ascii=False)),
            "segment_facts": facts(s),
            "headline": why["summary"]["headline"], "reasons": reasons,
            "evidence_gaps": why["summary"]["evidence_gaps"], "reviews": reviews,
            "note": "Reviews are from OTHER grocery stores (a proxy voice), not this store's customers. "
                    "Numbers in segment_facts and headline come from the owner's sales data: cite segment_ref. "
                    "Cite evidence_gaps and reasons-analysis statements with analysis_ref."}


def search_reviews(query: str) -> dict:
    """Search 25,000 Yelp reviews of OTHER grocery stores for what shoppers complain about on a topic,
    e.g. 'expired milk', 'long checkout lines', 'prices too high'. Returns 1-3 star reviews only."""
    SESSION.log("search_reviews", {"query": query})
    out = []
    for h in hybrid_search(query, CHAT_RETRIEVAL, REVIEWS_PER_SEARCH * 3):
        if stars(h) is not None and stars(h) > 3:
            continue
        ref = SESSION.ref("R", h["id"], f"Yelp review {h['id']} ({stars(h) or '?'}★, another store)",
                          text=h["text"][:300])
        out.append({"ref": ref, "stars": stars(h), "text": h["text"][:300]})
        if len(out) == REVIEWS_PER_SEARCH:
            break
    return {"query": query, "reviews": out,
            "note": "Reviews are from OTHER grocery stores (a proxy voice), not this store's customers."}


def search_marketing_trends(query: str) -> dict:
    """Search published marketing and retail reports (Listrak, Klaviyo, Merkle, Bond, McKinsey, Deloitte,
    Sprout Social, Hootsuite, a win-back playbook) for tactics, benchmarks, best practices and trends,
    e.g. 'SMS best practices', 'win-back email cadence', 'loyalty program value'."""
    SESSION.log("search_marketing_trends", {"query": query})
    out = []
    for h in _search_trends(query, k=TRENDS_PER_SEARCH):
        label = f"{h.get('publisher', '')} {h.get('year', '')}, \"{h.get('title', h.get('source', ''))}\", p.{h.get('page', '?')}"
        out.append({"ref": SESSION.ref("T", h["id"], label, text=h["text"][:500]), "report": label,
                    "text": h["text"][:500]})
    return {"query": query, "pages": out}


def get_campaign_kit(segment: str) -> dict:
    """Get the ready-made win-back campaign kit for one segment: the offer, email subject, SMS text, send plan,
    how to measure it, and the owner's checklist of things to fix BEFORE sending.
    `segment` is the segment's name or a description, e.g. 'high-value' or 'core visiting less'."""
    SESSION.log("get_campaign_kit", {"segment": segment})
    s = find_segment(segment)
    if s is None:
        return _no_segment(segment)
    if not KITS_PATH.exists():
        return {"error": "Campaign kits not generated yet (run python -m src.rag.campaign)."}
    kit = next((k for k in json.loads(KITS_PATH.read_text(encoding="utf-8")) if k["segment"] == seg_name(s)), None)
    if kit is None:
        return {"error": f"No campaign kit for {seg_name(s)}."}
    k = kit["kit"]
    out = {"segment": seg_name(s), "segment_ref": _segment_ref(s), "segment_facts": facts(s), "goal": k["goal"],
           "offer": {"headline": k["offer"]["headline"], "details": k["offer"]["details"],
                     "perk": k["offer"]["non_monetary_perk"]},
           "email_subject": k["email"]["subject"], "sms": k["sms"]["text"], "send_plan": k["send_plan"],
           "owner_checklist": k["owner_checklist"], "measurement": k["measurement"]}
    ref = SESSION.ref("K", f"kit:{seg_name(s)}", f"Campaign kit: {seg_name(s)} (models/campaign_kits.md)",
                      fixed=f"K_{_slug(s)}", text=json.dumps(out, ensure_ascii=False))
    return {"ref": ref, **out}


def timed(fn):
    """Add the tool's run time to SESSION.tool_seconds. functools.wraps keeps the name, docstring,
    signature and type hints that Gemini's automatic function calling reads."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            return fn(*args, **kwargs)
        finally:
            SESSION.tool_seconds += time.time() - start
    return wrapper


TOOLS = [timed(f) for f in (list_segments, get_segment_reasons, search_reviews, search_marketing_trends, get_campaign_kit)]


# ---------- chat ----------
def make_client():
    from google import genai
    from google.genai import types
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS))



def make_chat(client):
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=TOOLS,
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=MAX_TOOL_CALLS),
    )
    return client.chats.create(model=CHAT_MODEL, config=config)


ANSWER_NUMBER = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?%?")   # $2,700.75, 40.1%, 272
SOURCE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _to_float(raw):
    return float(raw.strip("$%").replace(",", ""))


def _number_matches(raw, stored):
    """True if `raw` equals a stored number, allowing rounding to 0-2 decimals and 40.1% ~ 0.401."""
    v = _to_float(raw)
    for c in stored:
        for cand in ((c, c * 100) if raw.endswith("%") else (c,)):
            if abs(cand - v) < 1e-6 or any(abs(round(cand, d) - v) < 1e-6 for d in (0, 1, 2)):
                return True
    return False


def _units(answer):
    """Split into checkable units, each with the citations it inherits: each bullet/list line is ONE unit (so a
    quoted SMS keeps the bullet's trailing citation) and inherits the refs of its list's lead-in line (the nearest
    non-bullet line above it, e.g. "complete these fixes [K_corevisiting]:"); other paragraphs are split into
    sentences, and a trailing '[R3].' fragment stays with its sentence. Returns [(text, inherited_refs)]."""
    out, lead = [], []
    for line in answer.splitlines():
        bullet = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line)      # list markers are not numbers
        if bullet != line:
            if bullet.strip():
                out.append((bullet, lead))
            continue
        if not line.strip():
            continue                                                    # a blank line keeps the lead-in
        lead = sorted(set(REF_PATTERN.findall(line)))
        for part in re.split(r"(?<=[.!?])\s+", line):
            if out and re.fullmatch(r"(\s*\[[^\]]*\]\s*)+[.!?]?", part):
                out[-1] = (out[-1][0] + " " + part, out[-1][1])
            elif part.strip():
                out.append((part, []))
    return out


def _sentences(answer):
    return [text for text, _ in _units(answer)]


def check_numbers(answer, refs):
    """Numbers in the answer that don't appear in the text of the ref cited for them. Each number is checked
    against the first citation after it in the same sentence (so '$12.98 for Core visiting less [S_corevisiting]'
    is checked against S_corevisiting only); numbers after the last citation use every ref the sentence cites.
    A bullet that cites nothing itself uses its list's lead-in citations; a bullet with its own citation keeps it."""
    def stored(cited):
        return [_to_float(n) for c in cited if c in refs
                for n in SOURCE_NUMBER.findall(f"{refs[c].get('text', '')} {refs[c].get('label', '')}") if n.strip(",")]

    issues = []
    for sentence, inherited in _units(answer):
        merged = re.sub(r"\]\s*\[", ", ", sentence)                      # [S_highvalue][S_all] -> one citation
        sentence_refs = sorted(set(REF_PATTERN.findall(merged))) or inherited
        chunks, pending = [], ""
        for part in re.split(r"(\[[^\]]*\])", merged):
            refs_here = REF_PATTERN.findall(part) if part.startswith("[") else []
            if refs_here:
                chunks.append((pending, sorted(set(refs_here))))
                pending = ""
            elif not part.startswith("["):                               # placeholders like [STORE NAME] are dropped
                pending += part
        chunks.append((pending, sentence_refs))
        for text, cited in chunks:
            numbers = stored(cited)
            for raw in ANSWER_NUMBER.findall(REF_PATTERN.sub(" ", text)):
                raw = raw.rstrip(",")
                if not _number_matches(raw, numbers):
                    issues.append({"sentence": sentence.strip(), "number": raw, "cited": cited})
    return issues


def ask(chat, question):
    start, n_before, tools_before = time.time(), len(SESSION.tool_log), SESSION.tool_seconds
    for attempt in range(4):
        try:
            resp = chat.send_message(question)
            break
        except Exception as e:
            msg = str(e)
            if "PerDay" in msg or "per day" in msg.lower():
                raise SystemExit("\n⏸ Daily Gemini quota used up for the chat model. Try later or set CHAT_MODEL in .env.")
            if not any(code in msg for code in RETRYABLE) or attempt == 3:
                raise
            wait = 20 * (attempt + 1)
            print(f"  Gemini busy, rate-limited or timed out ({msg[:60]}), retrying in {wait}s", flush=True)
            time.sleep(wait)
    answer = resp.text or "(no answer: the model stopped after calling tools)"
    cited, invalid = parse_citations(answer, SESSION.refs)
    total, tool_s = time.time() - start, SESSION.tool_seconds - tools_before
    tools = [t["tool"] for t in SESSION.tool_log[n_before:]]
    return {"answer": answer, "tools": tools,
            "tool_args": SESSION.tool_log[n_before:], "cited": cited, "invalid": invalid,
            "validity": round(1 - len(invalid) / len(cited), 3) if cited else None,
            "ungrounded_numbers": check_numbers(answer, SESSION.refs),
            "seconds": round(total, 1), "tool_seconds": round(tool_s, 2),
            "model_seconds": round(total - tool_s, 1), "model_calls_est": len(tools) + 1}


def print_turn(r):
    print(f"\nAssistant: {r['answer']}")
    validity = f"{r['validity']:.0%}" if r["validity"] is not None else "n/a"
    print(f"\n  [tools: {', '.join(r['tools']) or 'none'} | citations valid: {validity} | "
          f"{r['seconds']}s total = model {r['model_seconds']}s (~{r['model_calls_est']} calls) + tools {r['tool_seconds']}s]")
    for c in r["cited"]:
        print(f"  {c}: {SESSION.refs[c]['label'] if c in SESSION.refs else '⚠ not a source any tool returned'}")
    if r.get("ungrounded_numbers"):
        print("  ⚠ ungrounded numbers: " + "; ".join(
            f"{u['number']} (cited: {', '.join(u['cited']) or 'none'})" for u in r["ungrounded_numbers"]))


def main():
    client = make_client()
    chat = make_chat(client)
    print(f"Dimaagi Cart assistant | model: {CHAT_MODEL} | retrieval: {CHAT_RETRIEVAL}")
    if len(sys.argv) > 1:
        print_turn(ask(chat, " ".join(sys.argv[1:])))
        return
    print("Ask about your at-risk customers, why they're leaving, or what to send. Type 'exit' to quit.")
    while True:
        try:
            q = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        if q.lower() in ("exit", "quit"):
            break
        if q:
            print_turn(ask(chat, q))


if __name__ == "__main__":
    utf8_console()
    main()