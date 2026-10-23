"""Dimaagi Cart local backend. Listens on 127.0.0.1 only; every /api call must carry the launch token.

Run (dev):
  python -m src.api.app --port 8765 --token devtoken --dev      # --dev allows the Vite dev server origin
  python -m src.api.app                                         # free port + random token, both printed
Env: DIMAAGI_TOKEN (instead of --token), DIMAAGI_DATA_DIR (default: repo root in dev, %APPDATA%\\DimaagiCart packaged).
The legacy pre-0.3.2 names (WINBACK_TOKEN, WINBACK_DATA_DIR, ...) still work as deprecated aliases (see config.env).
"""
import argparse
import os
import re
import secrets
import shutil
import socket
import threading
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.api import VERSION, config, importer, jobs, stores, views
from src.console import utf8_console

TOKEN_HEADER = "X-Dimaagi-Token"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
MAX_CONVERSATIONS = 20
IMPORT_TYPES = (".csv", ".txt", ".xlsx", ".xlsm")


FILE_IN_LABEL = re.compile(r"\s*\(((?:models|data|config)/[^)]+)\)\s*$")


def owner_label(label):
    """'Campaign kit: Core · Visiting less (models/campaign_kits.md)' -> ('Campaign kit: Core · Visiting less',
    'models/campaign_kits.md'). Owners see the clean label; the file path stays for "How this was made"."""
    if not label:
        return label, None
    m = FILE_IN_LABEL.search(label)
    return (label[:m.start()], m.group(1)) if m else (label, None)


def error(status, code, message, **extra):
    return JSONResponse({"error": code, "message": message, **extra}, status_code=status)


# ---------- chat sessions ----------
class Conversations:
    """One Gemini chat + one assistant.Session per conversation_id. The assistant's tools write refs into the
    module-level assistant.SESSION, so turns run one at a time with that conversation's session swapped in."""
    def __init__(self):
        self.items, self.lock, self.client, self.client_key = OrderedDict(), threading.Lock(), None, None

    def _client(self, assistant):
        key = config.get_key()
        if self.client is None or self.client_key != key:
            os.environ["GEMINI_API_KEY"] = key
            self.client, self.client_key = assistant.make_client(), key
            self.items.clear()                       # chats belong to the old client
        return self.client

    def clear(self):
        with self.lock:
            self.items.clear()

    def ask(self, conversation_id, message):
        assistant = stores.mod("src.rag.assistant")      # tools read the active store's files
        stores.mod("src.rag.generate")
        with self.lock:
            client = self._client(assistant)
            conv = self.items.get(conversation_id)
            if conv is None or conv["model"] != assistant.CHAT_MODEL:
                conv = {"chat": assistant.make_chat(client), "session": assistant.Session(),
                        "model": assistant.CHAT_MODEL}
                self.items[conversation_id] = conv
                while len(self.items) > MAX_CONVERSATIONS:
                    self.items.popitem(last=False)
            self.items.move_to_end(conversation_id)
            before = set(conv["session"].refs)
            previous, assistant.SESSION = assistant.SESSION, conv["session"]
            try:
                result = assistant.ask(conv["chat"], message)
            finally:
                assistant.SESSION = previous
            refs = conv["session"].refs
        cited = [{"ref": c, "label": owner_label(refs[c]["label"])[0] if c in refs else None,
                  "valid": c not in result["invalid"]} for c in result["cited"]]
        invalid, ungrounded = result["invalid"], result["ungrounded_numbers"]
        how = {"model": conv["model"], "retrieval": assistant.CHAT_RETRIEVAL,
               "tool_calls": result.get("tool_args", []),
               "retrieved": [{"ref": r, "label": owner_label(refs[r]["label"])[0],
                              "file": owner_label(refs[r]["label"])[1]} for r in refs if r not in before],
               "model_seconds": result.get("model_seconds"), "tool_seconds": result.get("tool_seconds"),
               "checks": [{"name": "Citations come from a tool", "ok": not invalid,
                           "detail": f"{len(result['cited'])} cited, {len(invalid)} not from a source"},
                          {"name": "Numbers match the cited source", "ok": not ungrounded,
                           "detail": ", ".join(u["number"] for u in ungrounded) or "all numbers grounded"}]}
        return {"answer": result["answer"], "tools": result["tools"], "cited": cited,
                "validity": result["validity"], "ungrounded_numbers": ungrounded,
                "seconds": result["seconds"], "how": how}


class ChatIn(BaseModel):
    conversation_id: str
    message: str


class BuildKbIn(BaseModel):
    kind: str
    source_path: str


class ActivateIn(BaseModel):
    slug: str


class RegenerateIn(BaseModel):
    what: str = "both"          # reasons | kit | both


class AnalyzeIn(BaseModel):
    mapping: dict
    category_map: dict = {}
    store: str | None = None    # an existing store's slug: reuse its saved category matches


class RunImportIn(AnalyzeIn):
    store_name: str
    mode: str                   # pretrained | train


class SettingsIn(BaseModel):
    gemini_key: str | None = None
    clear_key: bool = False
    gemini_model: str | None = None
    chat_model: str | None = None


def create_app(token, dev=False, static_dir=None):
    app = FastAPI(title="Dimaagi Cart", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.jobs = jobs.JobManager()
    app.state.conversations = Conversations()
    imports = OrderedDict()                              # import_id -> {"path", "raw", "filename"} (last few only)

    # Middleware added later wraps earlier ones: host check -> CORS (dev only) -> token check -> routes
    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path.startswith("/api") and request.method != "OPTIONS":
            sent = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(sent.encode(), token.encode()):
                return error(401, "unauthorized", f"Missing or wrong {TOKEN_HEADER}.")
        return await call_next(request)

    if dev:
        app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET", "POST"],
                           allow_headers=[TOKEN_HEADER, "Content-Type"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.exception_handler(views.Missing)
    async def missing(_, e: views.Missing):
        return error(404, "missing_output", str(e), what=e.what)

    @app.exception_handler(views.UnknownSegment)
    async def unknown_segment(_, e: views.UnknownSegment):
        return error(404, "unknown_segment", str(e), available=e.available)

    # ---------- app state and stores ----------
    @app.get("/api/health")
    def health():
        out = views.outputs_status()
        app_settings = config.read_settings()
        return {"status": "ok", "version": VERSION, "kb": views.kb_status(),
                "outputs": {"why": out["why"], "kits": out["kits"], "segments": out["segments"],
                            "customers": out["customers"]},
                "has_key": bool(config.get_key()), "key_source": config.key_source(), "data_dir": str(Path.cwd()),
                "app": {"mode": app_settings.get("mode"), "active_store": stores.active(),
                        "store": views.store_meta(), "stores": stores.all_stores(),
                        "demo_label": stores.DEMO_LABEL}}

    @app.post("/api/stores/activate")
    def activate(body: ActivateIn):
        try:
            stores.activate(body.slug)
        except stores.StoreError as e:
            return error(404, "unknown_store", str(e))
        app.state.conversations.clear()                  # chats cite the old store's segments
        return {"active_store": stores.active(), "stores": stores.all_stores()}

    @app.post("/api/app/welcome")
    def show_welcome():
        config.write_settings(mode=None)
        return {"mode": None}

    # ---------- screens ----------
    @app.get("/api/dashboard")
    def dashboard():
        return views.dashboard()

    @app.get("/api/segments/{slug}/reasons")
    def reasons(slug: str):
        return views.reasons(slug)

    @app.get("/api/segments/{slug}/kit")
    def kit(slug: str):
        return views.kit(slug)

    @app.get("/api/customers")
    def customers(q: str = "", sort: str = "risk", desc: bool = True, page: int = 1, page_size: int = 50,
                  segment: str = "", at_risk: bool = False):
        return views.customers(q, sort, desc, page, page_size, segment, at_risk)

    @app.get("/api/customers/{customer_id}")
    def customer(customer_id: str):
        return views.customer(customer_id)

    @app.get("/api/model")
    def model_card():
        return views.model_card()

    # ---------- regenerate reasons and kits (uses Gemini) ----------
    def start_regenerate(names, what, fresh):
        if what not in ("reasons", "kit", "both"):
            return error(400, "bad_request", "what must be 'reasons', 'kit' or 'both'.")
        kb = views.kb_status()
        if not config.get_key():
            return error(400, "no_key", "Add your Gemini API key in AI settings first.")
        if not kb["reviews"]:
            return error(400, "no_kb", "Build the reviews knowledge base first (Retrain screen).")
        if what != "reasons" and not kb["trends"]:
            return error(400, "no_kb", "Build the marketing trends knowledge base first (Retrain screen).")
        if what == "kit" and not views.WHY.exists():
            return error(400, "no_reasons", "Write the reasons first: kits are built from them.")
        try:
            job = app.state.jobs.start("regenerate", jobs.REGEN_STEPS, jobs.regenerate, names, what, fresh)
        except jobs.JobBusy as e:
            return error(409, "busy", str(e))
        return job.to_dict()

    @app.post("/api/segments/{slug}/regenerate")
    def regenerate_segment(slug: str, body: RegenerateIn):
        name = views.segment_card(views._find(slug), 1)["name"]
        return start_regenerate([name], body.what, fresh=True)

    @app.post("/api/regenerate")
    def regenerate_all(body: RegenerateIn):
        views._segments()                                # setup prompt when nothing is scored yet
        return start_regenerate(None, body.what, fresh=False)

    # ---------- bring your own data ----------
    def load_import(import_id):
        item = imports.get(import_id)
        if item is None:
            raise views.Missing("import")
        if item["raw"] is None:
            item["raw"] = importer.read_table(item["path"])
        return item

    def analyzed(import_id, body):
        item = load_import(import_id)
        saved = (stores.read_meta(body.store) or {}).get("category_map", {}) if body.store else {}
        category_map = {**saved, **body.category_map}
        df, problems = importer.clean(item["raw"], body.mapping)
        if df.empty:
            raise ValueError("No usable rows: check the date and amount columns.")
        return df, problems, category_map

    @app.get("/api/import/template")
    def import_template():
        return PlainTextResponse(importer.template_csv(), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="dimaagi-cart-template.csv"'})

    @app.post("/api/import/upload")
    def import_upload(file: UploadFile = File(...)):
        name = file.filename or "upload.csv"
        ext = Path(name).suffix.lower()
        if ext not in IMPORT_TYPES:
            return error(400, "bad_file", "Upload a CSV or Excel (.xlsx) file.")
        import_id = secrets.token_hex(6)
        folder = jobs.UPLOADS / import_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"source{ext}"
        with open(path, "wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        try:
            preview = importer.read_table(path, nrows=importer.PREVIEW_ROWS)
        except Exception as e:
            return error(400, "bad_file", f"The file couldn't be read: {str(e)[:200]}")
        if preview.empty or len(preview.columns) < 3:
            return error(400, "bad_file", "The file needs a header row and at least 3 columns.")
        imports[import_id] = {"path": path, "raw": None, "filename": name}
        while len(imports) > 3:
            imports.popitem(last=False)
        columns = [str(c) for c in preview.columns]
        return {"import_id": import_id, "filename": name, "columns": columns,
                "preview": preview.fillna("").astype(str).values.tolist(),
                "suggested": importer.suggest_mapping(columns),
                "fields": [{"key": k, "label": v[0], "required": v[1]} for k, v in importer.FIELDS.items()],
                "targets": importer.TARGETS, "stores": [s for s in stores.all_stores() if not s["demo"]]}

    @app.post("/api/import/{import_id}/analyze")
    def import_analyze(import_id: str, body: AnalyzeIn):
        try:
            df, problems, category_map = analyzed(import_id, body)
            return {"categories": importer.categories(df, category_map),
                    "report": importer.report(df, problems, category_map)}
        except ValueError as e:
            return error(400, "bad_mapping", str(e))

    @app.post("/api/import/{import_id}/run")
    def import_run(import_id: str, body: RunImportIn):
        if body.mode not in ("pretrained", "train"):
            return error(400, "bad_request", "mode must be 'pretrained' or 'train'.")
        try:
            df, _, category_map = analyzed(import_id, body)
            slug = stores.create(body.store_name)
            stores.write_meta(slug, mapping=body.mapping, source_file=imports[import_id]["filename"])
            job = app.state.jobs.start("import", jobs.import_steps(body.mode), jobs.import_store,
                                       slug, df, category_map, body.mode)
        except (ValueError, stores.StoreError) as e:
            return error(400, "bad_request", str(e))
        except jobs.JobBusy as e:
            return error(409, "busy", str(e))
        app.state.conversations.clear()
        return {**job.to_dict(), "store": slug}

    # ---------- chat ----------
    @app.post("/api/chat")
    def chat(body: ChatIn):
        if not body.message.strip():
            return error(400, "empty_message", "Type a question first.")
        if not config.get_key():
            return error(400, "no_key", "Add your Gemini API key in AI settings (Retrain screen) to use the chat.")
        if not views.SEGMENTS.exists():
            raise views.Missing("segments")
        try:
            return app.state.conversations.ask(body.conversation_id, body.message.strip())
        except SystemExit as e:                                  # assistant.ask stops on a daily quota
            return error(429, "quota", str(e).strip() or "Gemini quota used up. Try again later.")
        except Exception as e:
            return error(502, "chat_failed", f"The assistant couldn't answer: {str(e)[:300]}")

    # ---------- knowledge bases, jobs, settings ----------
    @app.post("/api/setup/build-kb")
    def build_kb(body: BuildKbIn):
        if body.kind not in ("reviews", "trends"):
            return error(400, "bad_kind", "kind must be 'reviews' or 'trends'.")
        steps, fn = ((jobs.REVIEWS_STEPS, jobs.build_reviews) if body.kind == "reviews"
                     else (jobs.TRENDS_STEPS, jobs.build_trends))
        try:
            jobs.check_source(body.kind, body.source_path)
            job = app.state.jobs.start(f"build-{body.kind}", steps, fn, body.source_path)
        except jobs.StepFailed as e:
            return error(400, "bad_source", str(e))
        except jobs.JobBusy as e:
            return error(409, "busy", str(e))
        return job.to_dict()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job = app.state.jobs.get(job_id)
        if job is None:
            return error(404, "unknown_job", "No such job.")
        return job.to_dict()

    @app.get("/api/settings")
    def get_settings():
        return config.public_settings()

    @app.post("/api/settings")
    def post_settings(body: SettingsIn):
        if body.clear_key:
            config.set_key(None)
        elif body.gemini_key and body.gemini_key.strip():
            config.set_key(body.gemini_key.strip())
        config.save_models(gemini_model=body.gemini_model, chat_model=body.chat_model)
        return config.public_settings()

    if static_dir and Path(static_dir).is_dir():                 # packaged: serve the built front end too
        index = Path(static_dir) / "index.html"
        app.mount("/assets", StaticFiles(directory=Path(static_dir) / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (Path(static_dir) / path).resolve()
            if path and f.is_file() and Path(static_dir).resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(index)

    return app


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None):
    utf8_console()                                              # pipeline prints use emoji
    ap = argparse.ArgumentParser(description="Dimaagi Cart local backend")
    ap.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    ap.add_argument("--token", default=config.env("TOKEN"))
    ap.add_argument("--dev", action="store_true", help="allow the Vite dev server origin (CORS)")
    ap.add_argument("--static", default=config.env("STATIC_DIR"), help="built front end to serve")
    ap.add_argument("--self-check", action="store_true", help="check the runtime (packaged build) and exit")
    a = ap.parse_args(argv)
    if a.self_check:
        from src.api import selfcheck
        selfcheck.run()

    token = a.token or secrets.token_urlsafe(32)
    port = a.port or free_port()
    data_dir, copied = config.prepare_data_dir(config.default_data_dir())
    if config.migrate_legacy_key():
        print("Copied the saved Gemini key from the legacy WinBack AI entry to Dimaagi Cart.", flush=True)
    config.load_key_into_env()
    config.apply_models(config.read_models())
    stores.restore()
    print(f"Dimaagi Cart backend {VERSION} | data: {data_dir}" + (f" | seeded {len(copied)} files" if copied else ""), flush=True)
    print(f"Listening on http://127.0.0.1:{port}", flush=True)
    if not a.token:
        print(f"Token: {token}", flush=True)

    import uvicorn
    uvicorn.run(create_app(token, dev=a.dev, static_dir=a.static), host="127.0.0.1", port=port,
                log_level="warning")


if __name__ == "__main__":
    main()
