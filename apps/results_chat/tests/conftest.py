import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = Path(__file__).resolve().parents[3]

import pytest  # noqa: E402

os.environ.setdefault("RESULTS_CHAT_PROJECT_ROOT", str(PROJECT_ROOT))

from evidence import load_evidence  # noqa: E402


@pytest.fixture(scope="session")
def ev():
    return load_evidence(PROJECT_ROOT)


@pytest.fixture()
def flask_app(monkeypatch):
    # Force factual mode deterministically for these tests, REGARDLESS of
    # whether a local llama-server happens to be running on this host right
    # now (llm_adapter's "local" provider is auto-detected by a live health
    # check, not by an env var, so merely deleting API-key env vars is not
    # enough to guarantee factual mode during a dev session with the local
    # server up). Live-LLM behavior is covered separately and explicitly by
    # test_live_llm.py, which skips if no server is reachable rather than
    # silently testing against factual mode.
    monkeypatch.setenv("RESULTS_CHAT_LLM_PROVIDER", "none")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    import app as app_module
    app_module.app.config.update(TESTING=True)
    app_module._SESSION_STATE.clear()
    return app_module.app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture()
def chart_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_CHAT_CHART_CACHE_DIR", str(tmp_path / "chart_cache"))
    return tmp_path / "chart_cache"
