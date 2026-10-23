import pandas as pd


def make_labels(tx, cutoff, horizon_days=61, min_trips=5, drop=0.5):
    """Silent churn label.

    A regular customer (min_trips+ trips on or before the cutoff) is labelled 1
    if their average weekly spend in the `horizon_days` after the cutoff falls
    by `drop` (50%) or more compared with their weekly spend before the cutoff.
    Customers who stop shopping entirely are included (their spend is 0).
    """
    ts = tx["transaction_timestamp"]
    before = tx[ts <= cutoff]
    after  = tx[(ts > cutoff) & (ts <= cutoff + pd.Timedelta(days=horizon_days))]

    # Only regular customers
    trips = before.groupby("household_id")["basket_id"].nunique()
    regulars = trips[trips >= min_trips].index

    # Average weekly spend before vs. after the cutoff
    weeks_before = (cutoff - before["transaction_timestamp"].min()).days / 7
    weekly_before = (before.groupby("household_id")["sales_value"].sum()
                           .reindex(regulars) / weeks_before)
    weekly_after = (after.groupby("household_id")["sales_value"].sum()
                         .reindex(regulars, fill_value=0) / (horizon_days / 7))

    out = pd.DataFrame({
        "household_id": regulars,
        "spend_ratio": (weekly_after / weekly_before).values,
    })
    out["silent_churn"] = (out["spend_ratio"] < drop).astype(int)
    return out