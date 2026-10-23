"""Hybrid retrieval for reviews: vector + BM25 keyword search, fused with RRF,
plus an optional local cross-encoder reranker.

Run:
  python -m src.rag.hybrid "stale bread loaf from the bread aisle"          # compare all 4 methods
  python -m src.rag.hybrid "expired milk" --method hybrid_rerank -k 5        # one method
"""
import argparse
import os
import pickle
import re
import time
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from src.rag.retriever import get_collection, search as _vector_search
from src.console import utf8_console

BM25_CACHE = Path("data/processed/bm25_reviews.pkl")
RRF_K = 60            # standard RRF constant: dampens the gap between rank 1 and rank 2
CANDIDATES = 30       # how many results each method contributes before fusing / reranking
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
RERANK_CHARS = 1000   # reviews are truncated to this length for the reranker
METHODS = ["vector", "bm25", "hybrid", "hybrid_rerank"]

STOPWORDS = set("""a an the and or but if of to in on at for with from by is are was were be been
it this that these those i me my we our you your they them their he she his her its as so do does
did have has had just very really can will would could should there here what when which who all
any some more most than too about into over again then once only own same also get got""".split())


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS and len(t) > 1]


# ---------- BM25 (built once, cached to disk) ----------
_bm25 = None


def load_bm25():
    global _bm25
    if _bm25 is not None:
        return _bm25
    col = get_collection("reviews")
    n = col.count()
    if BM25_CACHE.exists():
        data = pickle.loads(BM25_CACHE.read_bytes())
        if data["n"] == n:                     # rebuild automatically if the index changed
            _bm25 = data
            return _bm25

    print(f"Building BM25 index over {n} reviews (one-time, ~1 min)...", flush=True)
    ids, docs, metas = [], [], []
    for offset in range(0, n, 5000):           # page through Chroma in batches
        got = col.get(include=["documents", "metadatas"], limit=5000, offset=offset)
        ids += got["ids"]
        docs += got["documents"]
        metas += [m or {} for m in got["metadatas"]]
    bm25 = BM25Okapi([tokenize(d) for d in docs])
    _bm25 = {"n": n, "ids": ids, "docs": docs, "metas": metas, "bm25": bm25}
    BM25_CACHE.parent.mkdir(parents=True, exist_ok=True)
    BM25_CACHE.write_bytes(pickle.dumps(_bm25))
    return _bm25


def bm25_search(query, k=CANDIDATES):
    idx = load_bm25()
    scores = idx["bm25"].get_scores(tokenize(query))
    top = np.argsort(scores)[::-1][:k]
    return [{"id": idx["ids"][i], "text": idx["docs"][i], "bm25": round(float(scores[i]), 3), **idx["metas"][i]}
            for i in top if scores[i] > 0]


def vector_search(query, k=CANDIDATES):
    return _vector_search(query, "reviews", k)


# ---------- fusion ----------
def hybrid_search(query, k=CANDIDATES):
    fused = {}
    for hits in (vector_search(query, CANDIDATES), bm25_search(query, CANDIDATES)):
        for rank, h in enumerate(hits, start=1):
            entry = fused.setdefault(h["id"], {**h, "rrf": 0.0})
            entry.update({key: v for key, v in h.items() if key not in entry})
            entry["rrf"] += 1.0 / (RRF_K + rank)
    ranked = sorted(fused.values(), key=lambda h: -h["rrf"])
    for h in ranked:
        h["rrf"] = round(h["rrf"], 4)
    return ranked[:k]


# ---------- reranking (local cross-encoder) ----------
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        print(f"Loading reranker {RERANK_MODEL} (first time downloads ~80 MB)...", flush=True)
        _reranker = TextCrossEncoder(model_name=RERANK_MODEL)
    return _reranker


def hybrid_rerank_search(query, k=5):
    candidates = hybrid_search(query, CANDIDATES)
    scores = list(get_reranker().rerank(query, [c["text"][:RERANK_CHARS] for c in candidates]))
    for c, s in zip(candidates, scores):
        c["rerank"] = round(float(s), 3)
    return sorted(candidates, key=lambda c: -c["rerank"])[:k]


# ---------- one entry point ----------
def search(query, method="hybrid_rerank", k=5):
    if method == "vector":
        return vector_search(query, k)
    if method == "bm25":
        return bm25_search(query, k)
    if method == "hybrid":
        return hybrid_search(query, k)
    if method == "hybrid_rerank":
        return hybrid_rerank_search(query, k)
    raise ValueError(f"Unknown method '{method}'. Choose from {METHODS}")


def _stars(h):
    return h.get("stars", h.get("rating", "?"))


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--method", default="all", choices=["all"] + METHODS)
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    for m in (METHODS if args.method == "all" else [args.method]):
        start = time.time()
        hits = search(args.query, m, args.k)
        print(f"\n===== {m}  ({time.time() - start:.2f}s)")
        for n, h in enumerate(hits, 1):
            print(f"[{n}] {_stars(h)}★ | {h['id'][:10]} | {h['text'][:110].strip()}...")