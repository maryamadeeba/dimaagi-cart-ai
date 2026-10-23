"""v0.3.2 rename (WinBack AI -> Dimaagi Cart): legacy env vars and the saved key keep working, and the old name is
gone from everything that ships. Offline: an in-memory keyring, no real Credential Manager or %APPDATA%."""
import re
from pathlib import Path

import keyring
import pytest

from src.api import config
from tests.test_api import MemoryKeyring

REPO = Path(__file__).resolve().parents[1]


# ---------- env vars: DIMAAGI_ is the name, WINBACK_ a deprecated alias ----------
@pytest.fixture
def clean_env(monkeypatch):
    for prefix in (config.ENV_PREFIX, config.LEGACY_ENV_PREFIX):
        for name in ("DATA_DIR", "TOKEN", "STATIC_DIR"):
            monkeypatch.delenv(prefix + name, raising=False)
    return monkeypatch


def test_env_new_name(clean_env):
    clean_env.setenv("DIMAAGI_TOKEN", "new")
    assert config.env("TOKEN") == "new"


def test_env_legacy_alias_still_works(clean_env, capsys):
    clean_env.setenv("WINBACK_TOKEN", "old")
    assert config.env("TOKEN") == "old"
    assert "deprecated" in capsys.readouterr().out          # says so, without printing the value
    assert "old" not in capsys.readouterr().out


def test_env_new_name_wins_over_legacy(clean_env):
    clean_env.setenv("WINBACK_TOKEN", "old")
    clean_env.setenv("DIMAAGI_TOKEN", "new")
    assert config.env("TOKEN") == "new"
    assert config.env("STATIC_DIR", "fallback") == "fallback"


def test_data_dir_alias_precedence(clean_env, tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    clean_env.setenv("WINBACK_DATA_DIR", str(old))
    assert config.default_data_dir() == old
    clean_env.setenv("DIMAAGI_DATA_DIR", str(new))
    assert config.default_data_dir() == new


def test_packaged_default_folder_is_dimaagicart(clean_env, tmp_path):
    clean_env.setattr(config, "is_frozen", lambda: True)
    clean_env.setenv("APPDATA", str(tmp_path))
    assert config.default_data_dir() == tmp_path / "DimaagiCart"


# ---------- the Gemini key in Credential Manager (a fake keyring here) ----------
@pytest.fixture
def ring(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    old = keyring.get_keyring()
    fake = MemoryKeyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(old)


def test_service_names():
    assert config.KEYRING_SERVICE == "Dimaagi Cart"
    assert config.LEGACY_KEYRING_SERVICE == "WinBack AI"


def test_legacy_key_is_copied_once(ring, capsys):
    ring.set_password(config.LEGACY_KEYRING_SERVICE, config.KEYRING_USER, "AIza-legacy-secret")
    assert config.migrate_legacy_key() is True
    assert ring.get_password(config.KEYRING_SERVICE, config.KEYRING_USER) == "AIza-legacy-secret"
    assert ring.get_password(config.LEGACY_KEYRING_SERVICE, config.KEYRING_USER) == "AIza-legacy-secret"   # left as is
    assert config.get_key() == "AIza-legacy-secret" and config.key_source() == "credential_manager"
    assert "AIza-legacy-secret" not in capsys.readouterr().out                                          # never logged
    assert config.migrate_legacy_key() is False                                                           # once only


def test_existing_new_key_is_never_overwritten(ring):
    ring.set_password(config.LEGACY_KEYRING_SERVICE, config.KEYRING_USER, "old-key")
    ring.set_password(config.KEYRING_SERVICE, config.KEYRING_USER, "new-key")
    assert config.migrate_legacy_key() is False
    assert ring.get_password(config.KEYRING_SERVICE, config.KEYRING_USER) == "new-key"


def test_a_cleared_key_is_not_brought_back(ring):
    ring.set_password(config.LEGACY_KEYRING_SERVICE, config.KEYRING_USER, "old-key")
    config.migrate_legacy_key()
    config.set_key(None)                                  # the owner removes the key in Settings
    assert config.migrate_legacy_key() is False          # next start: not copied again
    assert config.get_key() is None


def test_no_legacy_key_is_fine(ring):
    assert config.migrate_legacy_key() is False
    assert ring.get_password(config.KEYRING_SERVICE, config.KEYRING_USER) is None


# ---------- the old name is gone from what ships ----------
# Everything that goes into the installer: the front end, the Electron shell and the backend (its log lines too).
SHIPPED = ["frontend/index.html", "frontend/src/**/*.js", "frontend/src/**/*.jsx", "frontend/src/**/*.css",
           "frontend/public/*", "desktop/*.js", "desktop/splash.html", "desktop/package.json", "src/**/*.py"]
# The product name in any spelling: WinBack, WINBACK_, winback., "Win Back AI". Not the plain-English "win them
# back", "Win back your customers" or the marketing term "win-back campaign".
OLD_NAME = re.compile(r"win_?back|win back ai", re.IGNORECASE)


def shipped_files():
    files = {p for pattern in SHIPPED for p in REPO.glob(pattern) if p.is_file()}
    assert len(files) > 40, "the shipped-file patterns stopped matching"
    return sorted(files)


def test_old_name_not_in_shipped_strings():
    # Migration code has to name the legacy entries; those lines say "legacy" (case-insensitive).
    hits = []
    for f in shipped_files():
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if OLD_NAME.search(line) and "legacy" not in line.lower():
                hits.append(f"{f.relative_to(REPO).as_posix()}:{n}: {line.strip()[:100]}")
    assert not hits, "old product name in shipped files:\n" + "\n".join(hits)


def test_guard_catches_the_old_name():
    assert OLD_NAME.search("Ask WinBack") and OLD_NAME.search("WINBACK_DATA_DIR") and OLD_NAME.search("Win Back AI")
    assert not OLD_NAME.search("Win them back") and not OLD_NAME.search("a win-back campaign")
    assert not OLD_NAME.search("Win back your 40 regulars first.")


def test_new_name_is_shown():
    sidebar = (REPO / "frontend/src/components/Sidebar.jsx").read_text(encoding="utf-8")
    assert "Ask Dimaagi" in sidebar and "Win them back" in sidebar and "Dimaagi Cart" in sidebar
    assert "<title>Dimaagi Cart</title>" in (REPO / "frontend/index.html").read_text(encoding="utf-8")
