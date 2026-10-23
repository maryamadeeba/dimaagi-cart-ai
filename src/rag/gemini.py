"""Shared Gemini helper: JSON output checked against a Pydantic schema, disk cache, smart retries."""
import hashlib
import json
import os
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CACHE_DIR = Path("data/processed/gen_cache")
RETRYABLE = ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE")


def gemini_json(prompt, schema, model=None, temperature=0.0, refresh=False):
    """Returns (result_dict, was_cached). refresh=True skips the cached answer and asks again (the new one is cached)."""
    model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    key = hashlib.sha256((model + schema.__name__ + prompt).encode("utf-8")).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text(encoding="utf-8")), True

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
    )
    for attempt in range(4):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            break
        except Exception as e:
            msg = str(e)
            if "404" in msg or "NOT_FOUND" in msg:
                raise SystemExit(f"\n❌ Model '{model}' not found for your API key. Check the model name in .env.")
            if "PerDay" in msg or "per day" in msg.lower():
                raise SystemExit("\n⏸ Daily Gemini quota used up. Progress is cached: rerun the same "
                                 "command after the quota resets (midnight Pacific = 12:00 noon in Pakistan).")
            if not any(code in msg for code in RETRYABLE) or attempt == 3:
                raise
            wait = 20 * (attempt + 1)
            print(f"  Gemini busy or rate-limited ({msg[:60]}), retrying in {wait}s", flush=True)
            time.sleep(wait)

    out = schema.model_validate_json(resp.text).model_dump()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out, False

def cached_result(prompt, schema, model):
    """Return a cached Gemini result without calling the API (None if it was never run)."""
    key = hashlib.sha256((model + schema.__name__ + prompt).encode("utf-8")).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{key}.json"
    return json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else None