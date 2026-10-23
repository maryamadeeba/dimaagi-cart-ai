"""Day 5-6: a cited "why they're leaving" summary for each at-risk segment.

Run:
  python -m src.rag.generate --dry-run       # show retrieved evidence only (no Gemini call)
  python -m src.rag.generate                 # generate summaries for all segments
  python -m src.rag.generate --segment core  # only segments whose name contains "core"
"""
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from src.rag.gemini import gemini_json
from src.rag.hybrid import search as retrieve
from src.rag.refs import refs_in
from src.console import utf8_console

SEGMENTS_PATH = Path("models/segments.json")
OUT_JSON = Path("models/why_summaries.json")
OUT_MD = Path("models/why_summaries.md")        # contains Yelp quotes, so it stays gitignored
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
RETRIEVAL_METHOD = os.getenv("RETRIEVAL_METHOD", "hybrid_rerank")

TOP_CATEGORIES = 3     # lapsed categories to search per segment
PER_QUERY = 12         # reviews fetched per query (before filters)
PER_QUERY = 20         # reviews fetched per query (before filters)
MIN_RERANK = 1.0       # drop weak reranker matches (Day 6 dry run: off-topic hits scored ~0.1)
MAX_EVIDENCE = 12      # reviews passed to Gemini per segment
MAX_STARS = 3          # complaints only
MAX_REVIEW_CHARS = 600
MAX_DIST = 0.48        # only used for plain vector search (BM25/hybrid results have no distance)

# How shoppers actually say it (dunnhumby category -> everyday words)
CATEGORY_ALIASES = {
    "BAKED BREAD/BUNS/ROLLS": "bread",
    "FLUID MILK PRODUCTS": "milk",
    "CHEESE": "cheese",
    "SOUP": "soup",
    "BEEF": "meat beef",
    "SOFT DRINKS": "soda drinks",
    "FROZEN PIZZA": "frozen pizza",
    "BAG SNACKS": "chips snacks",
}

THEME_QUERIES = {
    "visiting less": [
        "stopped shopping here and switched to another grocery store",
        "prices too high, got more expensive",
        "long lines and slow checkout, not worth the trip",
    ],
    "basket changed": [
        "items always out of stock, empty shelves",
        "produce and food not fresh, poor quality",
        "selection got worse, can't find what I need",
    ],
}
GENERIC_WORDS = r"\b(products?|misc|other|all|items?|n/?a)\b"


# ---------- output schema ----------
class Reason(BaseModel):
    reason: str
    explanation: str
    citations: list[str]


class WhySummary(BaseModel):
    headline: str
    reasons: list[Reason]
    evidence_gaps: str


# ---------- reading segments.json (tolerant of its exact shape) ----------
def load_segments():
    data = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "segments" in data:
        data = data["segments"]
    if isinstance(data, dict):                       # {name: profile}
        return [{"name": k, **v} for k, v in data.items()]
    return data


def seg_name(s):
    return str(s.get("name") or s.get("segment") or s.get("label") or "Unnamed segment")


def lapsed_categories(s):
    key = next((k for k in s if "lapsed" in k.lower()), None) \
        or next((k for k in s if "categor" in k.lower()), None)
    if not key or not isinstance(s[key], list):
        return []
    cats = []
    for item in s[key]:
        if isinstance(item, str):
            cats.append(item)
        elif isinstance(item, (list, tuple)) and item:
            cats.append(str(item[0]))
        elif isinstance(item, dict):
            cats.append(str(item.get("category") or item.get("commodity")
                            or item.get("name") or next(iter(item.values()))))
    return cats[:TOP_CATEGORIES]


def theme(s):
    """The segment's main reason. segments.json stores the real split in reason_mix (e.g. High-value is
    59% visiting less); the name is only a fallback, since 'High-value · at risk' says nothing about the reason."""
    mix = s.get("reason_mix") or {}
    if mix:
        text = max(mix, key=mix.get).lower()
    else:
        text = f"{seg_name(s)} {s.get('reason', '')} {s.get('theme', '')}".lower()
    return "visiting less" if "visit" in text else "basket changed"


def facts(s):
    """Only simple values (numbers, short text) go to the LLM as citable facts."""
    return {k: v for k, v in s.items() if isinstance(v, (int, float, str)) and len(str(v)) < 120}


# ---------- retrieval ----------
def stars(h):
    v = h.get("stars", h.get("rating"))
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def category_terms(cat):
    """Everyday word(s) for a dunnhumby category, e.g. 'FLUID MILK PRODUCTS' -> 'milk'."""
    c = CATEGORY_ALIASES.get(cat.upper())
    if not c:
        c = re.sub(r"[/&,]", " ", cat.lower())
        c = re.sub(GENERIC_WORDS, " ", c)
        c = re.sub(r"\s+", " ", c).strip()
    return c


def category_query(cat):
    c = category_terms(cat)
    return f"{c}: {c} not fresh, expired, poor quality, overpriced or out of stock"


def mentions(text, terms):
    """True if the review actually names the product (allows plurals: 'loaf' won't match, 'cheeses' will)."""
    return any(re.search(rf"\b{re.escape(w)}(s|es)?\b", text, re.IGNORECASE) for w in terms.split())


def keep(h):
    if stars(h) is not None and stars(h) > MAX_STARS:
        return False
    if RETRIEVAL_METHOD == "vector" and h.get("distance", 0) > MAX_DIST:
        return False
    if "rerank" in h and h["rerank"] < MIN_RERANK:
        return False
    return True


def evidence_queries(s):
    """(label, query, words a review must mention) for each lapsed category, then the segment's theme."""
    queries = [(f"category: {c.lower()}", category_query(c), category_terms(c)) for c in lapsed_categories(s)]
    return queries + [(f"theme: {theme(s)}", q, None) for q in THEME_QUERIES[theme(s)]]


def gather_evidence(s):
    results = []
    for label, q, terms in evidence_queries(s):
        hits = [h for h in retrieve(q, RETRIEVAL_METHOD, PER_QUERY)
                if keep(h) and (terms is None or mentions(h["text"], terms))]
        results.append((label, hits))

    # round-robin so every query contributes, no duplicates
    seen, evidence = set(), []
    while len(evidence) < MAX_EVIDENCE and any(hits for _, hits in results):
        for label, hits in results:
            while hits:
                h = hits.pop(0)
                if h["id"] not in seen:
                    seen.add(h["id"])
                    evidence.append({**h, "query": label})
                    break
            if len(evidence) >= MAX_EVIDENCE:
                break
    for i, e in enumerate(evidence, 1):
        e["ref"] = f"R{i}"
    return evidence


def score_label(e):
    for key in ("rerank", "rrf", "distance", "bm25"):
        if key in e:
            return f"{key} {e[key]}"
    return ""

# ---------- generation ----------
def build_prompt(s, evidence):
    review_lines = "\n".join(
        f'[{e["ref"]}] ({stars(e) or "?"}★, matched {e["query"]}) '
        f'"{e["text"][:MAX_REVIEW_CHARS].strip()}"'
        for e in evidence
    )
    cats = ", ".join(lapsed_categories(s)) or "none recorded"
    return f"""You are helping a small grocery store owner understand why a group of their regular customers is drifting away.

SEGMENT: {seg_name(s)}
SEGMENT FACTS (from the owner's own sales data; these are the ONLY numbers you may use):
{json.dumps(facts(s), indent=2)}
Categories this segment cut back on most, compared with healthy customers: {cats}

CUSTOMER REVIEWS (Yelp reviews of OTHER grocery stores, used as a proxy for what grocery shoppers complain about; they are NOT this store's customers):
{review_lines}

TASK: Write 3 to 5 likely reasons this segment is drifting away.
Rules:
- Every reason must cite review refs (like "R3") that directly support THAT reason. Cite 2 to 3 refs when the reviews allow. Cite a review only if it actually mentions what the reason claims.
- Each reason must be distinct: never two reasons about the same problem or the same category.
- Use the strongest evidence first: if several reviews describe the same problem, that problem should be one of the reasons.
- Use only numbers from SEGMENT FACTS. Never invent statistics or percentages. Write money rounded with commas (e.g. $3,532).
- "Revenue at risk" is what these customers currently spend per week and could be lost. Never describe it as money they have already stopped spending.
- Because reviewers are not this store's customers, phrase reasons as likely causes ("reviewers at other stores complain that..."), not proven facts.
- Connect reasons to the lapsed categories ONLY where the reviews are about buying that item as groceries. If reviews matched to a category are really about prepared food (sandwiches, deli soup, hot food), say so plainly and note it in evidence_gaps instead of treating it as evidence about the grocery category.
- Never add details the reviews don't mention (e.g. don't say "for months" if the review gives no time span). Don't say "often" or "frequently" unless 3 or more cited reviews show it.
- evidence_gaps must be specific to this segment (which categories or themes lack good evidence). Don't just repeat that the reviews come from other stores.
- headline: one plain-English sentence for a busy shop owner. Each explanation: at most 2 sentences.
"""

def check_citations(summary, evidence):
    valid = {e["ref"] for e in evidence}
    cited = [ref for r in summary["reasons"] for c in r["citations"] for ref in refs_in(c)]
    invalid = [c for c in cited if c not in valid]
    return {
        "n_reasons": len(summary["reasons"]),
        "n_citations": len(cited),
        "invalid_citations": invalid,
        "citation_validity": round(1 - len(invalid) / len(cited), 3) if cited else 0.0,
        "uncited_reasons": sum(1 for r in summary["reasons"] if not any(refs_in(c) for c in r["citations"])),
        "single_citation_reasons": sum(1 for r in summary["reasons"]
                                       if len({ref for c in r["citations"] for ref in refs_in(c)}) == 1),
    }


# ---------- reporting ----------
def to_markdown(results):
    lines = ["# Why at-risk customers are drifting away", "",
             f"Model: `{MODEL}` · retrieval: `{RETRIEVAL_METHOD}`. Reviews are Yelp reviews of other grocery "
             "stores (a proxy voice), linked by category and theme, never by customer.", ""]
    for r in results:
        ev = {e["ref"]: e for e in r["evidence"]}
        lines += [f"## {r['segment']}", "", f"**{r['summary']['headline']}**", ""]
        for reason in r["summary"]["reasons"]:
            refs = ", ".join(reason["citations"])
            lines.append(f"- **{reason['reason'].rstrip('.')}.** {reason['explanation']} ({refs})")
            for ref in [x for c in reason["citations"] for x in refs_in(c)]:
                e = ev.get(ref)
                if e:
                    lines.append(f"  - {ref} ({stars(e) or '?'}★, review `{e['id']}`): "
                                 f"\"{e['text'][:MAX_REVIEW_CHARS].strip()}...\"")
                else:
                    lines.append(f"  - {ref}: ⚠ not in the retrieved evidence (invalid citation)")
        c = r["checks"]
        lines += ["", f"*Evidence gaps:* {r['summary']['evidence_gaps']}", "",
                  f"*Checks:* {c['n_reasons']} reasons, {c['n_citations']} citations, "
                  f"citation validity {c['citation_validity']:.0%}, uncited reasons {c['uncited_reasons']}, "
                  f"single-citation reasons {c.get('single_citation_reasons', 0)}", ""]
    return "\n".join(lines)


def merge_results(path, results):
    """Replace the rerun segments in an existing output file and keep the others (so --segment never drops them)."""
    if not path.exists():
        return results
    new = {r["segment"]: r for r in results}
    old = json.loads(path.read_text(encoding="utf-8"))
    merged = [new.pop(r["segment"], r) for r in old]
    return merged + list(new.values())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show evidence only, no Gemini call")
    ap.add_argument("--segment", default="", help="only segments whose name contains this text")
    ap.add_argument("--fresh", action="store_true", help="ask Gemini again instead of reusing a cached answer")
    args = ap.parse_args(argv)

    segments = [s for s in load_segments() if args.segment.lower() in seg_name(s).lower()]
    if not segments:
        print(f"No segments found in {SEGMENTS_PATH}.")
        return
    print(f"Retrieval: {RETRIEVAL_METHOD} | generation model: {MODEL}")

    results = []
    for s in segments:
        name = seg_name(s)
        cats = lapsed_categories(s)
        print(f"\n=== {name} | theme: {theme(s)} | lapsed: {cats or 'NONE FOUND'}")
        if not cats:
            print(f"  ⚠ No lapsed categories found. Keys in this segment: {list(s.keys())}")
        evidence = gather_evidence(s)
        print(f"  {len(evidence)} reviews retrieved")

        if args.dry_run:
            for e in evidence:
                print(f"  [{e['ref']}] {stars(e) or '?'}★ | {e['query']} | {score_label(e)} | "
                      f"{e['text'][:110].strip()}...")
            continue

        start = time.time()
        summary, cached = gemini_json(build_prompt(s, evidence), WhySummary, model=MODEL, temperature=0.2,
                                      refresh=args.fresh)
        checks = check_citations(summary, evidence)
        took = "(cached)" if cached else f"Gemini {time.time() - start:.1f}s"
        print(f"  {took} | {checks['n_reasons']} reasons | "
              f"citation validity {checks['citation_validity']:.0%} | uncited {checks['uncited_reasons']}")
        print(f"  → {summary['headline']}")
        meta = {"model": MODEL, "retrieval": RETRIEVAL_METHOD, "generated_at": datetime.now().isoformat(timespec="seconds"),
                "from_cache": cached, "seconds": round(time.time() - start, 1),
                "queries": [{"label": label, "query": q} for label, q, _ in evidence_queries(s)],
                "retrieved": len(evidence)}
        results.append({"segment": name, "theme": theme(s), "lapsed_categories": cats,
                        "retrieval": RETRIEVAL_METHOD, "summary": summary, "checks": checks,
                        "evidence": evidence, "meta": meta})

    if results:
        results = merge_results(OUT_JSON, results)
        OUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        OUT_MD.write_text(to_markdown(results), encoding="utf-8")
        print(f"\n✅ Saved {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    utf8_console()
    main()