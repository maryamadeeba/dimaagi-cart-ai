"""Background jobs: retrain from an uploaded CSV, and build the knowledge bases from the user's own files.
Each job runs the existing pipeline code step by step in a thread; one job at a time."""
import contextlib
import io
import json
import shutil
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd


# Tables src.train.load_data reads besides transactions and products. An imported store has none of them:
# they are written empty, so the marketing features they drive are 0 (flagged in the app).
TABLE_COLUMNS = {
    "demographics": ["household_id", "age", "income", "home_ownership", "marital_status",
                     "household_size", "household_comp", "kids_count"],
    "campaigns": ["campaign_id", "household_id"],
    "campaign_descriptions": ["campaign_id", "campaign_type", "start_date", "end_date"],
    "coupon_redemptions": ["household_id", "coupon_upc", "campaign_id", "redemption_date"],
}
UPLOADS = Path("uploads")
LOG_LINES = 200


class JobBusy(Exception):
    pass


class StepFailed(Exception):
    pass


class Job:
    def __init__(self, kind, steps):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "running"
        self.steps = [{"key": k, "label": label, "status": "pending", "detail": ""} for k, label in steps]
        self.error = None
        self.log = []
        self.started, self.finished = time.time(), None
        self.result = {}

    def step(self, key):
        return next(s for s in self.steps if s["key"] == key)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "steps": self.steps,
                "error": self.error, "log": self.log[-40:], "result": self.result,
                "seconds": round((self.finished or time.time()) - self.started, 1)}


class _LogWriter(io.TextIOBase):
    """Sends the pipeline's print() output to the job log (and still to the console)."""
    def __init__(self, job, echo):
        self.job, self.echo, self.buf = job, echo, ""

    def write(self, s):
        if self.echo:
            try:
                self.echo.write(s)
            except Exception:
                pass
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.job.log = (self.job.log + [line.rstrip()])[-LOG_LINES:]
        return len(s)


class JobManager:
    def __init__(self):
        self.jobs, self.lock = {}, threading.Lock()

    def running(self):
        return next((j for j in self.jobs.values() if j.status == "running"), None)

    def start(self, kind, steps, fn, *args):
        with self.lock:
            if self.running():
                raise JobBusy(f"A {self.running().kind} job is already running.")
            job = Job(kind, steps)
            self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, fn, args), daemon=True).start()
        return job

    def _run(self, job, fn, args):
        writer = _LogWriter(job, sys.__stdout__)
        try:
            with contextlib.redirect_stdout(writer):
                fn(job, *args)
            job.status = "done"
        except BaseException as e:                      # the pipelines raise SystemExit on quota stops
            job.status = "error"
            job.error = str(e) or e.__class__.__name__
            for s in job.steps:
                if s["status"] == "running":
                    s["status"], s["detail"] = "error", job.error
            if not isinstance(e, (StepFailed, SystemExit)):
                job.log.append(traceback.format_exc(limit=3))
        finally:
            job.finished = time.time()
            reset_caches()

    def get(self, job_id):
        return self.jobs.get(job_id)


@contextlib.contextmanager
def run_step(job, key):
    s = job.step(key)
    s["status"] = "running"
    yield s
    if s["status"] == "running":
        s["status"] = "done"


def skip(job, key, why):
    job.step(key).update(status="skipped", detail=why)


def reset_caches():
    """Drop in-memory search indexes so rebuilt knowledge bases are picked up."""
    if "src.rag.retriever" in sys.modules:
        sys.modules["src.rag.retriever"]._collections.clear()
    if "src.rag.hybrid" in sys.modules:
        sys.modules["src.rag.hybrid"]._bm25 = None


# ---------- import a store and score it ----------
def import_steps(mode):
    model = ("model", "Use the pre-trained model") if mode == "pretrained" else             ("model", "Train on your data and compare with the pre-trained model")
    return [("convert", "Convert your data"), model, ("score", "Score customers and refresh segments")]


def choose_model(store_eval, pretrained_eval):
    """Champion/challenger on the same newest-period test set: keep the model with the higher ROC-AUC
    (the store's own model wins ties, since it was trained on this store)."""
    return "store" if store_eval["roc_auc"] >= pretrained_eval["roc_auc"] else "pretrained"


def write_inputs(folder, tx, products):
    folder.mkdir(parents=True, exist_ok=True)
    tx.to_csv(folder / "transactions.csv", index=False)
    products.to_csv(folder / "products.csv", index=False)
    for name, cols in TABLE_COLUMNS.items():
        pd.DataFrame(columns=cols).to_csv(folder / f"{name}.csv", index=False)


def import_store(job, slug, df, category_map, mode):
    import joblib
    from src import segments, train
    from src.api import importer, stores

    stores.require_writable(slug)
    folder, models = stores.root(slug) / "input", stores.root(slug) / "models"
    with run_step(job, "convert") as s:
        tx, products = importer.convert(df, category_map)
        write_inputs(folder, tx, products)
        s["detail"] = f"{len(tx):,} purchases from {tx['household_id'].nunique():,} customers"

    with run_step(job, "model") as s:
        shipped = stores.root(stores.DEMO) / "models"
        pretrained_metrics = json.loads((shipped / f"metrics{stores.PRETRAINED}.json").read_text())
        store_data = {"from": str(tx["transaction_timestamp"].min().date()),
                      "to": str(tx["transaction_timestamp"].max().date()),
                      "households": int(tx["household_id"].nunique())}
        if mode == "pretrained":
            stores.copy_pretrained(slug)
            metrics = {**pretrained_metrics, "source": "pretrained", "store_data": store_data}
            (models / "metrics.json").write_text(json.dumps(metrics, indent=2))
            s["detail"] = "Pre-trained behaviour-only model copied (trained on a US grocery chain, 2017)"
        else:
            tx_, t = train.load_data(folder)
            history = train.training_history(tx_)
            if not history["ok"]:
                raise StepFailed(f"Training needs about {history['needed_days']} days of history; "
                                 f"this file has {history['days']}.")
            try:
                r = train.honest_test(tx_, t, marketing=False)     # imported stores have no marketing data
            except ValueError as e:
                raise StepFailed(str(e))
            m, test = r["metrics"], r["test"]
            pre_model = joblib.load(shipped / f"churn_model{stores.PRETRAINED}.pkl")
            pre_cols = json.loads((shipped / f"feature_columns{stores.PRETRAINED}.json").read_text())
            store_eval = {"roc_auc": m["test_roc_auc"], "pr_auc": m["test_pr_auc"], "capture": m["capture"]["model"]}
            pre_eval = train.evaluate(pre_model, pre_cols, r["X"][test], r["y"][test])
            kept = choose_model(store_eval, pre_eval)
            comparison = {"kept": kept, "store_model": store_eval, "pretrained_model": pre_eval,
                          "recency_rule_roc_auc": m["baseline_rule_roc_auc"], "test_customers": m["test_customers"],
                          "test_period_from": m["cutoffs"][-1]}
            if kept == "store":
                train.save_model(train.fit_final(r["X"], r["y"]), r["X"].columns,
                                 {**m, "source": "store", "store_data": store_data, "comparison": comparison}, models)
            else:
                stores.copy_pretrained(slug)
                (models / "metrics.json").write_text(json.dumps(
                    {**pretrained_metrics, "source": "pretrained", "store_data": store_data,
                     "comparison": comparison}, indent=2))
            s["detail"] = (f"Your model ROC-AUC {store_eval['roc_auc']} vs pre-trained {pre_eval['roc_auc']} "
                           f"on your newest customers: kept the {'model trained on your data' if kept == 'store' else 'pre-trained model'}")
        job.result["model"] = "store" if mode != "pretrained" and kept == "store" else "pretrained"

    with run_step(job, "score") as s:
        segments.main(str(folder), str(models), None)
        segs = json.loads((models / "segments.json").read_text())["segments"]
        small = [x["segment"] for x in segs if x["customers"] < importer.MIN_SEGMENT]
        s["detail"] = f"{sum(x['customers'] for x in segs):,} at-risk customers in {len(segs)} segments"
        job.result["small_segments"] = small
    stores.write_meta(slug, category_map=category_map, mode=mode, scored_with=job.result["model"],
                      scored_at=datetime.now().isoformat(timespec="seconds"), store_data=store_data,
                      marketing_available=False)
    stores.activate(slug)


# ---------- rewrite reasons and kits (Gemini) ----------
REGEN_STEPS = [("reasons", "Rewrite reasons"), ("kits", "Rewrite campaign kits")]


def regenerate(job, segment_names, what, fresh):
    """Rerun src.rag.generate / src.rag.campaign for some segments (None = all) of the active store."""
    from src.api import stores
    generate, campaign = stores.mod("src.rag.generate"), stores.mod("src.rag.campaign")
    flags = ["--fresh"] if fresh else []
    targets = segment_names or [None]
    if what in ("reasons", "both"):
        with run_step(job, "reasons") as s:
            for name in targets:
                generate.main((["--segment", name] if name else []) + flags)
            s["detail"] = "Cited reasons saved"
    else:
        skip(job, "reasons", "Not requested")
    if what in ("kit", "both"):
        with run_step(job, "kits") as s:
            for name in targets:
                campaign.main((["--segment", name] if name else []) + flags)
            s["detail"] = "Campaign kits saved and checked"
    else:
        skip(job, "kits", "Not requested")


# ---------- knowledge bases ----------
REVIEWS_STEPS = [("check", "Find the Yelp files"), ("ingest", "Pick grocery reviews and tag them"),
                 ("embed", "Embed reviews on this computer"), ("bm25", "Build the keyword index")]
TRENDS_STEPS = [("check", "Find the report PDFs"), ("index", "Chunk, embed and index the reports")]
YELP_FILES = ["yelp_academic_dataset_business.json", "yelp_academic_dataset_review.json"]


def check_source(kind, source):
    src = Path(source).expanduser()
    if not src.is_dir():
        raise StepFailed(f"Folder not found: {src}")
    if kind == "reviews":
        missing = [f for f in YELP_FILES if not (src / f).exists()]
        if missing:
            raise StepFailed(f"This folder is missing {', '.join(missing)} from the Yelp Open Dataset.")
        return src, "Yelp business and review files found"
    pdfs = list(src.glob("*.pdf"))
    if not pdfs:
        raise StepFailed("No PDF files in this folder.")
    if not Path("config/trend_sources.csv").exists():
        raise StepFailed("config/trend_sources.csv is missing from the data folder.")
    return src, f"{len(pdfs)} PDFs found"


def build_reviews(job, source):
    from src.rag import build_index, hybrid, ingest_reviews, llm
    with run_step(job, "check") as s:
        src, s["detail"] = check_source("reviews", source)
    with run_step(job, "ingest") as s:
        ingest_reviews.main(str(src), "data/processed/reviews.parquet", "config/niche.yaml")
        s["detail"] = "Grocery reviews saved on this computer"
    with run_step(job, "embed") as s:
        sleep = 0.0 if llm.EMBED_BACKEND == "local" else 1.0
        build_index.main("data/processed/reviews.parquet", "data/processed/emb_cache", "data/vectorstore",
                         100, sleep, None)
        s["detail"] = "Reviews searchable"
    with run_step(job, "bm25") as s:
        reset_caches()
        s["detail"] = f"{hybrid.load_bm25()['n']:,} reviews indexed"


def build_trends(job, source):
    from src.rag import ingest_trends
    with run_step(job, "check") as s:
        src, s["detail"] = check_source("trends", source)
    with run_step(job, "index") as s:
        ingest_trends.main(src)
        s["detail"] = "Report pages searchable"
