"""Ingest curated trend-report PDFs into the ChromaDB 'trends' collection.

Run:  python -m src.rag.ingest_trends
"""
import re
from pathlib import Path

import chromadb
import pandas as pd
from pypdf import PdfReader

from src.rag.llm import embed_texts
from src.console import utf8_console

PDF_DIR = Path("data/knowledge/trends")
SOURCES_CSV = Path("config/trend_sources.csv")
DB_PATH = "data/vectorstore"
COLLECTION = "trends"

CHUNK_SIZE = 1500     # characters
OVERLAP = 200         # characters shared between neighbouring chunks
MIN_PAGE_CHARS = 200  # skip near-empty pages (covers, dividers)
EMBED_BATCH = 32

BOILERPLATE = [
    r"Click to edit Master title style",
    r"Spam Test Email Deliverability Platform.*?English",   # MailGenius site menu
    r"Get started Get a demo",                               # Klaviyo site menu
]
# On saved web pages, everything after these words is sidebars, forms and footers.
END_MARKERS = re.compile(r"Recent Posts|Related Articles|Subscribe to our newsletter", re.IGNORECASE)
# Pages that match report keywords but carry no content: tables of contents, credits, references
SKIP_PAGE = re.compile(
    r"^\W*(table of )?contents\b|\backnowledg(e)?ments?\b|\babout the (authors?|research)\b"
    r"|^\W*(references|endnotes|sources|methodology notes)\b",
    re.IGNORECASE,
)


def is_skip_page(text):
    """True for contents, acknowledgments and reference pages (checked near the top of the page)."""
    return bool(SKIP_PAGE.search(text[:300]))


def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    for pattern in BOILERPLATE:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\(?https?://\S+\)?", " ", text)          # drop raw links
    text = re.sub(r"(?:\b\w\b[\s\-]+){8,}", " ", text)       # runs of single letters
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size=CHUNK_SIZE, overlap=OVERLAP):
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):                      # try to end on a sentence or word
            cut = max(text.rfind(". ", start, end), text.rfind(" ", start, end))
            if cut > start + size // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def load_sources():
    """Return {pdf file name: metadata dict} from config/trend_sources.csv."""
    df = pd.read_csv(SOURCES_CSV)
    file_col = next((c for c in ["file", "filename", "file_name", "source"] if c in df.columns), df.columns[0])
    return {str(r[file_col]).strip(): r.to_dict() for _, r in df.iterrows()}


def main(pdf_dir=PDF_DIR):
    sources = load_sources()
    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {pdf_dir}")

    rows = []
    for pdf in pdfs:
        info = sources.get(pdf.name, {})
        if not info:
            print(f"  ⚠ {pdf.name} has no row in {SOURCES_CSV} (metadata will be blank)")
        reader = PdfReader(str(pdf))
        kept = 0
        done = False
        for p, page in enumerate(reader.pages, start=1):
            if done:
                break
            raw = page.extract_text() or ""
            cut = END_MARKERS.search(raw)
            if cut:
                raw, done = raw[:cut.start()], True
            text = clean_text(raw)
            if len(text) < MIN_PAGE_CHARS or is_skip_page(text):
                continue
            for j, chunk in enumerate(chunk_text(text)):
                rows.append({
                    "id": f"{pdf.stem}-p{p}-c{j}",
                    "text": chunk,
                    "source": pdf.name,
                    "title": str(info.get("title", pdf.stem)),
                    "publisher": str(info.get("publisher", "")),
                    "year": int(info.get("year", 0) or 0),
                    "url": "" if pd.isna(info.get("url")) else str(info.get("url", "")),
                    "page": p,
                })
                kept += 1
        note = "  ← no text found (scanned PDF?)" if kept == 0 else ""
        print(f"  {pdf.name}: {len(reader.pages)} pages → {kept} chunks{note}")

    if not rows:
        print("No chunks to index. Check that the PDFs are in the folder.")
        return

    print(f"\nEmbedding {len(rows)} chunks...")
    texts = [r["text"] for r in rows]
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        vectors.extend(embed_texts(texts[i:i + EMBED_BATCH], task_type="RETRIEVAL_DOCUMENT"))
        print(f"  {min(i + EMBED_BATCH, len(texts))}/{len(texts)}", flush=True)

    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        client.delete_collection(COLLECTION)     # rebuild from scratch each run
    except Exception:
        pass
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[r["id"] for r in rows],
        documents=texts,
        embeddings=[v.tolist() for v in vectors],
        metadatas=[{k: v for k, v in r.items() if k not in ("id", "text")} for r in rows],
    )
    print(f"\n✅ '{COLLECTION}' collection rebuilt: {col.count()} chunks")


if __name__ == "__main__":
    utf8_console()
    main()