"""All embedding and Gemini calls go through here."""
import os, time

import numpy as np
from dotenv import load_dotenv

# "local" = free BGE-small model on your laptop (default); "gemini" = Gemini API embeddings
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "local")
GEMINI_EMBED_MODEL = "gemini-embedding-001"
GEMINI_EMBED_DIM = 768
LOCAL_EMBED_MODEL = "BAAI/bge-small-en-v1.5"      # 384 dimensions, small and fast

_client = None
_local = None


# ---------- Gemini ----------
def get_client():
    global _client
    if _client is None:
        from google import genai
        load_dotenv()
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not found. Add it to your .env file.")
        _client = genai.Client(api_key=key)
    return _client


def _with_retries(fn, max_retries=8):
    wait = 10
    for _ in range(max_retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if any(code in msg for code in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
                print(f"   rate limited, waiting {wait}s... ({msg[:150]})")
                time.sleep(wait)
                wait = min(wait * 2, 120)
            else:
                raise
    raise RuntimeError("Gemini call failed after several retries.")


def _embed_gemini(texts, task_type):
    from google.genai import types
    client = get_client()
    res = _with_retries(lambda: client.models.embed_content(
        model=GEMINI_EMBED_MODEL, contents=list(texts),
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=GEMINI_EMBED_DIM)))
    return np.array([e.values for e in res.embeddings], dtype=np.float32)


# ---------- Local (free, offline) ----------
def _embed_local(texts, task_type):
    global _local
    if _local is None:
        from fastembed import TextEmbedding
        print("Loading local embedding model BAAI/bge-small-en-v1.5...", flush=True)
        _local = TextEmbedding(LOCAL_EMBED_MODEL)
    gen = _local.query_embed(list(texts)) if task_type == "RETRIEVAL_QUERY" else _local.passage_embed(list(texts))
    return np.array(list(gen), dtype=np.float32)


# ---------- Public function ----------
def embed_texts(texts, task_type="RETRIEVAL_DOCUMENT", backend=None):
    """Embed texts. task_type: RETRIEVAL_DOCUMENT for reviews, RETRIEVAL_QUERY for questions."""
    backend = backend or EMBED_BACKEND
    vecs = _embed_local(texts, task_type) if backend == "local" else _embed_gemini(texts, task_type)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)