"""Bring your own data: read a store's CSV/Excel export, match its columns and categories, check it, and convert it
into the transactions + products tables src/features.py expects (the dunnhumby layout)."""
import csv
import re
from pathlib import Path

import pandas as pd

from src.features import DEPTS, STAPLES
from src.train import HORIZON_DAYS, MIN_PRE_HISTORY_DAYS, training_history

PREVIEW_ROWS = 8
REGULAR_TRIPS = 5           # src.segments / src.labels only score customers with 5+ trips
MIN_SEGMENT = 10            # smaller segments are flagged as too small to be meaningful

# field -> (label, required?, column names that usually mean it, most specific first)
FIELDS = {
    "customer_id": ("Customer ID", True, ["customer_id", "household_id", "customer", "customer_number", "member_id",
                                          "loyalty_id", "loyalty_card", "client_id", "card_number", "account"]),
    "timestamp": ("Date / time", True, ["transaction_timestamp", "timestamp", "datetime", "transaction_date",
                                        "order_date", "sale_date", "purchase_date", "date_time", "date", "time"]),
    "amount": ("Amount paid", True, ["sales_value", "amount_paid", "amount", "line_total", "total", "net_sales",
                                     "sales", "revenue", "paid", "value", "price"]),
    "category": ("Product category / department", False, ["product_category", "category", "department", "dept",
                                                          "product_group", "group", "class", "section", "aisle"]),
    "product": ("Product name", False, ["product_name", "product", "item_name", "item", "description", "sku",
                                        "product_id", "item_id", "upc"]),
    "quantity": ("Quantity", False, ["quantity", "qty", "units", "count"]),
}
TEMPLATE_COLUMNS = ["customer_id", "date", "product_name", "category", "quantity", "amount_paid"]
TEMPLATE_ROWS = [
    ["C1001", "2025-03-01 09:14", "Whole milk 1 gal", "Dairy", 1, 3.49],
    ["C1001", "2025-03-01 09:14", "Sourdough loaf", "Bakery", 1, 4.99],
    ["C1002", "2025-03-02 17:40", "Bananas", "Produce", 6, 1.74],
    ["C1001", "2025-03-08 10:02", "Cheddar 8oz", "Dairy", 1, 3.29],
]

# Where a store category can go. Staples also count toward the model's staples features.
STAPLE_NAMES = {"FLUID MILK PRODUCTS": "Milk", "BAKED BREAD/BUNS/ROLLS": "Bread", "CHEESE": "Cheese",
                "COLD CEREAL": "Cereal", "EGGS": "Eggs"}
DEPT_NAMES = {"GROCERY": "Grocery (packaged food and drinks)", "DRUG GM": "Health, beauty and household",
              "FUEL": "Fuel", "PRODUCE": "Fresh produce", "MEAT": "Fresh meat", "MEAT-PCKGD": "Packaged meat",
              "DELI": "Deli"}
OTHER = "OTHER"
STAPLE_DEPT = "GROCERY"      # in dunnhumby every staple category sits in GROCERY
TARGETS = ([{"value": f"STAPLE:{c}", "label": f"{n} (staple)", "department": STAPLE_DEPT} for c, n in STAPLE_NAMES.items()]
           + [{"value": d, "label": DEPT_NAMES.get(d, d.title()), "department": d} for d in DEPTS]
           + [{"value": OTHER, "label": "Other (not used by the model)", "department": OTHER}])
assert set(STAPLE_NAMES) == set(STAPLES)

KEYWORDS = [  # first match wins
    ("STAPLE:FLUID MILK PRODUCTS", r"\bmilk|\bdairy"),("STAPLE:EGGS", r"\beggs?\b"), ("STAPLE:CHEESE", r"chees"),
    ("STAPLE:BAKED BREAD/BUNS/ROLLS", r"bread|bak(ery|ed)|buns?\b|rolls?\b|bagel|loa(f|ves)"),
    ("STAPLE:COLD CEREAL", r"cereal|granola|muesli"),
    ("MEAT-PCKGD", r"packaged meat|bacon|sausage|hot ?dog|lunch ?meat|cold cuts|ham\b|jerky"),
    ("DELI", r"\bdeli|prepared|hot food|rotisserie|sandwich"),
    ("MEAT", r"meat|beef|pork|chicken|poultry|lamb|butcher|seafood|fish|turkey"),
    ("PRODUCE", r"produce|fruit|vegetable|veg\b|veggie|salad|herb|organic fresh|flower|floral"),
    ("FUEL", r"fuel|gas(oline)?\b|petrol|diesel"),
    ("DRUG GM", r"pharm|drug|health|beauty|cosmetic|personal care|household|clean|paper|toilet|baby|pet\b|"
                r"general merch|vitamin|medicine|hardware|kitchenware"),
    ("GROCERY", r"grocery|pantry|dairy|yog(h)?urt|butter|frozen|snack|chips|candy|confection|beverage|drink|soda|"
                r"juice|water|coffee|tea\b|canned|soup|pasta|rice|sauce|spice|condiment|baking|cereal|cookie|"
                r"cracker|ice cream|beer|wine|spirits|alcohol|tobacco"),
]


# ---------- reading ----------
def read_table(path, nrows=None):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return pd.read_excel(path, nrows=nrows, dtype=str)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                head = f.read(8192)
            try:
                sep = csv.Sniffer().sniff(head, delimiters=",;\t|").delimiter
            except csv.Error:
                sep = ","
            return pd.read_csv(path, nrows=nrows, dtype=str, encoding=enc, sep=sep, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    raise ValueError("The file couldn't be read as text. Save it as UTF-8 CSV or Excel (.xlsx).")


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def suggest_mapping(columns):
    """Best guess for each field: an exact alias first, then a column containing an alias. Each column used once."""
    norm = {c: _norm(c) for c in columns}
    used, out = set(), {}
    # fill the most specific fields first, so 'product_category' goes to category, not product
    for field in ("customer_id", "timestamp", "amount", "category", "quantity", "product"):
        aliases = FIELDS[field][2]
        pick = next((c for a in aliases for c in columns if c not in used and norm[c] == a), None)
        if pick is None:
            pick = next((c for a in aliases for c in columns
                         if c not in used and len(a) > 3 and a in norm[c]), None)
        out[field] = pick
        if pick:
            used.add(pick)
    return out


def template_csv():
    return pd.DataFrame(TEMPLATE_ROWS, columns=TEMPLATE_COLUMNS).to_csv(index=False)


def suggest_category(name):
    text = str(name).lower()
    for target, pattern in KEYWORDS:
        if re.search(pattern, text):
            return target
    return OTHER


# ---------- cleaning ----------
def _money(series):
    return pd.to_numeric(series.astype(str).str.replace(r"[$£€,\s]", "", regex=True), errors="coerce")


def clean(raw, mapping):
    """Mapped columns only, typed. Returns (clean frame, problems: {what: rows dropped})."""
    missing = [FIELDS[f][0] for f, (_, req, _) in FIELDS.items() if req and not mapping.get(f)]
    if missing:
        raise ValueError(f"Match these required columns first: {', '.join(missing)}.")
    unknown = [c for c in mapping.values() if c and c not in raw.columns]
    if unknown:
        raise ValueError(f"These columns aren't in the file: {', '.join(unknown)}.")
    df = pd.DataFrame({
        "customer_id": raw[mapping["customer_id"]].astype(str).str.strip(),
        "timestamp": pd.to_datetime(raw[mapping["timestamp"]], errors="coerce", format="mixed"),
        "amount": _money(raw[mapping["amount"]]),
        "category": raw[mapping["category"]].astype(str).str.strip() if mapping.get("category") else "Uncategorized",
        "product": raw[mapping["product"]].astype(str).str.strip() if mapping.get("product") else None,
        "quantity": pd.to_numeric(raw[mapping["quantity"]], errors="coerce") if mapping.get("quantity") else 1,
    })
    df["category"] = df["category"].replace({"": "Uncategorized", "nan": "Uncategorized"})
    if df["product"].isna().all():
        df["product"] = df["category"]
    df["quantity"] = df["quantity"].fillna(1)
    problems = {
        "missing customer ID": int(df["customer_id"].isin(["", "nan", "None"]).sum()),
        "unreadable date": int(df["timestamp"].isna().sum()),
        "unreadable amount": int(df["amount"].isna().sum()),
        "zero or negative amount (returns)": int((df["amount"] <= 0).sum()),
    }
    keep = (~df["customer_id"].isin(["", "nan", "None"]) & df["timestamp"].notna()
            & df["amount"].notna() & (df["amount"] > 0))
    return df[keep].reset_index(drop=True), {k: v for k, v in problems.items() if v}


def categories(df, category_map=None):
    category_map = category_map or {}
    g = df.groupby("category")["amount"].agg(rows="size", sales="sum").sort_values("sales", ascending=False)
    total = g["sales"].sum() or 1
    return [{"name": c, "rows": int(r.rows), "share_of_sales": round(float(r.sales / total), 4),
             "suggested": suggest_category(c), "target": category_map.get(c) or suggest_category(c)}
            for c, r in g.iterrows()]


# ---------- conversion ----------
def convert(df, category_map):
    """-> (transactions, products) in the layout src.train.load_data reads. One basket = one customer at one time."""
    targets = {c: category_map.get(c) or suggest_category(c) for c in df["category"].unique()}
    has_time = (df["timestamp"].dt.normalize() != df["timestamp"]).any()
    visit = df["timestamp"] if has_time else df["timestamp"].dt.normalize()

    prod_key = df["product"].astype(str) + "\x1f" + df["category"].astype(str)
    product_id, uniques = pd.factorize(prod_key)
    products = pd.DataFrame({"product_id": range(1, len(uniques) + 1),
                             "category": [u.split("\x1f", 1)[1] for u in uniques]})
    target = products["category"].map(targets)
    products["department"] = target.where(~target.str.startswith("STAPLE:"), STAPLE_DEPT)
    # staples take the model's staple category names; everything else keeps the store's own category name
    products["product_category"] = target.where(target.str.startswith("STAPLE:"), products["category"].str.upper())
    products["product_category"] = products["product_category"].str.replace("STAPLE:", "", regex=False)
    products = products[["product_id", "department", "product_category"]]

    basket_id, _ = pd.factorize(df["customer_id"] + "\x1f" + visit.astype(str))
    tx = pd.DataFrame({
        "household_id": df["customer_id"], "store_id": 1, "basket_id": basket_id + 1,
        "product_id": product_id + 1, "quantity": df["quantity"], "sales_value": df["amount"].round(2),
        "retail_disc": 0.0, "coupon_disc": 0.0, "coupon_match_disc": 0.0,     # no discount data: discount_share = 0
        "transaction_timestamp": df["timestamp"],
    }).sort_values("transaction_timestamp", kind="stable")
    return tx.reset_index(drop=True), products


# ---------- data check ----------
def report(df, problems, category_map=None):
    tx, _ = convert(df, category_map or {})
    trips = tx.groupby("household_id")["basket_id"].nunique()
    first, last = tx["transaction_timestamp"].min(), tx["transaction_timestamp"].max()
    days = int((last - first).days)
    history = training_history(tx) if days > HORIZON_DAYS else {"ok": False, "days": days, "needed_days": None}
    cats = categories(df, category_map)
    unmatched = sum(c["share_of_sales"] for c in cats if c["target"] == OTHER)
    regular = int((trips >= REGULAR_TRIPS).sum())
    notes = []
    if not (df["timestamp"].dt.normalize() != df["timestamp"]).any():
        notes.append("The dates have no times, so all of a customer's purchases on one day count as one trip.")
    if len(cats) == 1:
        notes.append("No product categories: basket-mix features (fresh produce, staples...) will be weak.")
    if unmatched > 0.2:
        notes.append(f"{unmatched:.0%} of sales are in categories matched to 'Other', which the model doesn't use.")
    notes.append("No campaign, coupon or discount data, so Dimaagi Cart uses its behaviour-only model, which doesn't rely on them.")
    return {
        "rows": int(len(tx)), "dropped": problems, "customers": int(trips.size), "regular_customers": regular,
        "from": str(first.date()), "to": str(last.date()), "days": days, "weeks": round(days / 7, 1),
        "trips": int(trips.sum()), "sales": round(float(tx["sales_value"].sum()), 2),
        "can_score": regular > 0,
        "can_train": bool(history["ok"]),
        "min_training_days": history.get("needed_days") or min_training_days(),
        "training_cutoffs": history.get("cutoffs", []),
        "notes": notes,
    }


def min_training_days():
    """Typical minimum from src.train: 61-day outcome window + 4 months between the 3 cutoffs + 8 weeks before."""
    return HORIZON_DAYS + 123 + MIN_PRE_HISTORY_DAYS     # 123 = the longest 4 calendar months
