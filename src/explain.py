"""Turn each customer's SHAP values into their top drivers, in plain English. No LLM: fixed phrases per feature."""
DEPT_NAMES = {"grocery": "grocery", "drug_gm": "drugstore and general goods", "fuel": "fuel", "produce": "fresh produce",
              "meat": "fresh meat", "meat_pckgd": "packaged meat", "deli": "deli"}
STAPLES_TEXT = "staples (milk, bread, cheese, cereal, eggs)"
MARKETING = ["ever_targeted", "campaigns_per_week", "type_a_per_week", "coupons_per_week", "discount_share"]


def _pct(v):
    return f"{v * 100:.0f}%"


def _trend(v, what, window):
    """Ratio of recent to usual: 0.52 -> 'Spending 48% less than usual over the last 4 weeks'."""
    if v <= 0.005:
        return f"{what[0]} stopped completely in the last {window}"
    change = (1 - v) * 100
    if abs(change) < 5:
        return f"{what[1]} about as usual over the last {window}"
    return f"{what[1]} {abs(change):.0f}% {'less' if change > 0 else 'more'} than usual over the last {window}"


SPEND = ("Spending", "Spending")
TRIPS = ("Visits", "Visiting")
PHRASES = {
    "recency_days": lambda v: f"{v:.0f} days since the last visit",
    "avg_basket": lambda v: f"Average basket of ${v:,.2f}",
    "trips_per_week": lambda v: f"{v:.1f} trips a week on average",
    "spend_per_week": lambda v: f"Usually spends ${v:,.2f} a week",
    "avg_gap_days": lambda v: ("Often makes several trips on the same day" if v < 1
                               else f"{v:.0f} days between visits on average"),
    "max_gap_days": lambda v: f"Longest gap between visits: {v:.0f} days",
    "trips_last_8w": lambda v: f"{v:.0f} trips in the last 8 weeks",
    "spend_last_8w_per_week": lambda v: f"${v:,.2f} a week over the last 8 weeks",
    "spend_trend": lambda v: _trend(v, SPEND, "8 weeks"),
    "trips_last_4w": lambda v: f"{v:.0f} trips in the last 4 weeks",
    "spend_last_4w_per_week": lambda v: f"${v:,.2f} a week over the last 4 weeks",
    "spend_trend_4w": lambda v: _trend(v, SPEND, "4 weeks"),
    "trip_trend_4w": lambda v: _trend(v, TRIPS, "4 weeks"),
    "active_week_share": lambda v: f"Shopped in {_pct(v)} of weeks",
    "discount_share": lambda v: f"{_pct(v)} of spend came from discounts",
    "n_stores": lambda v: f"Shops at {v:.0f} of your stores",
    "n_departments": lambda v: f"Buys from {v:.0f} departments",
    "staples_share": lambda v: f"{STAPLES_TEXT[0].upper()}{STAPLES_TEXT[1:]} are {_pct(v)} of spend",
    "days_since_staple": lambda v: (f"No {STAPLES_TEXT} bought yet" if v >= 365
                                    else f"{v:.0f} days since buying {STAPLES_TEXT}"),
    "ever_targeted": lambda v: "Has received your campaigns" if v else "Has never received a campaign",
    "campaigns_per_week": lambda v: f"{v:.2f} campaigns received a week",
    "type_a_per_week": lambda v: f"{v:.2f} Type A campaigns received a week",
    "coupons_per_week": lambda v: "Has never redeemed a coupon" if v == 0 else f"Redeems {v:.2f} coupons a week",
}
for _key, _name in DEPT_NAMES.items():
    PHRASES[f"share_{_key}"] = (lambda name: lambda v: f"{_pct(v)} of spend on {name}")(_name)

# For the model card: what each of the 30 features means, grouped like the README's feature table
GROUPS = {
    "Recency and frequency": ["recency_days", "trips_per_week", "avg_gap_days", "max_gap_days", "active_week_share",
                              "n_stores"],
    "Recent trends": ["trips_last_8w", "spend_last_8w_per_week", "spend_trend", "trips_last_4w",
                      "spend_last_4w_per_week", "spend_trend_4w", "trip_trend_4w"],
    "Spend": ["avg_basket", "spend_per_week", "discount_share"],
    "Basket mix": [f"share_{k}" for k in DEPT_NAMES] + ["n_departments", "staples_share", "days_since_staple"],
    "Marketing": ["ever_targeted", "campaigns_per_week", "type_a_per_week", "coupons_per_week"],
}
LABELS = {
    "recency_days": "Days since the last visit", "trips_per_week": "Trips per week", "avg_gap_days": "Average gap between visits",
    "max_gap_days": "Longest gap between visits", "active_week_share": "Share of weeks with a visit",
    "n_stores": "Number of your stores visited", "trips_last_8w": "Trips in the last 8 weeks",
    "spend_last_8w_per_week": "Weekly spend, last 8 weeks", "spend_trend": "Spend trend, 8 weeks vs usual",
    "trips_last_4w": "Trips in the last 4 weeks", "spend_last_4w_per_week": "Weekly spend, last 4 weeks",
    "spend_trend_4w": "Spend trend, 4 weeks vs usual", "trip_trend_4w": "Visit trend, 4 weeks vs usual",
    "avg_basket": "Average basket value", "spend_per_week": "Usual weekly spend", "discount_share": "Share of spend on discounts",
    "n_departments": "Number of departments bought from", "staples_share": "Staples share of spend",
    "days_since_staple": "Days since buying staples", "ever_targeted": "Ever received a campaign",
    "campaigns_per_week": "Campaigns received per week", "type_a_per_week": "Type A campaigns per week",
    "coupons_per_week": "Coupons redeemed per week",
    **{f"share_{k}": f"Share of spend: {v}" for k, v in DEPT_NAMES.items()},
}


def phrase(feature, value):
    fn = PHRASES.get(feature)
    return fn(float(value)) if fn else f"{LABELS.get(feature, feature)}: {value:.2f}"


def top_drivers(X, shap_values, k=3):
    """For each row: the k features that moved the risk most, with direction and size (SHAP, log-odds)."""
    cols = list(X.columns)
    out = []
    for row, sv in zip(X.itertuples(index=False), shap_values):
        idx = sorted(range(len(cols)), key=lambda i: -abs(sv[i]))[:k]
        out.append([{"feature": cols[i], "value": round(float(row[i]), 4), "phrase": phrase(cols[i], row[i]),
                     "shap": round(float(sv[i]), 3), "direction": "raises risk" if sv[i] > 0 else "lowers risk"}
                    for i in idx])
    return out


def features_used(columns, marketing_available=True):
    """The model card's feature list, grouped, with marketing features flagged when the store has no campaign data."""
    groups = []
    for group, feats in GROUPS.items():
        items = [{"feature": f, "label": LABELS.get(f, f),
                  "unavailable": (not marketing_available) and f in MARKETING} for f in feats if f in columns]
        if items:
            groups.append({"group": group, "features": items})
    return groups
