"""Day 6 Part C: score every retrieval method against the labels, and check how reliable the judge is.

Run:  python -m eval.run_eval
"""
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from eval.build_labels import JUDGE_MODEL, LABELS, SPOTCHECK, Judgments, judge_prompt, load_queries
from src.rag.gemini import cached_result
from src.rag.hybrid import METHODS, load_bm25, search
from src.console import utf8_console

REPORT = Path("reports/retrieval_eval.md")     # numbers only (no review text), safe to commit
RESULTS = Path("eval/results.json")
K_HIT, K_MRR = 5, 10
STRONG_JUDGE = "gemini-3.8-flash"
TYPES = ["category", "issue", "theme", "hard"]
METRICS = [("hit5", "Hit@5"), ("mrr", "MRR@10"), ("p5", "P@5")]


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def kappa(a, b):
    """Percent agreement and Cohen's kappa for two lists of True/False labels."""
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, ((po - pe) / (1 - pe) if pe < 1 else 1.0)


def load_labels():
    return {l["qid"]: l for l in (json.loads(x) for x in LABELS.read_text(encoding="utf-8").splitlines() if x.strip())}


# ---------- retrieval scoring ----------
def score_methods(labels):
    search("warm up the models", "hybrid_rerank", 5)          # load models first so timings are fair
    per_query, latency = defaultdict(dict), defaultdict(list)
    scored = [q for q in labels.values() if q["relevant"]]
    for i, l in enumerate(scored, 1):
        rel = set(l["relevant"])
        for m in METHODS:
            start = time.time()
            ids = [h["id"] for h in search(l["query"], m, K_MRR)]
            latency[m].append(time.time() - start)
            top = ids[:K_HIT]
            first = next((r for r, d in enumerate(ids, 1) if d in rel), None)
            per_query[l["qid"]][m] = {
                "hit5": float(any(d in rel for d in top)),
                "mrr": 1.0 / first if first else 0.0,
                "p5": sum(d in rel for d in top) / K_HIT,
            }
        print(f"  scored {i}/{len(scored)}", end="\r", flush=True)
    print()
    return per_query, latency


def summarize(per_query, qids):
    return {m: {k: mean([per_query[q][m][k] for q in qids]) for k, _ in METRICS} for m in METHODS}


def head_to_head(per_query, base="vector"):
    out = {}
    for m in METHODS:
        if m == base:
            continue
        wins = ties = losses = 0
        for q in per_query:
            a, b = per_query[q][m]["mrr"], per_query[q][base]["mrr"]
            if abs(a - b) < 1e-9:
                ties += 1
            elif a > b:
                wins += 1
            else:
                losses += 1
        out[m] = (wins, ties, losses)
    return out


# ---------- judge reliability ----------
def human_agreement():
    if not SPOTCHECK.exists():
        return None
    with SPOTCHECK.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("human", "").strip().upper() in ("Y", "N")]
    if not rows:
        return None
    judge = [r["judge"].strip().upper() == "Y" for r in rows]
    human = [r["human"].strip().upper() == "Y" for r in rows]
    po, k = kappa(judge, human)
    disagreements = [(r["qid"], r["review_id"], r["judge"].strip().upper(), r["human"].strip().upper())
                     for r, j, h in zip(rows, judge, human) if j != h]
    return {"n": len(rows), "agreement": po, "kappa": k, "disagreements": disagreements}


def strong_judge_agreement(labels):
    """Compare the strong model's cached verdicts with the Lite labels on the queries both judged."""
    idx = load_bm25()
    text_by_id = dict(zip(idx["ids"], idx["docs"]))
    strong_labels, lite_labels, n_queries = [], [], 0
    for q in load_queries():
        lab = labels.get(q["qid"])
        if not lab:
            continue
        refs = {f"D{n}": (d, text_by_id[d]) for n, d in enumerate(lab["judged"], 1)}
        strong = cached_result(judge_prompt(q, refs), Judgments, STRONG_JUDGE)
        if not strong:
            continue
        n_queries += 1
        verdict = {j["ref"].strip(" []"): j["relevant"] for j in strong["judgments"]}
        rel = set(lab["relevant"])
        for ref, (doc_id, _) in refs.items():
            if ref in verdict:
                strong_labels.append(verdict[ref])
                lite_labels.append(doc_id in rel)
    if not strong_labels:
        return None
    po, k = kappa(strong_labels, lite_labels)
    return {"queries": n_queries, "n": len(strong_labels), "agreement": po, "kappa": k,
            "strong_relevant_rate": mean(strong_labels), "lite_relevant_rate": mean(lite_labels)}


# ---------- report ----------
def to_markdown(labels, per_query, latency, overall, by_type, h2h, human, strong):
    skipped = [q for q in labels.values() if not q["relevant"]]
    best = {k: max(overall[m][k] for m in METHODS) for k, _ in METRICS}
    lines = ["# Retrieval evaluation (Day 6)", "",
             f"{len(per_query)} queries scored ({len(skipped)} skipped: no relevant review found). "
             f"Labels: top-{K_MRR} from each of {len(METHODS)} methods pooled, judged by `{JUDGE_MODEL}`. "
             "Every scored result has a real label.", "",
             "## Overall", "",
             "| Method | Hit@5 | MRR@10 | P@5 | ms/query |", "|---|---|---|---|---|"]
    for m in METHODS:
        cells = []
        for k, _ in METRICS:
            v = f"{overall[m][k]:.3f}"
            cells.append(f"**{v}**" if abs(overall[m][k] - best[k]) < 1e-9 else v)
        lines.append(f"| {m} | {' | '.join(cells)} | {mean(latency[m]) * 1000:.0f} |")

    lines += ["", "## By query type (MRR@10)", "",
              "| Type (n) | " + " | ".join(METHODS) + " |", "|---|" + "---|" * len(METHODS)]
    for t, qids in by_type.items():
        if qids:
            s = summarize(per_query, qids)
            lines.append(f"| {t} ({len(qids)}) | " + " | ".join(f"{s[m]['mrr']:.3f}" for m in METHODS) + " |")

    lines += ["", "## Head-to-head vs vector (MRR per query)", "",
              "| Method | Wins | Ties | Losses |", "|---|---|---|---|"]
    for m, (w, t, l) in h2h.items():
        lines.append(f"| {m} | {w} | {t} | {l} |")

    lines += ["", "## Judge reliability", ""]
    if human:
        lines.append(f"- **Human spot-check:** agreed on {round(human['agreement'] * human['n'])}/{human['n']} labels "
                     f"({human['agreement']:.0%}), Cohen's kappa {human['kappa']:.2f}.")
        for qid, rid, j, h in human["disagreements"]:
            lines.append(f"  - {qid} · review `{rid}`: judge {j}, human {h}")
    else:
        lines.append("- Human spot-check: not filled in yet.")
    if strong:
        lines.append(f"- **Strong vs Lite judge:** {strong['n']} labels on {strong['queries']} queries, "
                     f"agreement {strong['agreement']:.0%}, kappa {strong['kappa']:.2f}. Relevant rate: "
                     f"strong {strong['strong_relevant_rate']:.0%} vs Lite {strong['lite_relevant_rate']:.0%}.")
    return "\n".join(lines) + "\n"


def main():
    labels = load_labels()
    print(f"Scoring {len(METHODS)} methods on {sum(1 for l in labels.values() if l['relevant'])} queries...")
    per_query, latency = score_methods(labels)
    overall = summarize(per_query, list(per_query))
    by_type = {t: [q for q in per_query if labels[q]["type"] == t] for t in TYPES}
    h2h = head_to_head(per_query)
    human = human_agreement()
    strong = strong_judge_agreement(labels) if JUDGE_MODEL != STRONG_JUDGE else None

    md = to_markdown(labels, per_query, latency, overall, by_type, h2h, human, strong)
    REPORT.write_text(md, encoding="utf-8")
    RESULTS.write_text(json.dumps({"overall": overall, "per_query": per_query, "human": human,
                                   "strong_judge": strong}, indent=2), encoding="utf-8")
    print("\n" + md)
    print(f"✅ Saved {REPORT} and {RESULTS}")


if __name__ == "__main__":
    utf8_console()
    main()