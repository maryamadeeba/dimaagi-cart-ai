"""Embed the review knowledge base and load it into ChromaDB. Resumable.
Run from the project root:
    python -m src.rag.build_index --limit 2000     (quick test first)
    python -m src.rag.build_index                  (all 25,000)
"""
import argparse, time
from pathlib import Path

import chromadb
import numpy as np
import pandas as pd

from src.rag.llm import embed_texts
from src.console import utf8_console


def main(reviews_path, cache_dir, db_path, batch, sleep, limit):
    rv = pd.read_parquet(reviews_path).sort_values("review_id").reset_index(drop=True)
    if limit:
        rv = rv.iloc[:limit]
    texts = rv["text"].str.slice(0, 2000).tolist()   # stay well under the model's input limit

    # 1) Embed in batches, caching each batch to disk so the run can resume
    cache = Path(cache_dir); cache.mkdir(parents=True, exist_ok=True)
    n_batches = (len(texts) + batch - 1) // batch
    print(f"Embedding {len(texts):,} reviews in {n_batches} batches...")
    for b in range(n_batches):
        f = cache / f"batch_{b:05d}.npy"
        if f.exists():
            continue
        np.save(f, embed_texts(texts[b * batch:(b + 1) * batch]))
        print(f"  {b + 1}/{n_batches} batches done", flush=True)
        time.sleep(sleep)
    vecs = np.vstack([np.load(cache / f"batch_{b:05d}.npy") for b in range(n_batches)])

    # 2) Load into ChromaDB (rebuilt from scratch each run, using the cached embeddings)
    client = chromadb.PersistentClient(path=db_path)
    try:
        client.delete_collection("reviews")
    except Exception:
        pass
    col = client.create_collection("reviews")

    meta = pd.DataFrame({
        "stars": rv["stars"].astype(int),
        "sentiment": rv["sentiment"].astype(str),
        "product_tags": rv["product_tags"].fillna(""),
        "issue_tags": rv["issue_tags"].fillna(""),
        "store_name": rv["store_name"].fillna(""),
        "city": rv["city"].fillna(""),
        "state": rv["state"].fillna(""),
        "date": rv["date"].str.slice(0, 10),
        "year": rv["date"].str.slice(0, 4).astype(int),
        "useful": rv["useful"].astype(int),
    }).to_dict("records")

    for s in range(0, len(rv), 1000):
        col.add(ids=rv["review_id"].iloc[s:s + 1000].tolist(),
                embeddings=vecs[s:s + 1000].tolist(),
                documents=rv["text"].iloc[s:s + 1000].tolist(),
                metadatas=meta[s:s + 1000])
    print(f"Done: {col.count():,} reviews searchable in {db_path}")


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", default="data/processed/reviews.parquet")
    ap.add_argument("--cache", default="data/processed/emb_cache")
    ap.add_argument("--db", default="data/vectorstore")
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    main(a.reviews, a.cache, a.db, a.batch, a.sleep, a.limit)