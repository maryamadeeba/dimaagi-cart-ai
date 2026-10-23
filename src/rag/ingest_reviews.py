"""Build the grocery review knowledge base from the Yelp Open Dataset.
Run from the project root:  python -m src.rag.ingest_reviews
"""
import argparse, json, re
from pathlib import Path

import pandas as pd
import yaml
from src.console import utf8_console


def load_config(path="config/niche.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def find_stores(business_path, category):
    """All businesses whose Yelp categories include `category` exactly."""
    stores = {}
    with open(business_path, encoding="utf-8") as f:
        for line in f:
            b = json.loads(line)
            cats = [c.strip() for c in (b.get("categories") or "").split(",")]
            if category in cats:
                stores[b["business_id"]] = {"store_name": b["name"], "city": b["city"],
                                            "state": b["state"], "store_stars": b["stars"]}
    return stores


def collect_reviews(review_path, stores):
    """Stream the (very large) review file line by line, keeping only grocery stores."""
    rows = []
    with open(review_path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            r = json.loads(line)
            if r["business_id"] in stores:
                rows.append({"review_id": r["review_id"], "business_id": r["business_id"],
                             "stars": r["stars"], "useful": r["useful"],
                             "date": r["date"], "text": r["text"]})
            if i % 1_000_000 == 0:
                print(f"  scanned {i:,} reviews, kept {len(rows):,}")
    return pd.DataFrame(rows)


def compile_tags(tag_words):
    return {tag: re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
            for tag, words in tag_words.items()}


def tag_text(text, patterns):
    return "|".join(t for t, p in patterns.items() if p.search(text))


def main(yelp_dir, out_path, config_path):
    cfg = load_config(config_path)
    d = Path(yelp_dir)

    print("1/4 Finding grocery stores...")
    stores = find_stores(d / "yelp_academic_dataset_business.json", cfg["yelp_category"])
    print(f"    {len(stores):,} grocery stores")

    print("2/4 Collecting their reviews (takes a few minutes)...")
    df = collect_reviews(d / "yelp_academic_dataset_review.json", stores)
    print(f"    {len(df):,} grocery reviews found")

    print("3/4 Cleaning and sampling...")
    df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["text"].str.split().str.len() >= cfg["min_words"]].drop_duplicates("text")
    df["sentiment"] = pd.cut(df["stars"], bins=[0, 2, 3, 5], labels=["negative", "neutral", "positive"])
    parts = [g.sample(n=min(len(g), cfg["sample"][s]), random_state=42)
             for s, g in df.groupby("sentiment", observed=True)]
    df = pd.concat(parts, ignore_index=True)

    print("4/4 Tagging products and issues...")
    prod_p, issue_p = compile_tags(cfg["product_tags"]), compile_tags(cfg["issue_tags"])
    df["product_tags"] = df["text"].apply(lambda t: tag_text(t, prod_p))
    df["issue_tags"] = df["text"].apply(lambda t: tag_text(t, issue_p))
    df = df.merge(pd.DataFrame.from_dict(stores, orient="index"),
                  left_on="business_id", right_index=True, how="left")
    df["sentiment"] = df["sentiment"].astype(str)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    # --- Quick report ---
    neg = df[df["sentiment"] == "negative"]
    print(f"\nSaved {len(df):,} reviews to {out_path}")
    print(df["sentiment"].value_counts().to_string(), "\n")
    print(f"Date range: {df['date'].min()[:10]} to {df['date'].max()[:10]}  |  "
          f"Stores: {df['business_id'].nunique():,}  |  States: {df['state'].nunique()}")
    print("\nWhat negative reviews complain about (% of 1–2 star reviews):")
    for tag in cfg["issue_tags"]:
        print(f"  {tag:20s} {neg['issue_tags'].str.contains(tag).mean():.0%}")
    print("\nProducts mentioned in negative reviews:")
    for tag in cfg["product_tags"]:
        print(f"  {tag:20s} {neg['product_tags'].str.contains(tag).mean():.0%}")


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--yelp", default="data/raw/yelp")
    ap.add_argument("--out", default="data/processed/reviews.parquet")
    ap.add_argument("--config", default="config/niche.yaml")
    a = ap.parse_args()
    main(a.yelp, a.out, a.config)