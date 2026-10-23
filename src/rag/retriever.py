"""Search the ChromaDB knowledge bases (reviews + trends)."""
import argparse
import chromadb
from src.rag.llm import embed_texts
from src.console import utf8_console

DB_PATH = "data/vectorstore"
_collections = {}


def get_collection(name):
    if name not in _collections:
        client = chromadb.PersistentClient(path=DB_PATH)
        _collections[name] = client.get_collection(name)
    return _collections[name]


def search(query, collection="reviews", k=5, where=None, max_per_source=None):
    """Vector search. If max_per_source is set, no single source fills more than that many slots."""
    q = embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
    n = k * 6 if max_per_source else k          # fetch extra so we can skip repeats
    res = get_collection(collection).query(
        query_embeddings=[q.tolist()], n_results=n, where=where
    )
    hits = [
        {"id": i, "text": d, "distance": round(dist, 3), **(m or {})}
        for i, d, dist, m in zip(res["ids"][0], res["documents"][0],
                                 res["distances"][0], res["metadatas"][0])
    ]
    if not max_per_source:
        return hits[:k]

    picked, per_source = [], {}
    for h in hits:
        src = h.get("source", h["id"])
        if per_source.get(src, 0) < max_per_source:
            picked.append(h)
            per_source[src] = per_source.get(src, 0) + 1
        if len(picked) == k:
            break
    return picked


def search_reviews(query, k=5, where=None):
    return search(query, "reviews", k, where)


def search_trends(query, k=5, where=None, max_per_source=2):
    return search(query, "trends", k, where, max_per_source)


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--trends", action="store_true", help="search trend reports instead of reviews")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    hits = search_trends(args.query, k=args.k) if args.trends else search_reviews(args.query, k=args.k)

    for n, h in enumerate(hits, 1):
        if args.trends:
            label = f"{h.get('source')} | p.{h.get('page')}"
        else:
            label = f"{h.get('rating')}★"
        print(f"\n[{n}] {label} | dist {h['distance']}")
        print(h["text"][:300].replace("\n", " "), "...")