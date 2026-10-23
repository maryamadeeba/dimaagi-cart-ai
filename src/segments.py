"""Score current customers and group at-risk ones into segments.
Run from the project root:  python -m src.segments
"""
import argparse, json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from src.explain import top_drivers
from src.features import build_features
from src.train import load_data, make_X
from src.console import utf8_console

THEMES = {
    "Spending is falling":      ["spend_trend", "spend_trend_4w", "spend_last_8w_per_week",
                                 "spend_last_4w_per_week", "spend_per_week", "avg_basket"],
    "Visiting less often":      ["recency_days", "trips_last_8w", "trips_last_4w", "trip_trend_4w",
                                 "avg_gap_days", "max_gap_days", "active_week_share", "trips_per_week"],
    "Shopping basket changed":  ["days_since_staple", "staples_share", "n_departments"],  # + share_* added below
    "Low marketing engagement": ["campaigns_per_week", "type_a_per_week", "coupons_per_week",
                                 "ever_targeted", "discount_share"],
}
REASON_LABELS = {"Shopping basket changed": "Basket changed", "Visiting less often": "Visiting less"}
NON_PRODUCT = r"COUPON|GASOLINE|FUEL|MISC ITEMS|DEPOSIT|BAG"   # till entries, not products


def score_customers(tx, t, model_dir, as_of, min_trips=5, at_risk_share=0.2):
    fe = build_features(tx, t["products"], t["demographics"], t["campaigns"],
                        t["campaign_descriptions"], t["coupon_redemptions"], as_of)
    fe = fe[fe["trips"] >= min_trips].reset_index(drop=True)

    cols = json.loads((Path(model_dir) / "feature_columns.json").read_text())
    X = make_X(fe).reindex(columns=cols, fill_value=0)
    model = joblib.load(Path(model_dir) / "churn_model.pkl")

    out = fe[["household_id", "spend_per_week", "trips_per_week", "recency_days"]].copy()
    out["risk"] = model.predict_proba(X)[:, 1]

    # SHAP → themes → underlying reason (beyond "spending is falling")
    sv = shap.TreeExplainer(model)(X).values
    out["drivers"] = top_drivers(X, sv)          # each customer's top 3 reasons, in plain English
    themes = dict(THEMES)
    themes["Shopping basket changed"] = themes["Shopping basket changed"] + [c for c in cols if c.startswith("share_")]
    for name, feats in themes.items():
        idx = [cols.index(f) for f in feats if f in cols]
        out[name] = sv[:, idx].clip(min=0).sum(axis=1)

    # Who is at risk, how valuable are they, and why?
    out["at_risk"] = out["risk"].rank(ascending=False, pct=True) <= at_risk_share
    out["tier"] = np.where(out["spend_per_week"] >= out["spend_per_week"].quantile(0.75), "High-value", "Core")
    reason = out[["Shopping basket changed", "Visiting less often"]].idxmax(axis=1).map(REASON_LABELS)
    out["reason"] = np.where(out["at_risk"], reason, "")
    out["segment"] = np.select(
        [~out["at_risk"], out["tier"] == "High-value"],
        ["Healthy", "High-value · at risk"],
        default="Core · " + reason)
    return out


def category_habits(tx, prod, as_of, weeks_recent=8, min_weekly=0.5, drop=0.5):
    """One row per (customer, category) they bought regularly ($0.50+/week),
    flagged `lapsed` if they cut it by 50%+ in the last 8 weeks."""
    t = tx[tx["transaction_timestamp"] <= as_of].merge(
        prod[["product_id", "product_category"]], on="product_id", how="left")
    t = t[~t["product_category"].fillna("").str.contains(NON_PRODUCT, case=False)]

    weeks_all = (as_of - t["transaction_timestamp"].min()).days / 7
    usual = t.groupby(["household_id", "product_category"])["sales_value"].sum() / weeks_all
    recent_t = t[t["transaction_timestamp"] > as_of - pd.Timedelta(weeks=weeks_recent)]
    recent = recent_t.groupby(["household_id", "product_category"])["sales_value"].sum() / weeks_recent

    df = usual.rename("usual").to_frame().join(recent.rename("recent")).fillna(0)
    df = df[df["usual"] >= min_weekly]
    df["lapsed"] = (1 - df["recent"] / df["usual"]) >= drop
    return df.reset_index()[["household_id", "product_category", "lapsed"]]


def build_profiles(scored, habits, top_n=5, min_buyers=10, min_lapsed=5):
    """For each segment: of the customers who REGULARLY bought a category, what share
    stopped? Compared with healthy customers in the SAME value tier (like for like)."""
    h = habits.merge(scored[["household_id", "segment", "tier", "at_risk"]], on="household_id")
    base = h[~h["at_risk"]].groupby(["tier", "product_category"])["lapsed"].mean()
    total_at_risk = scored.loc[scored["at_risk"], "spend_per_week"].sum()

    profiles = []
    for seg, g in scored[scored["at_risk"]].groupby("segment"):
        tier = g["tier"].iloc[0]
        s = h[h["segment"] == seg].groupby("product_category")["lapsed"].agg(rate="mean", lapsed="sum", buyers="size")
        s = s[(s["buyers"] >= min_buyers) & (s["lapsed"] >= min_lapsed)]
        s["healthy_rate"] = base.loc[tier].reindex(s.index).fillna(0).clip(lower=0.02)
        s["lift"] = s["rate"] / s["healthy_rate"]
        s = s.sort_values("lift", ascending=False).head(top_n)

        profiles.append({
            "segment": seg,
            "tier": tier,
            "customers": int(len(g)),
            "avg_risk": round(float(g["risk"].mean()), 3),
            "median_spend_per_week": round(float(g["spend_per_week"].median()), 2),
            "weekly_revenue_at_risk": round(float(g["spend_per_week"].sum()), 2),
            "share_of_revenue_at_risk": round(float(g["spend_per_week"].sum() / total_at_risk), 3),
            "reason_mix": {k: round(float(v), 2) for k, v in g["reason"].value_counts(normalize=True).items()},
            "top_lapsed_categories": [
                {"category": c, "regular_buyers": int(r.buyers), "dropped_rate": round(float(r.rate), 2),
                 "healthy_rate": round(float(r.healthy_rate), 2), "lift": round(float(r.lift), 1)}
                for c, r in s.iterrows()],
        })
    return sorted(profiles, key=lambda p: -p["weekly_revenue_at_risk"])


def main(data_dir, model_dir, as_of):
    tx, t = load_data(data_dir)
    as_of = pd.Timestamp(as_of) if as_of else tx["transaction_timestamp"].max().normalize()
    scored = score_customers(tx, t, model_dir, as_of)
    habits = category_habits(tx, t["products"], as_of)
    profiles = build_profiles(scored, habits)

    out = Path(model_dir)
    drivers = {str(h): d for h, d in zip(scored["household_id"], scored["drivers"])}
    (out / "drivers.json").write_text(json.dumps(drivers), encoding="utf-8")
    scored = scored.drop(columns="drivers")
    scored.to_csv(out / "scored_customers.csv", index=False)
    (out / "segments.json").write_text(json.dumps({"as_of": str(as_of.date()), "segments": profiles}, indent=2))

    total = sum(p["weekly_revenue_at_risk"] for p in profiles)
    print(f"As of {as_of.date()}: {len(scored)} regular customers, {int(scored['at_risk'].sum())} at risk, "
          f"${total:,.0f}/week revenue at risk\n")
    for p in profiles:
        print(f"{p['segment']:24s} {p['customers']:4d} customers | ${p['weekly_revenue_at_risk']:,.0f}/week "
              f"({p['share_of_revenue_at_risk']:.0%} of at-risk revenue) | reasons: {p['reason_mix']}")
        for c in p["top_lapsed_categories"]:
            print(f"{'':26s}• {c['category']}: {c['dropped_rate']:.0%} of its {c['regular_buyers']} regular buyers "
                  f"dropped it vs {c['healthy_rate']:.0%} of healthy {p['tier'].lower()} buyers ({c['lift']}×)")
        print()


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--models", default="models")
    ap.add_argument("--as-of", default="2017-12-31")
    a = ap.parse_args()
    main(a.data, a.models, a.as_of)