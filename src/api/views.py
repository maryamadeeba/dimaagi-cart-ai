"""Read the saved outputs of the active store and shape them for the app's screens.
Store paths below are repointed by src.api.stores when the owner switches store."""
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from src.api import stores
from src.explain import features_used, phrase

SEGMENTS = Path("models/segments.json")
METRICS = Path("models/metrics.json")
WHY = Path("models/why_summaries.json")
KITS = Path("models/campaign_kits.json")
PROFILE = Path("config/store_profile.yaml")
DRIVERS = Path("models/drivers.json")
SCORED = Path("models/scored_customers.csv")
FEATURES = Path("models/feature_columns.json")
STORE_META = Path("store.json")
CHROMA_DB = Path("data/vectorstore/chroma.sqlite3")      # shared by every store
SNIPPET_CHARS = 300
SHORT_QUOTE = 160
MIN_SEGMENT = 10

MISSING_HINTS = {
    "segments": "No customer segments yet. Import your sales data to score your customers.",
    "metrics": "No model yet. Import your sales data to score your customers.",
    "import": "That upload has expired. Upload the file again.",
    "customer": "No customer with that ID in this store.",
    "customers": "No scored customers yet. Import your sales data, or retrain, to see each customer's risk.",
    "why": "The reasons haven't been written yet. Build the reviews knowledge base and add a Gemini key, then press Regenerate.",
    "kits": "The campaign kits haven't been written yet. Build both knowledge bases and add a Gemini key, then press Regenerate.",
}
LIMITATIONS = [
    "The pre-trained model learned from one US grocery chain's loyalty-card data (dunnhumby, 2017). "
    "Other stores, places and years may behave differently.",
    "It predicts silent churn: a regular's weekly spend dropping by half or more over the next 61 days. "
    "It doesn't see why; the reasons screen adds that.",
    "Only regular customers (5+ trips) are scored. One-off shoppers are left out.",
    "Risk scores rank customers; they are not exact probabilities for your store.",
    "Findings are associations, not causes: coupon users stay more, but coupons may not be the reason.",
]


class Missing(Exception):
    """A saved output or knowledge base isn't there yet: the UI shows a setup prompt."""
    def __init__(self, what):
        super().__init__(MISSING_HINTS.get(what, f"{what} not found"))
        self.what = what


class UnknownSegment(Exception):
    def __init__(self, slug, available):
        super().__init__(f"No segment '{slug}'.")
        self.slug, self.available = slug, available


def _gen():
    return stores.mod("src.rag.generate")


def _asst():
    return stores.mod("src.rag.assistant")


def _read_json(path, what):
    if not path.exists():
        raise Missing(what)
    return json.loads(path.read_text(encoding="utf-8"))


def store_meta():
    return stores.read_meta() or {}


# ---------- health ----------
def kb_status():
    """Which Chroma collections exist, read straight from Chroma's SQLite file (fast, no chromadb import)."""
    if not CHROMA_DB.exists():
        return {"reviews": False, "trends": False}
    try:
        con = sqlite3.connect(f"file:{CHROMA_DB.resolve().as_posix()}?mode=ro", uri=True)
        try:
            names = {r[0] for r in con.execute("SELECT name FROM collections")}
        finally:
            con.close()
    except sqlite3.Error:
        names = set()
    return {"reviews": "reviews" in names, "trends": "trends" in names}


def outputs_status():
    return {"segments": SEGMENTS.exists(), "why": WHY.exists(), "kits": KITS.exists(), "customers": SCORED.exists()}


# ---------- segments ----------
def _segments():
    if not SEGMENTS.exists():
        raise Missing("segments")
    return _gen().load_segments()


def slug_of(s):
    return _asst()._slug(s)


def _find(slug):
    segs = _segments()
    s = next((s for s in segs if slug_of(s) == slug), None)
    if s is None:
        raise UnknownSegment(slug, [slug_of(x) for x in segs])
    return s


def main_reason(s):
    mix = s.get("reason_mix") or {}
    return max(mix, key=mix.get).lower() if mix else ""


def display_categories(s):
    g = _gen()
    return [g.category_terms(c) for c in g.lapsed_categories(s)]


def segment_card(s, total_customers):
    n = _asst()._segment_numbers(s)
    return {"slug": slug_of(s), "name": _gen().seg_name(s), "tier": s.get("tier", ""),
            "customers": s["customers"], "customer_share": round(s["customers"] / total_customers, 3),
            "main_reason": main_reason(s), "reason_mix": s.get("reason_mix", {}),
            "median_spend_per_week": s.get("median_spend_per_week"),
            "weekly_revenue_at_risk": s["weekly_revenue_at_risk"],
            "share_of_revenue_at_risk": n["share_of_revenue_at_risk"],
            "revenue_at_risk_per_customer": n["revenue_at_risk_per_customer"],
            "lapsed_categories": display_categories(s), "too_small": s["customers"] < MIN_SEGMENT}


def store_profile():
    return yaml.safe_load(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else {}


def model_metrics():
    if not METRICS.exists():
        return None
    m = json.loads(METRICS.read_text(encoding="utf-8"))
    return {"roc_auc": m.get("test_roc_auc"), "pr_auc": m.get("test_pr_auc"),
            "recency_rule_roc_auc": m.get("baseline_rule_roc_auc"), "n_features": m.get("n_features"),
            "trained_at": m.get("trained_at"), "cutoffs": m.get("cutoffs", []),
            "capture": m.get("capture"), "source": m.get("source", "store"),
            "comparison": m.get("comparison")}


def _kit_for(name):
    if not KITS.exists():
        return None
    return next((k for k in json.loads(KITS.read_text(encoding="utf-8")) if k["segment"] == name), None)


def dashboard():
    data = _read_json(SEGMENTS, "segments")
    segs = _segments()
    total_customers = sum(s["customers"] for s in segs)
    cards = [segment_card(s, total_customers) for s in segs]
    # Share of at-risk customers by main reason: each segment's reason mix weighted by its size
    split = {}
    for s in segs:
        for reason, share in (s.get("reason_mix") or {}).items():
            split[reason.lower()] = split.get(reason.lower(), 0) + share * s["customers"]
    focus = max(cards, key=lambda c: c["revenue_at_risk_per_customer"]) if cards else None
    why_focus = None
    if focus:
        kit = _kit_for(focus["name"])
        why_focus = {"per_customer": focus["revenue_at_risk_per_customer"],
                     "others": [c["revenue_at_risk_per_customer"] for c in sorted(cards, key=lambda c: -c["revenue_at_risk_per_customer"])
                                if c["slug"] != focus["slug"]],
                     "perk": kit["kit"]["offer"]["non_monetary_perk"] if kit else None}
    meta = store_meta()
    return {
        "as_of": data.get("as_of") if isinstance(data, dict) else None,
        "store_name": store_profile().get("store_name", "[STORE NAME]"),
        "store": {"slug": stores.active(), "name": meta.get("name"), "demo": meta.get("demo", False),
                  "scored_with": meta.get("scored_with", "store")},
        "totals": {"customers": total_customers,
                   "weekly_revenue_at_risk": round(sum(s["weekly_revenue_at_risk"] for s in segs), 2),
                   "segments": len(segs)},
        "segments": cards,
        "focus": focus["slug"] if focus else None,
        "focus_why": why_focus,
        "model": model_metrics(),
        "reason_split": {k: round(v / total_customers, 3) for k, v in split.items()} if total_customers else {},
        "small_segments": [c["name"] for c in cards if c["too_small"]],
    }


# ---------- why they leave ----------
def _cap(sentence, limit=SHORT_QUOTE):
    """At most ~160 characters, cut at a word."""
    if len(sentence) <= limit:
        return sentence
    return sentence[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def short_quote(text, limit=SHORT_QUOTE):
    """The first sentence, at most ~160 characters, cut at a word."""
    text = " ".join(str(text).split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return _cap(m.group(1) if m else text, limit)


def _words(text):
    """Content words, lightly stemmed so 'shelves'/'shelf' and 'expired'/'expire' meet halfway (stop words dropped)."""
    from src.rag.hybrid import tokenize
    return {t.rstrip("s").removesuffix("ed").removesuffix("ing") if len(t) > 4 else t for t in tokenize(text)}


def best_quote(text, context, limit=SHORT_QUOTE):
    """The review sentence sharing the most content words with `context` (the reason it backs and the search that
    found it); ties go to the earliest sentence, and no overlap at all falls back to the first sentence."""
    text = " ".join(str(text).split())
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()] or [text]
    want = _words(context)
    scores = [len(_words(x) & want) for x in sentences]
    best = max(range(len(sentences)), key=lambda i: (scores[i], -i))
    return _cap(sentences[best], limit)


def _topic(e):
    """'category: fluid milk products' -> 'milk'; 'theme: visiting less' -> 'visiting less'."""
    kind, _, value = str(e.get("query", "")).partition(": ")
    return _gen().category_terms(value) if kind == "category" else value


def _stale(meta):
    """True when the text was written before this store's latest import (its numbers may be out of date)."""
    scored_at = store_meta().get("scored_at")
    return bool(meta and scored_at and meta.get("generated_at", "") < scored_at)


def reasons(slug):
    g = _gen()
    s = _find(slug)
    why = next((w for w in _read_json(WHY, "why") if w["segment"] == g.seg_name(s)), None)
    if why is None:
        raise Missing("why")
    ev = {e["ref"]: e for e in why["evidence"]}
    # Renumber cited reviews R1, R2... in reading order (original_ref points into models/why_summaries.md)
    renum, out_reasons, context = {}, [], {}
    queries = {q["label"]: q["query"] for q in (why.get("meta") or {}).get("queries", [])}
    for i, r in enumerate(why["summary"]["reasons"], 1):
        refs = []
        for old in [x for c in r["citations"] for x in g.refs_in(c)]:
            if old in ev:
                context[old] = f"{context.get(old, '')} {r['reason']} {r['explanation']}"
                renum.setdefault(old, f"R{len(renum) + 1}")
                if renum[old] not in refs:
                    refs.append(renum[old])
        out_reasons.append({"n": i, "title": r["reason"].rstrip("."), "text": r["explanation"], "refs": refs})
    reviews = []
    for old, new in renum.items():
        text = ev[old]["text"][:SNIPPET_CHARS].strip()
        label = ev[old].get("query", "")
        search = queries.get(label) or label.partition(": ")[2]          # the full query if it was recorded
        reviews.append({"ref": new, "original_ref": old, "id": ev[old]["id"], "stars": g.stars(ev[old]),
                        "text": text, "short": best_quote(text, f"{context.get(old, '')} {search}"),
                        "truncated": len(ev[old]["text"]) > SNIPPET_CHARS, "topic": _topic(ev[old])})
    card = segment_card(s, sum(x["customers"] for x in _segments()))
    meta = why.get("meta")
    checks = why.get("checks", {})
    how = {"recorded": meta is not None, "model": (meta or {}).get("model"),
           "retrieval": (meta or {}).get("retrieval") or why.get("retrieval"),
           "theme": why.get("theme"), "queries": (meta or {}).get("queries", []),
           "retrieved": (meta or {}).get("retrieved", len(why["evidence"])),
           "retrieved_refs": [e["ref"] for e in why["evidence"]], "cited": len(renum),
           "generated_at": (meta or {}).get("generated_at"), "from_cache": (meta or {}).get("from_cache"),
           "checks": [{"name": "Citations point to retrieved reviews", "ok": checks.get("citation_validity") == 1.0,
                       "detail": f"{checks.get('n_citations', 0)} citations, validity {checks.get('citation_validity', 0):.0%}"},
                      {"name": "Every reason is cited", "ok": checks.get("uncited_reasons", 1) == 0,
                       "detail": f"{checks.get('uncited_reasons', 0)} uncited"}],
           "stale": _stale(meta)}
    return {**card, "headline": why["summary"]["headline"], "reasons": out_reasons, "reviews": reviews,
            "gaps": why["summary"]["evidence_gaps"], "checks": checks, "how": how}


# ---------- win them back ----------
def kit(slug):
    from src.rag.campaign import trend_label
    g = _gen()
    s = _find(slug)
    k = _kit_for(g.seg_name(s)) if KITS.exists() else None
    if not KITS.exists() or k is None:
        raise Missing("kits")
    card = segment_card(s, sum(x["customers"] for x in _segments()))
    labels = list(dict.fromkeys(trend_label(t) for t in k.get("trends", [])))
    c, meta = k["checks"], k.get("meta")
    how = {"recorded": meta is not None, "model": (meta or {}).get("model"),
           "retrieval": (meta or {}).get("retrieval", "vector (trend reports)"),
           "queries": (meta or {}).get("queries", []), "retrieved": len(k.get("trends", [])),
           "retrieved_refs": [{"ref": t["ref"], "label": trend_label(t)} for t in k.get("trends", [])],
           "reviews_used": len(k.get("reviews", [])),
           "generated_at": (meta or {}).get("generated_at"), "from_cache": (meta or {}).get("from_cache"),
           "checks": [
               {"name": "Citations valid", "ok": c["citation_validity"] == 1.0,
                "detail": f"{c['citations']} citations, validity {c['citation_validity']:.0%}"},
               {"name": "Numbers grounded in the sources", "ok": not c["unsupported_numbers"],
                "detail": ", ".join(c["unsupported_numbers"]) or "every number found in a source"},
               {"name": "SMS length", "ok": c["sms_ok"], "detail": f"{c['sms_send_chars']} / 160 characters when sent"},
               {"name": "Email subject length", "ok": c["subject_ok"], "detail": f"{c['subject_chars']} / 60 characters"},
               {"name": "Offer economics", "ok": c["offer"]["economics_ok"],
                "detail": f"discount {c['offer']['discount_rate']:.0%} of a basket "
                          f"{'above' if c['offer']['threshold_above_median'] else 'not above'} median spend"},
               {"name": "Promises tagged [CONFIRM]", "ok": not c["unflagged_claims"],
                "detail": f"{len(c['unflagged_claims'])} untagged"}],
           "stale": _stale(meta)}
    return {**card, "kit": k["kit"], "checks": c, "how": how,
            "sources": {"reviews": len(k.get("reviews", [])), "trends": labels,
                        "refs": {t["ref"]: trend_label(t) for t in k.get("trends", [])}}}


# ---------- customers ----------
@lru_cache(maxsize=4)
def _customers_table(path, mtime, drivers_mtime):
    df = pd.read_csv(path, dtype={"household_id": str})
    drivers = json.loads(DRIVERS.read_text(encoding="utf-8")) if DRIVERS.exists() else {}
    for ds in drivers.values():                       # phrase from the stored value, so wording fixes apply
        for d in ds:
            if "value" in d:
                d["phrase"] = phrase(d["feature"], d["value"])
    slugs = {}
    if SEGMENTS.exists():
        slugs = {_gen().seg_name(s): slug_of(s) for s in _segments()}
    df["customer_id"] = df["household_id"].astype(str)
    df["revenue_at_risk"] = df["spend_per_week"].where(df["at_risk"], 0.0)
    df["segment_slug"] = df["segment"].map(slugs)
    df["top_reason"] = [next((d["phrase"] for d in drivers.get(h, []) if d["shap"] > 0), "")
                        for h in df["customer_id"]]
    return df, drivers


def _customers():
    if not SCORED.exists():
        raise Missing("customers")
    return _customers_table(str(SCORED.resolve()), SCORED.stat().st_mtime,
                            DRIVERS.stat().st_mtime if DRIVERS.exists() else 0)


SORTS = {"risk": "risk", "spend": "spend_per_week", "revenue": "revenue_at_risk", "id": "customer_id",
         "segment": "segment"}


def customers(q="", sort="risk", desc=True, page=1, page_size=50, segment="", at_risk_only=False):
    df, _ = _customers()
    view = df
    if q:
        ql = q.strip().lower()
        view = view[view["customer_id"].str.lower().str.contains(ql, regex=False)
                    | view["top_reason"].str.lower().str.contains(ql, regex=False)]
    if segment:
        view = view[view["segment_slug"] == segment]
    if at_risk_only:
        view = view[view["at_risk"]]
    view = view.sort_values(SORTS.get(sort, "risk"), ascending=not desc, kind="stable")
    page_size = max(1, min(int(page_size), 200))
    pages = max(1, -(-len(view) // page_size))
    page = max(1, min(int(page), pages))
    rows = view.iloc[(page - 1) * page_size: page * page_size]
    return {"total": int(len(view)), "all": int(len(df)), "at_risk": int(df["at_risk"].sum()),
            "page": page, "pages": pages, "page_size": page_size,
            "rows": [{"id": r.customer_id, "risk": round(float(r.risk), 3), "segment": r.segment,
                      "segment_slug": r.segment_slug if isinstance(r.segment_slug, str) else None,
                      "at_risk": bool(r.at_risk), "spend_per_week": round(float(r.spend_per_week), 2),
                      "revenue_at_risk": round(float(r.revenue_at_risk), 2), "top_reason": r.top_reason}
                     for r in rows.itertuples()]}


def customer(customer_id):
    df, drivers = _customers()
    hit = df[df["customer_id"] == str(customer_id)]
    if hit.empty:
        raise Missing("customer")
    r = hit.iloc[0]
    return {"id": r.customer_id, "risk": round(float(r.risk), 3), "segment": r.segment,
            "segment_slug": r.segment_slug if isinstance(r.segment_slug, str) else None,
            "at_risk": bool(r.at_risk), "spend_per_week": round(float(r.spend_per_week), 2),
            "trips_per_week": round(float(r.trips_per_week), 2), "recency_days": int(r.recency_days),
            "revenue_at_risk": round(float(r.revenue_at_risk), 2), "drivers": drivers.get(r.customer_id, [])}


# ---------- model card ----------
def pretrained_models():
    """The two shipped models' scores on the demo data's newest period (the same test for both)."""
    out = {}
    for key, name, label in (("full", "metrics.json", "Full model (30 signals, with marketing)"),
                             ("behaviour", f"metrics{stores.PRETRAINED}.json",
                              "Behaviour-only model (25 signals, used for imported stores)")):
        path = stores.root(stores.DEMO) / "models" / name
        if path.exists():
            m = json.loads(path.read_text(encoding="utf-8"))
            out[key] = {"label": label, "roc_auc": m.get("test_roc_auc"), "pr_auc": m.get("test_pr_auc"),
                        "n_features": m.get("n_features"), "capture": (m.get("capture") or {}).get("model"),
                        "recency_rule_roc_auc": m.get("baseline_rule_roc_auc"),
                        "test_customers": m.get("test_customers"), "cutoffs": m.get("cutoffs", [])}
    return out


def model_card():
    m = _read_json(METRICS, "metrics")
    meta = store_meta()
    columns = json.loads(FEATURES.read_text()) if FEATURES.exists() else []
    trained_on = ({"from": m.get("data_from"), "to": m.get("data_to"), "households": m.get("households")}
                  if m.get("data_from") else None)
    return {
        "source": m.get("source", "store"),
        "store": {"name": meta.get("name"), "demo": meta.get("demo", False)},
        "trained_on": trained_on, "store_data": m.get("store_data"),
        "validation": "Trained on the past, tested on the future: the model learns from older snapshots and is "
                      "scored on the newest period it has never seen.",
        "cutoffs": m.get("cutoffs", []), "test_customers": m.get("test_customers"),
        "trained_at": m.get("trained_at"), "roc_auc": m.get("test_roc_auc"), "pr_auc": m.get("test_pr_auc"),
        "recency_rule_roc_auc": m.get("baseline_rule_roc_auc"), "at_risk_rate": m.get("test_at_risk_rate"),
        "capture": m.get("capture"), "comparison": m.get("comparison"),
        "features": features_used(columns, meta.get("marketing_available", True)),
        "n_features": len(columns) or m.get("n_features"),
        "marketing_available": meta.get("marketing_available", True),
        "behaviour_only": m.get("marketing_features") is False,
        "pretrained_models": pretrained_models(),
        "limitations": LIMITATIONS,
    }
