"""`dimaagi-backend --self-check`: prove a (packaged) backend has everything it needs, without touching user data.
Imports the runtime stack, loads the shipped model, runs one SHAP explanation, does an in-memory ChromaDB round
trip and reports the keyring backend. Prints one JSON report; exit code 1 if anything failed."""
import importlib
import json
import sys
import traceback


def _check(report, name, fn):
    try:
        report[name] = {"ok": True, **(fn() or {})}
    except Exception as e:  # report every failure, keep checking the rest
        report[name] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                        "where": traceback.format_exc(limit=2).splitlines()[-2:]}


def run():
    import os
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    from src.api import VERSION, config
    report = {"version": VERSION, "frozen": config.is_frozen(), "bundle": str(config.bundle_dir())}

    def imports():
        mods = ["fastapi", "uvicorn", "multipart", "pydantic", "keyring", "yaml", "pandas", "numpy", "pyarrow",
                "openpyxl", "sklearn", "xgboost", "shap", "joblib", "chromadb", "fastembed", "onnxruntime",
                "tokenizers", "rank_bm25", "pypdf", "google.genai", "src.rag.assistant", "src.rag.campaign",
                "src.rag.generate", "src.rag.ingest_reviews", "src.rag.ingest_trends", "src.rag.build_index",
                "src.train", "src.segments"]
        return {"versions": {m: getattr(importlib.import_module(m), "__version__", "") for m in mods}}

    def model():
        import joblib
        import numpy as np
        import pandas as pd
        import shap
        d = config.bundle_dir()
        cols = json.loads((d / "models/feature_columns.json").read_text())
        m = joblib.load(d / "models/churn_model.pkl")
        X = pd.DataFrame(np.zeros((1, len(cols))), columns=cols)
        p = float(m.predict_proba(X)[0, 1])
        sv = shap.TreeExplainer(m)(X).values
        return {"features": len(cols), "risk_of_all_zero_customer": round(p, 3), "shap_shape": list(sv.shape)}

    def chroma():
        import chromadb
        client = chromadb.EphemeralClient()
        col = client.get_or_create_collection("selfcheck")
        col.add(ids=["a", "b"], embeddings=[[1.0, 0.0], [0.0, 1.0]], documents=["milk", "bread"])
        hit = col.query(query_embeddings=[[0.9, 0.1]], n_results=1)["documents"][0][0]
        return {"nearest": hit}

    def onnx():
        import onnxruntime
        return {"providers": onnxruntime.get_available_providers()}

    def keyring_backend():
        import keyring
        kr = keyring.get_keyring()
        name = f"{type(kr).__module__}.{type(kr).__name__}"
        if "fail" in name.lower() or "null" in name.lower():
            raise RuntimeError(f"no usable keyring backend ({name})")
        return {"backend": name}

    def defaults():
        d = config.bundle_dir()
        missing = [f for f in config.SEED_FILES if not (d / f).exists()]
        if missing:
            raise RuntimeError(f"missing shipped files: {missing}")
        return {"files": len(config.SEED_FILES)}

    for name, fn in [("imports", imports), ("shipped_files", defaults), ("model_and_shap", model),
                     ("chromadb", chroma), ("onnxruntime", onnx), ("keyring", keyring_backend)]:
        _check(report, name, fn)
    ok = all(v["ok"] for v in report.values() if isinstance(v, dict) and "ok" in v)
    report["ok"] = ok
    print(json.dumps(report, indent=2), flush=True)
    sys.exit(0 if ok else 1)
