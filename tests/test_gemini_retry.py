"""Offline checks for src.rag.gemini retries: the genai client is mocked, so there is no network call."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from src.rag import gemini


class Tiny(BaseModel):
    ok: bool


@pytest.fixture
def fake_client(monkeypatch, tmp_path):
    """Mock genai.Client, keep the cache in a temp dir, and make retries instant."""
    import google.genai

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    sleeps = MagicMock()
    monkeypatch.setattr(gemini.time, "sleep", sleeps)
    client = MagicMock()
    monkeypatch.setattr(google.genai, "Client", MagicMock(return_value=client))
    return client.models.generate_content, sleeps


def test_permanent_error_raises_after_one_attempt(fake_client):
    generate, sleeps = fake_client
    generate.side_effect = ValueError("400 INVALID_ARGUMENT: bad schema")
    with pytest.raises(ValueError, match="INVALID_ARGUMENT"):
        gemini.gemini_json("prompt-permanent", Tiny, model="test-model")
    assert generate.call_count == 1
    sleeps.assert_not_called()


def test_temporary_error_is_retried(fake_client):
    generate, sleeps = fake_client
    generate.side_effect = [RuntimeError("503 UNAVAILABLE"), SimpleNamespace(text='{"ok": true}')]
    out, cached = gemini.gemini_json("prompt-temporary", Tiny, model="test-model")
    assert out == {"ok": True} and cached is False
    assert generate.call_count == 2
    assert sleeps.call_count == 1


def test_fourth_temporary_failure_raises(fake_client):
    generate, sleeps = fake_client
    generate.side_effect = RuntimeError("503 UNAVAILABLE")
    with pytest.raises(RuntimeError, match="503"):
        gemini.gemini_json("prompt-always-busy", Tiny, model="test-model")
    assert generate.call_count == 4
    assert sleeps.call_count == 3
