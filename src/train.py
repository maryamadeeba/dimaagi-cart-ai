"""Train the Dimaagi Cart churn model.  Run from the project root:
    python -m src.train --data data/raw --out models
    python -m src.train --data data/raw --out models --no-marketing   # behaviour-only model for imported stores
"""
import argparse, json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

from src.features import build_features, NON_MODEL_COLS
from src.labels import make_labels
from src.console import utf8_console

HORIZON_DAYS = 61
MIN_PRE_HISTORY_DAYS = 56       # 8 weeks of shopping before the oldest cutoff
DEMO_COLS = ["age", "income_band", "household_size", "kids_count",
             "marital_status", "home_ownership", "demo_unknown"]
# Campaign, coupon and discount signals. Imported stores don't have this data, so the behaviour-only model
# (--no-marketing) leaves them out instead of feeding it zeros.
MARKETING_COLS = ["ever_targeted", "campaigns_per_week", "type_a_per_week", "coupons_per_week", "discount_share"]
BEHAVIOUR_SUFFIX = "_behaviour"     # churn_model_behaviour.pkl, feature_columns_behaviour.json, metrics_behaviour.json
PARAMS = dict(n_estimators=400, max_depth=2, learning_rate=0.03, min_child_weight=10,
              subsample=0.8, colsample_bytree=0.7, reg_lambda=5,
              eval_metric="logloss", random_state=42)


def load_data(data_dir):
    d = Path(data_dir)
    tx = pd.read_csv(d / "transactions.csv", parse_dates=["transaction_timestamp"])
    tables = {name: pd.read_csv(d / f"{name}.csv") for name in
              ["products", "demographics", "campaigns", "campaign_descriptions", "coupon_redemptions"]}
    return tx, tables


def auto_cutoffs(tx, n=3, step_months=2):
    """The latest cutoff that still has a full outcome window, plus earlier ones."""
    last = tx["transaction_timestamp"].max().normalize() - pd.Timedelta(days=HORIZON_DAYS)
    return [last - pd.DateOffset(months=step_months * i) for i in reversed(range(n))]


def make_X(df, marketing=True):
    drop = ["household_id", "silent_churn", "cutoff"] + NON_MODEL_COLS + DEMO_COLS
    if not marketing:
        drop += MARKETING_COLS
    X = df.drop(columns=[c for c in drop if c in df.columns])
    return X.replace([np.inf, -np.inf], np.nan).fillna(0)


def capture_rates(y, scores, shares=(0.1, 0.2, 0.3)):
    """Share of all at-risk customers found by contacting the top 10/20/30% ranked by `scores`."""
    order = np.argsort(-np.asarray(scores, dtype=float), kind="stable")
    y = np.asarray(y)[order]
    return {f"{int(s * 100)}%": round(float(y[:int(round(s * len(y)))].sum() / y.sum()), 3) for s in shares}


def build_snapshots(tx, t, cutoffs):
    snaps = []
    for c in cutoffs:
        lab = make_labels(tx, c, horizon_days=HORIZON_DAYS)
        fe = build_features(tx, t["products"], t["demographics"], t["campaigns"],
                            t["campaign_descriptions"], t["coupon_redemptions"], c)
        s = lab[["household_id", "silent_churn"]].merge(fe, on="household_id", how="left")
        s["cutoff"] = c
        snaps.append(s)
    return pd.concat(snaps, ignore_index=True)


def training_history(tx):
    """Is there enough history to train? The code needs a full 61-day outcome window after the newest cutoff,
    three cutoffs 2 months apart, and 8 weeks of shopping before the oldest cutoff (the 8-week trend features).
    That is 61 days + 4 calendar months + 56 days: about 240 days, depending on month lengths."""
    first, last = tx["transaction_timestamp"].min(), tx["transaction_timestamp"].max()
    cutoffs = auto_cutoffs(tx)
    pre_days = (cutoffs[0] - first).days
    needed = (last.normalize() - cutoffs[0]).days + MIN_PRE_HISTORY_DAYS
    return {"ok": pre_days >= MIN_PRE_HISTORY_DAYS, "days": (last - first).days, "needed_days": needed,
            "cutoffs": [str(c.date()) for c in cutoffs]}


def evaluate(model, columns, X, y):
    """ROC-AUC, PR-AUC and capture rates of a saved model on a test set (missing features count as 0)."""
    p = model.predict_proba(X.reindex(columns=columns, fill_value=0))[:, 1]
    return {"roc_auc": round(float(roc_auc_score(y, p)), 3), "pr_auc": round(float(average_precision_score(y, p)), 3),
            "capture": capture_rates(y, p)}


def honest_test(tx, t, marketing=True):
    """Train on the older snapshots and test on the newest: the same split for every model we compare."""
    cutoffs = auto_cutoffs(tx)
    print("Cutoffs:", [str(c.date()) for c in cutoffs])
    snap = build_snapshots(tx, t, cutoffs)
    X, y = make_X(snap, marketing), snap["silent_churn"]
    train, test = snap["cutoff"] < cutoffs[-1], snap["cutoff"] == cutoffs[-1]
    for name, mask in (("training", train), ("test", test)):
        if y[mask].nunique() < 2:
            raise ValueError(f"The {name} period has no customers who drifted away (or none who stayed), "
                             "so a model can't learn from it. More history or more customers are needed.")
    ratio = (y[train] == 0).sum() / (y[train] == 1).sum()
    m = XGBClassifier(scale_pos_weight=ratio, **PARAMS).fit(X[train], y[train])
    p = m.predict_proba(X[test])[:, 1]
    rule = roc_auc_score(y[test], X.loc[test, "recency_days"])
    metrics = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "cutoffs": [str(c.date()) for c in cutoffs],
        "data_from": str(tx["transaction_timestamp"].min().date()),
        "data_to": str(tx["transaction_timestamp"].max().date()),
        "households": int(tx["household_id"].nunique()),
        "test_customers": int(test.sum()),
        "test_roc_auc": round(float(roc_auc_score(y[test], p)), 3),
        "test_pr_auc": round(float(average_precision_score(y[test], p)), 3),
        "baseline_rule_roc_auc": round(float(rule), 3),
        "test_at_risk_rate": round(float(y[test].mean()), 3),
        "n_features": int(X.shape[1]),
        "marketing_features": marketing,
        "capture": {"model": capture_rates(y[test], p),
                    "recency_rule": capture_rates(y[test], X.loc[test, "recency_days"]),
                    "random": {k: float(k.rstrip("%")) / 100 for k in ("10%", "20%", "30%")}},
    }
    print(json.dumps(metrics, indent=2))
    return {"metrics": metrics, "X": X, "y": y, "test": test}


def fit_final(X, y):
    """Final model: retrain on ALL snapshots, so it learns from the newest data too."""
    ratio_all = (y == 0).sum() / (y == 1).sum()
    return XGBClassifier(scale_pos_weight=ratio_all, **PARAMS).fit(X, y)


def save_model(model, columns, metrics, out_dir, suffix=""):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / f"churn_model{suffix}.pkl")
    (out / f"feature_columns{suffix}.json").write_text(json.dumps(list(columns)))
    (out / f"metrics{suffix}.json").write_text(json.dumps(metrics, indent=2))
    print(f"Saved model + metrics to {out}/")


def main(data_dir, out_dir, metrics_only=False, marketing=True):
    tx, t = load_data(data_dir)
    r = honest_test(tx, t, marketing)
    metrics = r["metrics"]
    suffix = "" if marketing else BEHAVIOUR_SUFFIX
    if metrics_only:          # refresh test metrics in an existing metrics.json without replacing the model
        path = Path(out_dir) / f"metrics{suffix}.json"
        saved = json.loads(path.read_text()) if path.exists() else {}
        keep = {k: v for k, v in metrics.items() if k != "trained_at"}
        path.write_text(json.dumps({**saved, **keep}, indent=2))
        print(f"Updated test metrics in {path}")
        return metrics
    save_model(fit_final(r["X"], r["y"]), r["X"].columns, metrics, out_dir, suffix)
    return metrics


if __name__ == "__main__":
    utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--out", default="models")
    ap.add_argument("--metrics-only", action="store_true", help="only recompute test metrics (keeps the model)")
    ap.add_argument("--no-marketing", action="store_true",
                    help="leave out campaign, coupon and discount features (saved as *_behaviour files)")
    a = ap.parse_args()
    main(a.data, a.out, a.metrics_only, marketing=not a.no_marketing)
    