"""Check the packaged backend (dist/dimaagi-backend) before it goes into the installer.

  python packaging/verify_backend.py                     # uses dist/dimaagi-backend
  python packaging/verify_backend.py path/to/dimaagi-backend

1. Licensing: nothing from data/ (Yelp reviews, trend PDFs/chunks, vector store, caches), no .env, no outputs that
   quote reviews; the shipped defaults are exactly the allowed files.
2. --self-check: imports, model + SHAP, ChromaDB, onnxruntime and the keyring backend work in the frozen build.
3. First run: start the exe with an empty data folder and check it copies the shipped files there, answers
   /api/health (timed), rejects a missing token, and serves the dashboard, the model card and the front end.
Never touches %APPDATA%\\DimaagiCart (or the legacy %APPDATA%\\WinBack) or the owner's saved keys: the backend is
pointed at throwaway Credential Manager entries, removed afterwards.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.api.config import SEED_FILES  # noqa: E402  (the ship list)

ALLOWED_DEFAULTS = set(SEED_FILES)
FORBIDDEN = ["yelp", "vectorstore", "reviews.parquet", "why_summaries", "campaign_kits", "spotcheck", "bm25_reviews",
             "gen_cache", "emb_cache", "chroma.sqlite3", "knowledge"]
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""), flush=True)


def size_mb(folder):
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1e6


def licensing(dist):
    files = [f.relative_to(dist).as_posix() for f in dist.rglob("*") if f.is_file()]
    bad = [f for f in files if any(word in f.lower() for word in FORBIDDEN)
           or Path(f).name == ".env" or f.lower().endswith(".pdf")]
    check("no review text, trend reports, vector store, caches or .env", not bad, ", ".join(bad[:10]))
    defaults = {f.split("defaults/", 1)[1] for f in files if "/defaults/" in f or f.startswith("defaults/")}
    check("shipped defaults are exactly the allowed files", defaults == ALLOWED_DEFAULTS,
          f"extra {sorted(defaults - ALLOWED_DEFAULTS)}, missing {sorted(ALLOWED_DEFAULTS - defaults)}")


def get(port, path, token=None, timeout=10):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"X-Dimaagi-Token": token} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def first_run(exe):
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "DimaagiCart"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        token = "verify-" + os.urandom(8).hex()
        service = f"DimaagiCart-verify-{os.urandom(4).hex()}"           # throwaway Credential Manager entries
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("DIMAAGI_", "WINBACK_")) and k != "GEMINI_API_KEY"}   # WINBACK_: legacy aliases
        env.update({"DIMAAGI_DATA_DIR": str(data), "DIMAAGI_TOKEN": token, "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1", "DIMAAGI_KEYRING_SERVICE": service,
                    "DIMAAGI_LEGACY_KEYRING_SERVICE": service + "-legacy"})
        args = [str(exe), "--port", str(port)]
        static = ROOT / "frontend" / "dist"
        if static.exists():
            args += ["--static", str(static)]
        start = time.time()
        proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            ready = None
            while time.time() - start < 120 and proc.poll() is None:
                try:
                    if get(port, "/api/health", token)[0] == 200:
                        ready = time.time() - start
                        break
                except OSError:
                    pass
                time.sleep(0.3)
            check("starts and answers /api/health", ready is not None,
                  f"{ready:.1f}s" if ready else f"exit code {proc.poll()}")
            if ready is None:
                print(proc.stdout.read().decode("utf-8", "replace")[-2000:] if proc.poll() is not None else "")
                return
            seeded = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file()
                            and p.relative_to(data).as_posix() in ALLOWED_DEFAULTS)
            check("first run copies the shipped files into the data folder", set(seeded) == ALLOWED_DEFAULTS,
                  f"{len(seeded)}/{len(ALLOWED_DEFAULTS)} files in {data.name}")
            check("rejects a request without the token", get(port, "/api/health")[0] == 401)
            health = json.loads(get(port, "/api/health", token)[1])
            check("health shape", {"status", "version", "kb", "outputs"} <= set(health) and health["status"] == "ok",
                  f"version {health.get('version')}, kb {health.get('kb')}")
            code, body = get(port, "/api/dashboard", token, timeout=90)       # first call imports the ML stack
            dash = json.loads(body) if code == 200 else {}
            check("dashboard from the shipped segments", code == 200 and dash["totals"]["customers"] > 0,
                  f"{dash.get('totals')}")
            code, body = get(port, "/api/model", token)
            card = json.loads(body) if code == 200 else {}
            check("model card, with both pre-trained models", code == 200 and card.get("roc_auc") is not None
                  and set(card.get("pretrained_models", {})) == {"full", "behaviour"})
            code, body = get(port, "/api/customers?page_size=5", token, timeout=60)
            cust = json.loads(body) if code == 200 else {}
            check("demo Customers list returns rows", code == 200 and len(cust.get("rows", [])) == 5,
                  f"{cust.get('all')} customers, top risk {cust['rows'][0]['risk'] if cust.get('rows') else '-'}")
            if cust.get("rows"):
                code, body = get(port, f"/api/customers/{cust['rows'][0]['id']}", token)
                check("customer drawer has 3 SHAP drivers", code == 200 and len(json.loads(body)["drivers"]) == 3)
            code, body = get(port, "/api/segments/highvalue/reasons", token)
            check("reasons ask for setup (not shipped)", code == 404 and json.loads(body).get("what") == "why")
            if static.exists():
                code, body = get(port, "/")
                check("serves the front end", code == 200 and b"<div id=\"root\">" in body)
        finally:
            subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"], capture_output=True)
            proc.wait(timeout=10)
            forget_service(service)


def forget_service(service):
    """Remove the throwaway entries the backend wrote (the key-migration marker)."""
    import keyring
    from keyring.errors import KeyringError
    for user in ("gemini_api_key", "legacy_key_checked"):
        try:
            keyring.delete_password(service, user)
        except KeyringError:
            pass


def main():
    dist = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "dimaagi-backend"
    exe = dist / "dimaagi-backend.exe"
    if not exe.exists():
        sys.exit(f"{exe} not found. Build it first: .venv\\Scripts\\pyinstaller dimaagi-backend.spec --noconfirm")
    print(f"Checking {dist} ({size_mb(dist):,.0f} MB)\n")
    licensing(dist)
    r = subprocess.run([str(exe), "--self-check"], capture_output=True, timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = r.stdout.decode("utf-8", "replace")
    try:
        report = json.loads(out[out.index("{"):])
        for k, v in report.items():
            if isinstance(v, dict) and "ok" in v:
                detail = v.get("error") or {kk: vv for kk, vv in v.items() if kk not in ("ok", "versions")}
                check(f"self-check: {k}", v["ok"], str(detail))
    except ValueError:
        check("self-check ran", False, (out + r.stderr.decode("utf-8", "replace"))[-1500:])
    first_run(exe)
    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
