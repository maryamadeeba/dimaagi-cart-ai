"""Day 6 Part B: pool candidates from every retrieval method, then label relevance with a Gemini judge.

Run:  python -m eval.build_labels
"""
import csv
import json
import os
import random
import time
from pathlib import Path

from pydantic import BaseModel

from src.rag.gemini import gemini_json
from src.rag.hybrid import METHODS, search
from src.console import utf8_console

QUERIES = Path("eval/queries.jsonl")
LABELS = Path("eval/labels.jsonl")
SPOTCHECK = Path("eval/spotcheck.csv")     # contains review text, so it's gitignored
POOL_DEPTH = 10                            # top-10 from each method go into the pool
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
JUDGE_CHARS = 700
SPOT_QUERIES = 8                           # queries sampled for your hand check
SEED = 42


class Judgment(BaseModel):
    ref: str
    relevant: bool


class Judgments(BaseModel):
    judgments: list[Judgment]


def load_queries():
    return [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]


def pool(query):
    docs = {}
    for method in METHODS:
        for h in search(query, method, POOL_DEPTH):
            docs.setdefault(h["id"], h["text"])
    return docs


def judge_prompt(q, refs):
    note = f"\nWhat counts for this query: {q['note']}" if q.get("note") else ""
    lines = "\n".join(f'[{ref}] "{text[:JUDGE_CHARS].strip()}"' for ref, (_, text) in refs.items())
    return f"""You are labelling search results for a grocery-review search engine.

QUERY: "{q['query']}"{note}

A review is RELEVANT only if a shopper describes an experience that directly matches the query topic at a grocery store.
Passing mentions, or reviews mainly about something else, are NOT relevant.
For product queries, the review must be about buying that product as groceries, not a prepared sandwich or restaurant meal,
unless the query is about deli or prepared food.

REVIEWS:
{lines}

Return one judgment for every review ref (D1, D2, ...), with relevant true or false."""


def main():
    queries = load_queries()
    rng = random.Random(SEED)
    spot_qids = set(rng.sample([q["qid"] for q in queries], SPOT_QUERIES))
    print(f"Labelling {len(queries)} queries | judge: {JUDGE_MODEL} | pool depth {POOL_DEPTH} x {len(METHODS)} methods")

    labels, spot_rows, total_missing = [], [], 0
    for i, q in enumerate(queries, 1):
        docs = pool(q["query"])
        refs = {f"D{n}": (doc_id, text) for n, (doc_id, text) in enumerate(docs.items(), 1)}
        out, cached = gemini_json(judge_prompt(q, refs), Judgments, model=JUDGE_MODEL)
        verdict = {j["ref"].strip(" []"): j["relevant"] for j in out["judgments"]}
        missing = [r for r in refs if r not in verdict]          # unjudged = treated as not relevant
        total_missing += len(missing)
        relevant = [refs[r][0] for r in refs if verdict.get(r)]
        labels.append({"qid": q["qid"], "query": q["query"], "type": q["type"],
                       "judged": [doc_id for doc_id, _ in refs.values()], "relevant": relevant})
        print(f"[{i}/{len(queries)}] {q['qid']} | pool {len(refs)} | relevant {len(relevant)} | "
              f"{'cached' if cached else 'judged'}" + (f" | ⚠ {len(missing)} unjudged" if missing else ""), flush=True)

        if q["qid"] in spot_qids:
            rel = [r for r in refs if verdict.get(r)]
            non = [r for r in refs if r in verdict and not verdict[r]]
            for r in rng.sample(rel, min(3, len(rel))) + rng.sample(non, min(3, len(non))):
                spot_rows.append({"qid": q["qid"], "query": q["query"], "review_id": refs[r][0],
                                  "review_text": refs[r][1][:400].replace("\n", " "),
                                  "judge": "Y" if verdict[r] else "N", "human": ""})
        if not cached:
            time.sleep(4)                                        # stay under free-tier rate limits

    LABELS.write_text("\n".join(json.dumps(l) for l in labels) + "\n", encoding="utf-8")
    print(f"\n✅ Saved {LABELS} ({sum(len(l['relevant']) for l in labels)} relevant labels; {total_missing} unjudged)")

    if SPOTCHECK.exists():
        print(f"ℹ {SPOTCHECK} already exists, not overwritten (protects your hand labels).")
    else:
        with SPOTCHECK.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(spot_rows[0].keys()))
            writer.writeheader()
            writer.writerows(spot_rows)
        print(f"✅ Saved {SPOTCHECK} ({len(spot_rows)} rows): fill the 'human' column with Y or N")


if __name__ == "__main__":
    utf8_console()
    main()