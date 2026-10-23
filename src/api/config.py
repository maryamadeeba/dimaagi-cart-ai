"""Where the app keeps its data, and the AI settings (the Gemini key lives in the OS keyring, never in a file).

Every existing module uses paths relative to the working directory (models/, data/vectorstore, config/...),
so the backend switches into the data directory once at launch and all of them resolve from there.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import keyring
from keyring.errors import KeyringError

APP_NAME = "DimaagiCart"
# The two service names can be overridden only so checks and launch tests use throwaway Credential Manager entries
KEYRING_SERVICE = os.getenv("DIMAAGI_KEYRING_SERVICE") or "Dimaagi Cart"
KEYRING_USER = "gemini_api_key"
KEYRING_MIGRATED = "legacy_key_checked"  # marker in KEYRING_SERVICE: the old key was looked for once, never again
ENV_PREFIX = "DIMAAGI_"
# Legacy: before v0.3.2 the app was called WinBack AI. Its env vars and Credential Manager entry are still read.
LEGACY_ENV_PREFIX = "WINBACK_"
LEGACY_KEYRING_SERVICE = os.getenv("DIMAAGI_LEGACY_KEYRING_SERVICE") or "WinBack AI"
DEFAULT_MODELS = {"gemini_model": "gemini-3.8-flash", "chat_model": "gemini-3.5-flash-lite"}   # as in .env.example
ENV_NAMES = {"gemini_model": "GEMINI_MODEL", "chat_model": "CHAT_MODEL"}
SETTINGS_FILE = "settings.json"          # model names and app choices, no secrets

# What ships with the app and is copied into a fresh data directory (see dimaagi-backend.spec)
SEED_FILES = ["models/churn_model.pkl", "models/feature_columns.json", "models/metrics.json",
              "models/churn_model_behaviour.pkl", "models/feature_columns_behaviour.json",
              "models/metrics_behaviour.json",            # pre-trained model for imported stores (no marketing data)
              "models/segments.json", "models/scored_customers.csv", "models/drivers.json",   # the demo store
              "config/store_profile.yaml", "config/niche.yaml", "config/trend_sources.csv"]

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_frozen():
    return getattr(sys, "frozen", False)


def bundle_dir():
    """Folder holding the shipped defaults: the PyInstaller bundle when packaged, the repo in dev."""
    return Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / "defaults" if is_frozen() else REPO_ROOT


_warned = set()


def env(name, default=None):
    """DIMAAGI_<name>, else the deprecated legacy alias (DIMAAGI_ wins if both are set), else default."""
    if os.getenv(ENV_PREFIX + name):
        return os.environ[ENV_PREFIX + name]
    if os.getenv(LEGACY_ENV_PREFIX + name):
        if name not in _warned:
            _warned.add(name)
            print(f"Note: {LEGACY_ENV_PREFIX}{name} is deprecated; rename it to {ENV_PREFIX}{name}.", flush=True)
        return os.environ[LEGACY_ENV_PREFIX + name]
    return default


def default_data_dir():
    if env("DATA_DIR"):
        return Path(env("DATA_DIR")).expanduser()
    if is_frozen():
        return Path(os.getenv("APPDATA", Path.home())) / APP_NAME
    return REPO_ROOT


def seed_data_dir(data_dir, source=None):
    """Copy the shipped model, segments and config into a new data directory. Never overwrites."""
    source = Path(source or bundle_dir())
    copied = []
    if source.resolve() == Path(data_dir).resolve():
        return copied
    for rel in SEED_FILES:
        src, dst = source / rel, Path(data_dir) / rel
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(rel)
    return copied


def prepare_data_dir(data_dir):
    """Create and seed the data directory, switch into it and point the model caches at it."""
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    copied = seed_data_dir(data_dir)
    os.chdir(data_dir)
    (data_dir / "cache").mkdir(exist_ok=True)
    os.environ["FASTEMBED_CACHE_PATH"] = str(data_dir / "cache")     # embedding + reranker models download once
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")            # ChromaDB sends usage pings unless told not to
    # Personal mode / dev: a .env in the data folder (this repo's) gives the same key and models the CLI tools use.
    # Loaded here, at startup, so the packaged app behaves the same from the first request. Public mode's
    # %APPDATA%\DimaagiCart never has one; the key then comes from Windows Credential Manager.
    if (data_dir / ".env").exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(data_dir / ".env")
        except ImportError:
            pass
    return data_dir, copied


# ---------- settings ----------
def get_key():
    try:
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except KeyringError:
        key = None
    return key or os.getenv("GEMINI_API_KEY") or None


def key_source():
    """Where the key in use comes from: 'credential_manager' (saved in the app), 'folder_env' (the data folder's
    .env, as in personal mode), 'environment' (set outside the app) or None. Compares values in memory only."""
    try:
        if keyring.get_password(KEYRING_SERVICE, KEYRING_USER):
            return "credential_manager"
    except KeyringError:
        pass
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    env_file = Path(".env")                     # the backend runs inside the data folder
    if env_file.exists():
        try:
            from dotenv import dotenv_values
            if dotenv_values(env_file).get("GEMINI_API_KEY") == key:
                return "folder_env"
        except ImportError:
            pass
    return "environment"


def set_key(key):
    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
        os.environ["GEMINI_API_KEY"] = key
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except KeyringError:
            pass
        os.environ.pop("GEMINI_API_KEY", None)


def migrate_legacy_key():
    """Once per computer: if Dimaagi Cart has no saved key but the legacy entry has one, copy it over (the legacy
    entry is left as it is). Returns True if a key was copied. Never logs or returns the key itself."""
    try:
        if keyring.get_password(KEYRING_SERVICE, KEYRING_MIGRATED):
            return False
        copied = False
        if not keyring.get_password(KEYRING_SERVICE, KEYRING_USER):
            old = keyring.get_password(LEGACY_KEYRING_SERVICE, KEYRING_USER)
            if old:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, old)
                copied = True
        # So a key the owner later clears in the app isn't brought back from the legacy entry on the next start
        keyring.set_password(KEYRING_SERVICE, KEYRING_MIGRATED, "1")
        return copied
    except KeyringError:
        return False


def load_key_into_env():
    """Make a keyring-stored key visible to the existing modules, which read GEMINI_API_KEY."""
    try:
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except KeyringError:
        key = None
    if key:
        os.environ["GEMINI_API_KEY"] = key


def read_settings():
    """settings.json in the data folder: model names, the welcome choice and the active store. Never secrets."""
    if Path(SETTINGS_FILE).exists():
        return json.loads(Path(SETTINGS_FILE).read_text(encoding="utf-8"))
    return {}


def write_settings(**updates):
    current = {**read_settings(), **updates}
    Path(SETTINGS_FILE).write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def read_models():
    saved = read_settings()
    return {k: saved.get(k) or os.getenv(ENV_NAMES[k]) or v for k, v in DEFAULT_MODELS.items()}


def save_models(**models):
    current = read_models()
    current.update({k: v for k, v in models.items() if k in DEFAULT_MODELS and v})
    write_settings(**current)
    apply_models(current)
    return current


def apply_models(models):
    """Push model names into the environment and into modules that read them at import time."""
    for k, env in ENV_NAMES.items():
        os.environ[env] = models[k]
    for name, attr, k in (("src.rag.assistant", "CHAT_MODEL", "chat_model"),
                          ("src.rag.generate", "MODEL", "gemini_model"),
                          ("src.rag.campaign", "MODEL", "gemini_model")):
        if name in sys.modules:
            setattr(sys.modules[name], attr, models[k])


def public_settings():
    return {"has_key": bool(get_key()), "key_source": key_source(), **read_models()}
