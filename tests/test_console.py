"""The CLIs print emoji; on a cp1252 console (Windows, or output piped to a file) that used to crash a run after
its work was done. These tests run the print paths with cp1252 streams."""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.console import utf8_console

REPO = Path(__file__).resolve().parents[1]


def cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_cp1252_stream_fails_without_the_fix():
    out = cp1252_stream()
    with pytest.raises(UnicodeEncodeError):
        print("✅ Saved", file=out)
        out.flush()


def test_utf8_console_makes_cp1252_streams_safe(monkeypatch):
    out, err = cp1252_stream(), cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    utf8_console()
    print("✅ Saved | ⚠ check | ❌ failed | Core · Basket changed")
    print("❌ to stderr", file=sys.stderr)
    out.flush(); err.flush()
    assert "✅ Saved" in out.buffer.getvalue().decode("utf-8")
    assert "❌ to stderr" in err.buffer.getvalue().decode("utf-8")


def test_utf8_console_without_a_console(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)            # a windowed (console-less) app
    monkeypatch.setattr(sys, "stderr", io.StringIO())   # a stream that can't be reconfigured
    utf8_console()


def test_cli_print_path_on_a_cp1252_console(tmp_path):
    """python -m src.rag.campaign in an empty folder prints '⚠ ... not found' then stops with '❌ ...'."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models/segments.json").write_text('{"segments": []}')    # no reasons yet: campaign stops with ❌
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "PYTHONPATH": str(REPO)}
    env.pop("GEMINI_API_KEY", None)
    r = subprocess.run([sys.executable, "-m", "src.rag.campaign"], cwd=tmp_path, env=env,
                       capture_output=True, timeout=120)
    out, err = r.stdout.decode("utf-8"), r.stderr.decode("utf-8")
    assert "UnicodeEncodeError" not in err, err
    assert "⚠ config" in out and "store_profile.yaml not found" in out
    assert "❌" in err and r.returncode == 1          # the intended stop, not a crash
