"""Offline tests for bring-your-own-data, the ML explanations and the fixes from the Phase 3 review.
Every dataset here is synthetic and made in the test; no Gemini calls, nothing read from the real data/ or models/."""
import hashlib
import io
import json
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import train
from src.api import importer, jobs, stores, views
from src.api.app import create_app
from src.explain import phrase, top_drivers
from src.features import build_features

TOKEN = "t"
H = {"X-Dimaagi-Token": TOKEN}
CATS = {"Dairy": [("Whole milk", 3.5), ("Cheddar", 4.0)], "Bakery": [("Sourdough loaf", 4.5)],
        "Produce": [("Bananas", 1.8), ("Apples", 3.0)], "Meat": [("Chicken breast", 8.0)],
        "Snacks": [("Crisps", 2.5)], "Household": [("Dish soap", 3.2)]}


def synthetic_sales(n_customers=90, days=300, seed=0):
    """A small store: regular shoppers, about 40% start drifting (fewer trips, no dairy) at some point."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01 09:00")
    items = [(c, n, p) for c, lst in CATS.items() for n, p in lst]
    rows = []
    for cid in range(1, n_customers + 1):
        drift = rng.uniform(90, 290) if rng.random() < 0.4 else None
        for day in range(days):
            drifting = drift is not None and day > drift
            if rng.random() > (0.08 if drifting else 0.3):
                continue
            when = start + pd.Timedelta(days=day, minutes=int(rng.integers(0, 600)))
            for _ in range(int(rng.integers(2, 6))):
                cat, name, price = items[rng.integers(len(items))]
                if drifting and cat in ("Dairy", "Bakery"):
                    continue
                rows.append([f"C{cid:04d}", when.strftime("%Y-%m-%d %H:%M"), name, cat, 1, price])
    return pd.DataFrame(rows, columns=["Customer Number", "Sale Date", "Item", "Dept", "Qty", "Total $"])


MAPPING = {"customer_id": "Customer Number", "timestamp": "Sale Date", "amount": "Total $",
           "category": "Dept", "product": "Item", "quantity": "Qty"}


# ---------- review quotes ----------
def test_short_quote_first_sentence_cut_at_a_word():
    assert views.short_quote("Milk was off. Bread too.") == "Milk was off."
    long = "word " * 60
    short = views.short_quote(long)
    assert len(short) <= views.SHORT_QUOTE + 1 and short.endswith("…") and not short[:-1].endswith(" ")


def test_review_quote_is_the_sentence_that_matches_the_reason():
    text = ("I was unimpressed. The parking lot is tiny. The milk is always expired no matter what the date says. "
            "Staff were fine.")
    context = "Expired or spoiled milk: shoppers report milk that was already expired. milk: milk not fresh, expired"
    assert views.best_quote(text, context) == "The milk is always expired no matter what the date says."


def test_review_quote_ties_go_to_the_earliest_and_no_overlap_falls_back_to_the_first():
    assert views.best_quote("Bread was stale. Bread was stale again.", "stale bread") == "Bread was stale."
    assert views.best_quote("Nice store. Clean floors.", "expired milk") == "Nice store."
    assert views.best_quote("the and of it. Milk!", "the and of it milk") == "Milk!"   # stop words don't count


def test_review_quote_is_capped_at_a_word():
    long = "Milk " + "really very expensive milk " * 20 + "here."
    q = views.best_quote(long, "milk")
    assert len(q) <= views.SHORT_QUOTE + 1 and q.endswith("…")


# ---------- behaviour-only model ----------
def test_no_marketing_drops_exactly_the_marketing_features():
    df = pd.DataFrame({"household_id": [1], "silent_churn": [0], "recency_days": [3.0], "spend_trend": [0.5],
                       "ever_targeted": [1], "campaigns_per_week": [0.2], "type_a_per_week": [0.1],
                       "coupons_per_week": [0.3], "discount_share": [0.05], "trips": [9]})
    assert list(train.make_X(df).columns) == ["recency_days", "spend_trend", "ever_targeted", "campaigns_per_week",
                                              "type_a_per_week", "coupons_per_week", "discount_share"]
    assert list(train.make_X(df, marketing=False).columns) == ["recency_days", "spend_trend"]


def test_imported_stores_get_the_behaviour_model(data_root):
    slug = stores.create("Shop A")
    stores.copy_pretrained(slug)
    models = data_root / "stores" / slug / "models"
    shipped = data_root / "models"
    assert (models / "churn_model.pkl").read_bytes() == (shipped / "churn_model_behaviour.pkl").read_bytes()
    assert (models / "churn_model.pkl").read_bytes() != (shipped / "churn_model.pkl").read_bytes()
    cols = json.loads((models / "feature_columns.json").read_text())
    assert cols == json.loads((shipped / "feature_columns_behaviour.json").read_text())
    assert not set(cols) & set(train.MARKETING_COLS)


# ---------- B: explanations ----------
def test_driver_phrases_are_plain_english():
    assert phrase("spend_trend_4w", 0.52) == "Spending 48% less than usual over the last 4 weeks"
    assert phrase("days_since_staple", 24) == "24 days since buying staples (milk, bread, cheese, cereal, eggs)"
    assert phrase("trip_trend_4w", 0.0) == "Visits stopped completely in the last 4 weeks"
    assert phrase("coupons_per_week", 0) == "Has never redeemed a coupon"


def test_top_drivers_sorted_by_size_with_direction():
    X = pd.DataFrame({"recency_days": [30.0], "spend_trend_4w": [0.5], "staples_share": [0.2]})
    d = top_drivers(X, np.array([[0.1, 0.9, -0.4]]), k=2)[0]
    assert [x["feature"] for x in d] == ["spend_trend_4w", "staples_share"]
    assert d[0]["direction"] == "raises risk" and d[1]["direction"] == "lowers risk"


# ---------- D: import ----------
def test_column_auto_mapping():
    assert importer.suggest_mapping(["Customer Number", "Sale Date", "Item", "Dept", "Qty", "Total $"]) == MAPPING
    dunnhumby = ["household_id", "store_id", "basket_id", "product_id", "quantity", "sales_value",
                 "retail_disc", "transaction_timestamp", "product_category"]
    m = importer.suggest_mapping(dunnhumby)
    assert (m["customer_id"], m["timestamp"], m["amount"], m["category"], m["product"]) == \
        ("household_id", "transaction_timestamp", "sales_value", "product_category", "product_id")


def test_template_maps_itself():
    df = pd.read_csv(io.StringIO(importer.template_csv()))
    assert list(df.columns) == importer.TEMPLATE_COLUMNS and len(df) > 0
    m = importer.suggest_mapping(list(df.columns))
    assert all(m[f] for f in importer.FIELDS)


def test_category_suggestions():
    assert importer.suggest_category("Dairy & Milk") == "STAPLE:FLUID MILK PRODUCTS"
    assert importer.suggest_category("Fresh Fruit") == "PRODUCE"
    assert importer.suggest_category("Bakery") == "STAPLE:BAKED BREAD/BUNS/ROLLS"
    assert importer.suggest_category("Household cleaning") == "DRUG GM"
    assert importer.suggest_category("Gift cards") == importer.OTHER


def test_conversion_feeds_build_features():
    raw = synthetic_sales(n_customers=12, days=120).astype(str)
    df, problems = importer.clean(raw, MAPPING)
    assert not problems
    tx, products = importer.convert(df, {})
    assert {"household_id", "basket_id", "product_id", "sales_value", "transaction_timestamp",
            "store_id", "retail_disc", "coupon_disc", "coupon_match_disc"} <= set(tx.columns)
    assert set(products.columns) == {"product_id", "department", "product_category"}
    milk = products.merge(tx[["product_id"]].drop_duplicates())
    assert "FLUID MILK PRODUCTS" in set(products["product_category"])        # Dairy -> the staple category
    assert set(products["department"]) <= set(importer.DEPTS) | {importer.OTHER}
    # one basket per customer visit
    visits = df.groupby(["customer_id", "timestamp"]).ngroups
    assert tx["basket_id"].nunique() == visits and len(milk) > 0
    empty = {name: pd.DataFrame(columns=cols) for name, cols in jobs.TABLE_COLUMNS.items()}
    fe = build_features(tx, products, empty["demographics"], empty["campaigns"], empty["campaign_descriptions"],
                        empty["coupon_redemptions"], tx["transaction_timestamp"].max())
    assert len(fe) == tx["household_id"].nunique()
    assert (fe["campaigns_per_week"] == 0).all() and (fe["coupons_per_week"] == 0).all()
    assert fe["staples_share"].gt(0).any() and fe["share_produce"].gt(0).any()


def test_clean_drops_bad_rows_and_reports_them():
    raw = pd.DataFrame({"c": ["A", "", "B", "C"], "d": ["2025-01-01", "2025-01-02", "not a date", "2025-01-03"],
                        "a": ["$3.50", "2", "1", "-1"]})
    df, problems = importer.clean(raw, {"customer_id": "c", "timestamp": "d", "amount": "a"})
    assert len(df) == 1 and df["amount"].iloc[0] == 3.5
    assert problems == {"missing customer ID": 1, "unreadable date": 1, "zero or negative amount (returns)": 1}
    with pytest.raises(ValueError, match="Amount paid"):
        importer.clean(raw, {"customer_id": "c", "timestamp": "d"})


def test_history_rule():
    assert importer.min_training_days() == 240
    def tx_for(days):
        return pd.DataFrame({"household_id": [1, 1], "transaction_timestamp": pd.to_datetime(
            ["2025-01-01", "2025-01-01"]) + pd.to_timedelta([0, days], unit="D")})
    assert train.training_history(tx_for(250))["ok"]
    assert not train.training_history(tx_for(200))["ok"]
    h = train.training_history(tx_for(250))
    assert 238 <= h["needed_days"] <= 240 and len(h["cutoffs"]) == 3


def test_champion_challenger_keeps_the_better_model():
    assert jobs.choose_model({"roc_auc": 0.71}, {"roc_auc": 0.69}) == "store"
    assert jobs.choose_model({"roc_auc": 0.66}, {"roc_auc": 0.69}) == "pretrained"
    assert jobs.choose_model({"roc_auc": 0.70}, {"roc_auc": 0.70}) == "store"


# ---------- end to end: import into a store, the demo store untouched ----------
def file_hashes(folder):
    return {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """A data folder whose demo store has a model trained on synthetic data (standing in for dunnhumby)."""
    monkeypatch.chdir(tmp_path)
    raw = synthetic_sales(seed=1).astype(str)
    df, _ = importer.clean(raw, MAPPING)
    tx, products = importer.convert(df, {})
    jobs.write_inputs(tmp_path / "demo_input", tx, products)
    train.main(str(tmp_path / "demo_input"), "models")                       # full model (with marketing)
    train.main(str(tmp_path / "demo_input"), "models", marketing=False)      # behaviour-only model
    (tmp_path / "config").mkdir()
    (tmp_path / "config/store_profile.yaml").write_text('store_name: "[STORE NAME]"\n')
    stores.activate(stores.DEMO, remember=False)
    yield tmp_path
    stores.activate(stores.DEMO, remember=False)


def wait(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if job["status"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


@pytest.mark.parametrize("mode", ["train", "pretrained"])
def test_import_scores_a_new_store_and_never_touches_the_demo(data_root, mode):
    demo_before = file_hashes(data_root / "models")
    client = TestClient(create_app(TOKEN))
    csv = synthetic_sales(seed=2).to_csv(index=False).encode()
    up = client.post("/api/import/upload", files={"file": ("sales.csv", csv, "text/csv")}, headers=H).json()
    assert up["suggested"] == MAPPING and len(up["preview"]) == importer.PREVIEW_ROWS

    a = client.post(f"/api/import/{up['import_id']}/analyze", json={"mapping": up["suggested"]}, headers=H).json()
    rep = a["report"]
    assert rep["customers"] == 90 and rep["can_score"] and rep["can_train"] and rep["min_training_days"] <= 240
    assert {c["name"]: c["target"] for c in a["categories"]}["Dairy"] == "STAPLE:FLUID MILK PRODUCTS"

    run = client.post(f"/api/import/{up['import_id']}/run", headers=H,
                      json={"mapping": up["suggested"], "store_name": "Corner Shop", "mode": mode}).json()
    job = wait(client, run["id"])
    assert job["status"] == "done", job
    store = data_root / "stores" / "corner-shop"
    assert (store / "models/segments.json").exists() and (store / "models/drivers.json").exists()
    metrics = json.loads((store / "models/metrics.json").read_text())
    if mode == "train":
        comp = metrics["comparison"]
        assert comp["kept"] in ("store", "pretrained")
        assert metrics["marketing_features"] is False or metrics["source"] == "pretrained"
        assert {"roc_auc", "capture"} <= set(comp["store_model"]) and "roc_auc" in comp["pretrained_model"]
    else:
        assert metrics["source"] == "pretrained" and metrics["marketing_features"] is False
    assert file_hashes(data_root / "models") == demo_before              # the demo store was not touched
    assert not (data_root / "models/segments.json").exists()

    health = client.get("/api/health", headers=H).json()
    assert health["app"]["active_store"] == "corner-shop" and health["app"]["mode"] == "own"
    cust = client.get("/api/customers?page_size=5", headers=H).json()
    assert cust["all"] > 0 and len(cust["rows"]) <= 5
    card = client.get("/api/model", headers=H).json()
    assert card["marketing_available"] is False and card["behaviour_only"] is True
    listed = {f["feature"] for g in card["features"] for f in g["features"]}
    assert not listed & set(train.MARKETING_COLS)                         # nothing zero-filled
    assert set(card["pretrained_models"]) == {"full", "behaviour"}
    store_cols = json.loads((store / "models/feature_columns.json").read_text())
    assert len(store_cols) == 25 and not set(store_cols) & set(train.MARKETING_COLS)

    client.post("/api/stores/activate", json={"slug": "demo"}, headers=H)
    r = client.get("/api/dashboard", headers=H)
    assert r.status_code == 404 and r.json()["what"] == "segments"     # the demo store has no segments here


def test_demo_store_is_read_only(data_root):
    with pytest.raises(stores.StoreError):
        stores.require_writable(stores.DEMO)
    with pytest.raises(stores.StoreError):
        stores.copy_pretrained(stores.DEMO)
    with pytest.raises(stores.StoreError):
        stores.slugify("Demo")


def test_regenerate_needs_a_key(data_root, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("src.api.config.get_key", lambda: None)
    client = TestClient(create_app(TOKEN))
    r = client.post("/api/regenerate", json={"what": "both"}, headers=H)
    assert r.status_code == 404 and r.json()["what"] == "segments"       # nothing scored yet
    (data_root / "models/segments.json").write_text(json.dumps({"segments": [
        {"segment": "Core · Visiting less", "customers": 20, "weekly_revenue_at_risk": 100.0,
         "reason_mix": {"Visiting less": 1.0}, "top_lapsed_categories": []}]}))
    r = client.post("/api/segments/corevisiting/regenerate", json={"what": "reasons"}, headers=H)
    assert r.status_code == 400 and r.json()["error"] == "no_key"
