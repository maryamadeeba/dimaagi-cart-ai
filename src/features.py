import pandas as pd
import numpy as np

# Weekly staples from Finding 3
STAPLES = ["FLUID MILK PRODUCTS", "BAKED BREAD/BUNS/ROLLS", "CHEESE", "COLD CEREAL", "EGGS"]

INCOME_BANDS = {
    "Under 15K": "Under $35K", "15-24K": "Under $35K", "25-34K": "Under $35K",
    "35-49K": "$35-74K", "50-74K": "$35-74K",
    "75-99K": "$75-149K", "100-124K": "$75-149K", "125-149K": "$75-149K",
    "150-174K": "$150K+", "175-199K": "$150K+", "200-249K": "$150K+", "250K+": "$150K+"}

DEPTS = ["GROCERY", "DRUG GM", "FUEL", "PRODUCE", "MEAT", "MEAT-PCKGD", "DELI"]
# Kept for reporting, but NOT used by the model (they grow with time and leak the cutoff date)
NON_MODEL_COLS = ["trips", "total_spend", "tenure_days",
                  "campaigns_received", "type_a_received", "coupons_redeemed"]


def build_features(tx, prod, demo, camp, cdesc, redm, cutoff):
    """One row per household, using ONLY data on or before the cutoff (no leakage)."""
    t = tx[tx["transaction_timestamp"] <= cutoff].copy()
    weeks = (cutoff - t["transaction_timestamp"].min()).days / 7

    # --- Shopping trips (baskets) ---
    baskets = (t.groupby(["household_id", "basket_id"])
                 .agg(ts=("transaction_timestamp", "min"), value=("sales_value", "sum"))
                 .reset_index().sort_values(["household_id", "ts"]))
    b = baskets.groupby("household_id")

    f = pd.DataFrame({
        "recency_days": (cutoff - b["ts"].max()).dt.days,      # R
        "trips":        b.size(),                               # F
        "total_spend":  b["value"].sum(),                       # M
        "avg_basket":   b["value"].mean(),
        "tenure_days":  (cutoff - b["ts"].min()).dt.days,
    })
    f["trips_per_week"] = f["trips"] / weeks
    f["spend_per_week"] = f["total_spend"] / weeks

    # Gaps between trips (Finding 2: gaps are an early warning)
    baskets["gap"] = b["ts"].diff().dt.days
    f["avg_gap_days"] = baskets.groupby("household_id")["gap"].mean()
    f["max_gap_days"] = baskets.groupby("household_id")["gap"].max()

    # Recent trend: last 8 weeks vs. their usual
    recent = baskets[baskets["ts"] > cutoff - pd.Timedelta(weeks=8)]
    f["trips_last_8w"] = recent.groupby("household_id").size().reindex(f.index, fill_value=0)
    f["spend_last_8w_per_week"] = (recent.groupby("household_id")["value"].sum()
                                   .reindex(f.index, fill_value=0) / 8)
    f["spend_trend"] = f["spend_last_8w_per_week"] / f["spend_per_week"]

    # Last 4 weeks: an even sharper "drifting away" signal
    last4 = baskets[baskets["ts"] > cutoff - pd.Timedelta(weeks=4)]
    f["trips_last_4w"] = last4.groupby("household_id").size().reindex(f.index, fill_value=0)
    f["spend_last_4w_per_week"] = (last4.groupby("household_id")["value"].sum()
                                   .reindex(f.index, fill_value=0) / 4)
    f["spend_trend_4w"] = f["spend_last_4w_per_week"] / f["spend_per_week"]
    f["trip_trend_4w"] = (f["trips_last_4w"] / 4) / f["trips_per_week"]

    # How consistently they shop: share of weeks with at least one trip
    active_weeks = (baskets.assign(wk=baskets["ts"].dt.to_period("W"))
                           .groupby("household_id")["wk"].nunique())
    f["active_week_share"] = active_weeks / weeks

    # Discounts and stores
    disc = t[["retail_disc", "coupon_disc", "coupon_match_disc"]].abs().sum(axis=1)
    f["discount_share"] = disc.groupby(t["household_id"]).sum() / f["total_spend"]
    f["n_stores"] = t.groupby("household_id")["store_id"].nunique()

    # --- What they buy (Finding 3) ---
    tp = t.merge(prod[["product_id", "department", "product_category"]], on="product_id", how="left")
    dept = tp.pivot_table(index="household_id", columns="department",
                          values="sales_value", aggfunc="sum", fill_value=0)
    dept = dept.div(dept.sum(axis=1), axis=0)
    for d in DEPTS:
        col = "share_" + d.lower().replace(" ", "_").replace("-", "_")
        f[col] = dept[d].reindex(f.index, fill_value=0) if d in dept.columns else 0
    f["n_departments"] = tp.groupby("household_id")["department"].nunique()

    st = tp[tp["product_category"].isin(STAPLES)]
    f["staples_share"] = st.groupby("household_id")["sales_value"].sum().reindex(f.index, fill_value=0) / f["total_spend"]
    f["days_since_staple"] = (cutoff - st.groupby("household_id")["transaction_timestamp"].max()).dt.days
    f["days_since_staple"] = f["days_since_staple"].reindex(f.index).fillna(365)

    # --- Marketing (Finding 5) ---
    cd = cdesc.copy()
    cd["start_date"] = pd.to_datetime(cd["start_date"])
    c = camp.merge(cd, on="campaign_id")
    c = c[c["start_date"] <= cutoff]
    f["campaigns_received"] = c.groupby("household_id")["campaign_id"].nunique().reindex(f.index, fill_value=0)
    f["type_a_received"] = (c[c["campaign_type"] == "Type A"].groupby("household_id")["campaign_id"]
                            .nunique().reindex(f.index, fill_value=0))
    f["ever_targeted"] = (f["campaigns_received"] > 0).astype(int)

    r = redm.copy()
    r["redemption_date"] = pd.to_datetime(r["redemption_date"])
    r = r[r["redemption_date"] <= cutoff]
    f["coupons_redeemed"] = r.groupby("household_id").size().reindex(f.index, fill_value=0)
    # Rates instead of totals, so features mean the same thing at every cutoff
    f["campaigns_per_week"] = f["campaigns_received"] / weeks
    f["type_a_per_week"]    = f["type_a_received"] / weeks
    f["coupons_per_week"]   = f["coupons_redeemed"] / weeks

    # --- Who they are (Finding 4) ---
    d = demo.set_index("household_id")[["age", "income", "household_size", "kids_count",
                                        "marital_status", "home_ownership"]].copy()
    d["income_band"] = d["income"].map(INCOME_BANDS)
    d = d.drop(columns="income")
    f = f.join(d)
    f["demo_unknown"] = f["age"].isna().astype(int)
    for col in ["age", "income_band", "household_size", "kids_count", "marital_status", "home_ownership"]:
            f[col] = f[col].fillna("Unknown").astype(str)

    return f.reset_index()