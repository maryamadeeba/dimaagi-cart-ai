"""Offline tests for the Phase 3 backend: a temp data dir, an in-memory keyring and a mocked assistant.
No Gemini calls, nothing read from the real models/ or data/."""
import io
import json
import time

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend

from src.api import VERSION, config
from src.api.app import create_app
from src.rag import assistant

TOKEN = "test-token"
H = {"X-Dimaagi-Token": TOKEN}
SEGMENTS = {"as_of": "2017-12-31", "segments": [
    {"segment": "Core · Basket changed", "tier": "Core", "customers": 200, "avg_risk": 0.7,
     "median_spend_per_week": 10.0, "weekly_revenue_at_risk": 3000.0, "share_of_revenue_at_risk": 0.6,
     "reason_mix": {"Basket changed": 1.0},
     "top_lapsed_categories": [{"category": "FLUID MILK PRODUCTS", "regular_buyers": 40, "dropped_rate": 0.7,
                                "healthy_rate": 0.2, "lift": 3.5}]},
    {"segment": "High-value · at risk", "tier": "High-value", "customers": 25, "avg_risk": 0.8,
     "median_spend_per_week": 70.0, "weekly_revenue_at_risk": 2000.0, "share_of_revenue_at_risk": 0.4,
     "reason_mix": {"Visiting less": 0.6, "Basket changed": 0.4},
     "top_lapsed_categories": [{"category": "SOUP", "regular_buyers": 18, "dropped_rate": 1.0,
                                "healthy_rate": 0.15, "lift": 6.6}]},
]}
METRICS = {"test_roc_auc": 0.764, "test_pr_auc": 0.469, "baseline_rule_roc_auc": 0.684, "n_features": 30,
           "capture": {"model": {"20%": 0.436}, "recency_rule": {"20%": 0.378}, "random": {"20%": 0.2}}}


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for name in ("GEMINI_MODEL", "CHAT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield tmp_path
    keyring.set_keyring(old)


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def with_outputs(data_dir):
    write(data_dir / "models/segments.json", SEGMENTS)
    write(data_dir / "models/metrics.json", METRICS)
    return data_dir


@pytest.fixture
def client():
    return TestClient(create_app(TOKEN))


def test_token_required(client, data_dir):
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={"X-Dimaagi-Token": "wrong"}).status_code == 401
    assert client.post("/api/settings", json={"gemini_key": "x"}).status_code == 401
    assert client.get("/api/health", headers=H).status_code == 200


def test_untrusted_host_rejected(client, data_dir):
    assert client.get("/api/health", headers={**H, "Host": "evil.example"}).status_code == 400


def test_health_shape(client, data_dir):
    body = client.get("/api/health", headers=H).json()
    assert body["status"] == "ok" and body["version"] == VERSION
    assert body["kb"] == {"reviews": False, "trends": False}
    assert body["outputs"]["why"] is False and body["outputs"]["kits"] is False


def test_dashboard_numbers_match_segments(client, with_outputs):
    body = client.get("/api/dashboard", headers=H).json()
    segs = SEGMENTS["segments"]
    assert body["totals"]["customers"] == sum(s["customers"] for s in segs)
    assert body["totals"]["weekly_revenue_at_risk"] == sum(s["weekly_revenue_at_risk"] for s in segs)
    by_slug = {s["slug"]: s for s in body["segments"]}
    assert set(by_slug) == {"corebasket", "highvalue"}
    hv = by_slug["highvalue"]
    assert hv["customers"] == 25 and hv["weekly_revenue_at_risk"] == 2000.0
    assert hv["revenue_at_risk_per_customer"] == 80.0
    assert hv["share_of_revenue_at_risk"] == 0.4
    assert hv["lapsed_categories"] == ["soup"] and by_slug["corebasket"]["lapsed_categories"] == ["milk"]
    assert body["focus"] == "highvalue"
    assert body["model"]["roc_auc"] == 0.764 and body["model"]["capture"]["model"]["20%"] == 0.436
    # 200 basket + 0.4 * 25 basket = 210 of 225 customers
    assert body["reason_split"]["basket changed"] == round(210 / 225, 3)


def test_missing_outputs_return_setup_errors(client, data_dir):
    r = client.get("/api/dashboard", headers=H)
    assert r.status_code == 404 and r.json()["error"] == "missing_output" and r.json()["what"] == "segments"
    write(data_dir / "models/segments.json", SEGMENTS)
    r = client.get("/api/segments/highvalue/reasons", headers=H)
    assert r.status_code == 404 and r.json()["what"] == "why"
    r = client.get("/api/segments/highvalue/kit", headers=H)
    assert r.status_code == 404 and r.json()["what"] == "kits"
    r = client.get("/api/segments/nope/kit", headers=H)
    assert r.status_code == 404 and r.json()["error"] == "unknown_segment"


def test_reasons_renumber_refs_and_trim_snippets(client, with_outputs):
    long_text = "Milk was expired again. " * 30
    why = [{"segment": "High-value · at risk", "evidence": [
        {"ref": "R1", "id": "a", "text": "Shelves empty.", "stars": 1, "query": "theme: visiting less"},
        {"ref": "R7", "id": "b", "text": long_text, "stars": 2, "query": "category: fluid milk products"}],
        "summary": {"headline": "h", "evidence_gaps": "no soup evidence",
                    "reasons": [{"reason": "Milk.", "explanation": "e", "citations": ["R7"]},
                                {"reason": "Stock", "explanation": "e", "citations": ["R1, R7"]}]}}]
    write(with_outputs / "models/why_summaries.json", why)
    body = client.get("/api/segments/highvalue/reasons", headers=H).json()
    assert [r["refs"] for r in body["reasons"]] == [["R1"], ["R2", "R1"]]
    assert body["reasons"][0]["title"] == "Milk"
    milk = body["reviews"][0]
    assert milk["original_ref"] == "R7" and milk["topic"] == "milk"
    assert len(milk["text"]) <= 300 and milk["truncated"]
    assert body["gaps"] == "no soup evidence"


def test_chat_with_mocked_assistant(client, with_outputs, monkeypatch):
    calls = []

    def fake_ask(chat, question):
        calls.append((chat, question, assistant.SESSION))
        assistant.SESSION.ref("S", "seg:hv", "Your sales data: High-value · at risk", fixed="S_highvalue")
        return {"answer": "Focus on High-value [S_highvalue] [R9].", "tools": ["list_segments"],
                "cited": ["R9", "S_highvalue"], "invalid": ["R9"], "validity": 0.5,
                "ungrounded_numbers": [], "seconds": 1.2}

    monkeypatch.setattr(assistant, "make_client", lambda: "client")
    monkeypatch.setattr(assistant, "make_chat", lambda c: object())
    monkeypatch.setattr(assistant, "ask", fake_ask)

    r = client.post("/api/chat", json={"conversation_id": "c1", "message": "who first?"}, headers=H)
    assert r.status_code == 400 and r.json()["error"] == "no_key"

    client.post("/api/settings", json={"gemini_key": "fake-key"}, headers=H)
    r = client.post("/api/chat", json={"conversation_id": "c1", "message": "who first?"}, headers=H)
    body = r.json()
    assert r.status_code == 200 and body["tools"] == ["list_segments"] and body["validity"] == 0.5
    assert {c["ref"]: (c["label"], c["valid"]) for c in body["cited"]} == {
        "S_highvalue": ("Your sales data: High-value · at risk", True), "R9": (None, False)}

    client.post("/api/chat", json={"conversation_id": "c1", "message": "and why?"}, headers=H)
    client.post("/api/chat", json={"conversation_id": "c2", "message": "hi"}, headers=H)
    (chat1, _, s1), (chat1b, _, s1b), (chat2, _, s2) = calls
    assert chat1 is chat1b and s1 is s1b          # same conversation keeps its chat and refs
    assert chat2 is not chat1 and s2 is not s1    # a new conversation starts fresh


def test_chat_quota_stop_is_a_clean_error(client, with_outputs, monkeypatch):
    def quota(chat, question):
        raise SystemExit("Daily Gemini quota used up")

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(assistant, "make_client", lambda: "client")
    monkeypatch.setattr(assistant, "make_chat", lambda c: object())
    monkeypatch.setattr(assistant, "ask", quota)
    r = client.post("/api/chat", json={"conversation_id": "c", "message": "hi"}, headers=H)
    assert r.status_code == 429 and r.json()["error"] == "quota"


def test_settings_never_echo_the_key(client, data_dir):
    secret = "AIza-very-secret-key-123"
    r = client.post("/api/settings", json={"gemini_key": secret, "chat_model": "gemini-x-lite"}, headers=H)
    assert secret not in r.text
    assert r.json() == {"has_key": True, "key_source": "credential_manager",
                        "gemini_model": config.DEFAULT_MODELS["gemini_model"], "chat_model": "gemini-x-lite"}
    r = client.get("/api/settings", headers=H)
    assert secret not in r.text and r.json()["has_key"] is True
    saved = (data_dir / config.SETTINGS_FILE).read_text(encoding="utf-8")
    assert secret not in saved                                 # only model names go to disk
    assert keyring.get_password(config.KEYRING_SERVICE, config.KEYRING_USER) == secret
    r = client.post("/api/settings", json={"clear_key": True}, headers=H)
    assert r.json()["has_key"] is False


def wait_for(client, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_import_rejects_bad_files_and_missing_columns(client, data_dir):
    r = client.post("/api/import/upload", files={"file": ("sales.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
                    headers=H)
    assert r.status_code == 400 and r.json()["error"] == "bad_file"
    csv = io.BytesIO(b"customer,date,item\nA,2025-01-01,milk\n")
    up = client.post("/api/import/upload", files={"file": ("sales.csv", csv, "text/csv")}, headers=H).json()
    assert up["suggested"]["amount"] is None
    r = client.post(f"/api/import/{up['import_id']}/analyze", json={"mapping": up["suggested"]}, headers=H)
    assert r.status_code == 400 and "Amount paid" in r.json()["message"]
    r = client.post("/api/import/nope/analyze", json={"mapping": {}}, headers=H)
    assert r.status_code == 404 and r.json()["what"] == "import"


def test_build_kb_checks_the_folder(client, data_dir):
    r = client.post("/api/setup/build-kb", json={"kind": "reviews", "source_path": str(data_dir / "nope")},
                    headers=H)
    assert r.status_code == 400 and r.json()["error"] == "bad_source"
    (data_dir / "pdfs").mkdir()
    r = client.post("/api/setup/build-kb", json={"kind": "trends", "source_path": str(data_dir / "pdfs")},
                    headers=H)
    assert r.status_code == 400 and "No PDF" in r.json()["message"]
    r = client.post("/api/setup/build-kb", json={"kind": "other", "source_path": "x"}, headers=H)
    assert r.json()["error"] == "bad_kind"


def test_seed_copies_shipped_files_without_overwriting(tmp_path):
    src, dst = tmp_path / "bundle", tmp_path / "data"
    write(src / "models/segments.json", SEGMENTS)
    write(src / "models/metrics.json", METRICS)
    write(dst / "models/metrics.json", {"mine": True})
    copied = config.seed_data_dir(dst, src)
    assert copied == ["models/segments.json"]
    assert json.loads((dst / "models/metrics.json").read_text()) == {"mine": True}


def test_chat_labels_hide_file_paths_from_owners(client, with_outputs, monkeypatch):
    def fake_ask(chat, question):
        assistant.SESSION.ref("K", "kit:cv", "Campaign kit: Core · Visiting less (models/campaign_kits.md)",
                              fixed="K_corevisiting")
        return {"answer": "Fix these first [K_corevisiting]:", "tools": ["get_campaign_kit"], "cited": ["K_corevisiting"],
                "invalid": [], "validity": 1.0, "ungrounded_numbers": [], "seconds": 1.0}

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(assistant, "make_client", lambda: "client")
    monkeypatch.setattr(assistant, "make_chat", lambda c: object())
    monkeypatch.setattr(assistant, "ask", fake_ask)
    body = client.post("/api/chat", json={"conversation_id": "c", "message": "what first?"}, headers=H).json()
    assert body["cited"][0]["label"] == "Campaign kit: Core · Visiting less"            # Sources panel
    assert body["how"]["retrieved"][0] == {"ref": "K_corevisiting", "label": "Campaign kit: Core · Visiting less",
                                           "file": "models/campaign_kits.md"}           # How this was made


def test_key_source_says_where_the_key_comes_from(client, data_dir, monkeypatch):
    assert client.get("/api/settings", headers=H).json()["key_source"] is None
    (data_dir / ".env").write_text("GEMINI_API_KEY=from-the-folder\n")
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-folder")
    assert client.get("/api/settings", headers=H).json()["key_source"] == "folder_env"
    monkeypatch.setenv("GEMINI_API_KEY", "set-elsewhere")
    assert client.get("/api/settings", headers=H).json()["key_source"] == "environment"
    client.post("/api/settings", json={"gemini_key": "saved-in-app"}, headers=H)
    body = client.get("/api/settings", headers=H)
    assert body.json()["key_source"] == "credential_manager" and "saved-in-app" not in body.text

