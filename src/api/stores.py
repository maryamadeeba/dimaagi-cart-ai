"""Stores: the demo store (dunnhumby, the data folder's own models/ and config/) and the owner's stores under
stores/<slug>/. The demo store is never written to: imports and retraining always go to an owner's store.

The existing modules keep store files at module-level relative paths (generate.SEGMENTS_PATH, campaign.OUT_JSON...).
Switching store points those constants at the active store's folder. Shared files (knowledge bases, caches,
config/niche.yaml, config/trend_sources.csv) stay at the data-folder root for every store.
"""
import importlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from src.api import config

DEMO = "demo"
DEMO_LABEL = "Demo store: dunnhumby The Complete Journey, 2017"
STORES_DIR = Path("stores")
META = "store.json"

# module -> {constant: path inside a store's folder}
PATHS = {
    "src.api.views": {"SEGMENTS": "models/segments.json", "METRICS": "models/metrics.json",
                      "WHY": "models/why_summaries.json", "KITS": "models/campaign_kits.json",
                      "PROFILE": "config/store_profile.yaml", "DRIVERS": "models/drivers.json",
                      "SCORED": "models/scored_customers.csv", "FEATURES": "models/feature_columns.json",
                      "STORE_META": META},
    "src.rag.generate": {"SEGMENTS_PATH": "models/segments.json", "OUT_JSON": "models/why_summaries.json",
                         "OUT_MD": "models/why_summaries.md"},
    "src.rag.campaign": {"WHY_PATH": "models/why_summaries.json", "PROFILE_PATH": "config/store_profile.yaml",
                         "OUT_JSON": "models/campaign_kits.json", "OUT_MD": "models/campaign_kits.md"},
    "src.rag.assistant": {"WHY_PATH": "models/why_summaries.json", "KITS_PATH": "models/campaign_kits.json"},
}
_active = DEMO


class StoreError(Exception):
    pass


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    if not slug or slug == DEMO:
        raise StoreError("Choose a store name with letters or numbers (and not 'demo').")
    return slug


def root(slug=None):
    slug = slug or _active
    return Path(".") if slug == DEMO else STORES_DIR / slug


def active():
    return _active


def _patch(module):
    for attr, rel in PATHS.get(module.__name__, {}).items():
        setattr(module, attr, root() / rel)


def mod(name):
    """Import one of the path-holding modules, pointed at the active store."""
    m = importlib.import_module(name)
    _patch(m)
    return m


def activate(slug, remember=True):
    global _active
    if slug != DEMO and not (STORES_DIR / slug / META).exists():
        raise StoreError(f"No store '{slug}'.")
    _active = slug
    for name in PATHS:
        if name in sys.modules:
            _patch(sys.modules[name])
    if remember:
        config.write_settings(active_store=slug, mode="demo" if slug == DEMO else "own")


def restore():
    """At startup: reopen the store chosen last time (the demo store if it's gone)."""
    slug = config.read_settings().get("active_store") or DEMO
    try:
        activate(slug, remember=False)
    except StoreError:
        activate(DEMO, remember=False)


def read_meta(slug=None):
    slug = slug or _active
    if slug == DEMO:
        return {"slug": DEMO, "name": "Demo store", "demo": True, "label": DEMO_LABEL,
                "marketing_available": True, "scored_with": "store"}
    path = STORES_DIR / slug / META
    return {**json.loads(path.read_text(encoding="utf-8")), "slug": slug, "demo": False} if path.exists() else None


def write_meta(slug, **updates):
    if slug == DEMO:
        raise StoreError("The demo store is read-only.")
    path = STORES_DIR / slug / META
    meta = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    meta.update(updates)
    meta.pop("slug", None)
    meta.pop("demo", None)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def create(name):
    """A new owner's store: its own models/ and config/, with a store profile copied from the demo's template."""
    slug = slugify(name)
    folder = STORES_DIR / slug
    if (folder / META).exists():
        return slug
    for sub in ("models", "config", "input"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    template = Path("config/store_profile.yaml")
    if template.exists():
        text = template.read_text(encoding="utf-8")
        text = re.sub(r'^store_name:.*$', f'store_name: "{name.strip()}"', text, count=1, flags=re.M)
        (folder / "config/store_profile.yaml").write_text(text, encoding="utf-8")
    write_meta(slug, name=name.strip(), created=datetime.now().isoformat(timespec="seconds"),
               marketing_available=False)
    return slug


def all_stores():
    stores = [read_meta(DEMO)]
    if STORES_DIR.exists():
        for d in sorted(STORES_DIR.iterdir()):
            if (d / META).exists():
                stores.append(read_meta(d.name))
    return [{"slug": s["slug"], "name": s["name"], "demo": s["demo"],
             "scored": (root(s["slug"]) / "models/segments.json").exists()} for s in stores]


def require_writable(slug=None):
    if (slug or _active) == DEMO:
        raise StoreError("The demo store is read-only. Import your own data to create your store.")


PRETRAINED = "_behaviour"     # imported stores have no campaign/coupon/discount data: use the model trained without it


def pretrained_files():
    """The pre-trained model for imported stores: the behaviour-only model trained on the demo data."""
    return {f"{name}{PRETRAINED}{ext}": f"{name}{ext}"
            for name, ext in (("churn_model", ".pkl"), ("feature_columns", ".json"), ("metrics", ".json"))}


def copy_pretrained(slug):
    """Give an owner's store the shipped behaviour-only model, under the names src.segments reads."""
    require_writable(slug)
    dst = root(slug) / "models"
    dst.mkdir(parents=True, exist_ok=True)
    for shipped, name in pretrained_files().items():
        src = root(DEMO) / "models" / shipped
        if not src.exists():
            raise StoreError(f"The pre-trained model file {shipped} is missing.")
        shutil.copy2(src, dst / name)
