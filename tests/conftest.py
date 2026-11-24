import os
import tempfile
from pathlib import Path

# IMPORTANT: configure an isolated data directory BEFORE importing the app.
# Tests must never touch the real data/assistant.db.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="assistente-pessoal-testes-"))
_TEST_DATA = _TEST_ROOT / "data"

os.environ["ASSISTANT_DATA_DIR"] = str(_TEST_DATA)
os.environ["ASSISTANT_DB_PATH"] = str(_TEST_DATA / "assistant.db")
os.environ["ASSISTANT_TESTING"] = "1"
# Run the suite on the real factory defaults (turbo and allow-all are opt-in).
os.environ.pop("ASSISTANT_TURBO_MODE", None)
os.environ.pop("ASSISTANT_ALLOW_ALL_DIRS", None)
os.environ["ASSISTANT_MAX_TOOL_ROUNDS"] = "3"
# The Biblioteca never seeds the real Downloads/Documents during tests.
os.environ["ASSISTANT_LIBRARY_DEFAULTS"] = "0"
os.environ.setdefault("ASSISTANT_MODEL", os.environ.get("ASSISTANT_MODEL", "qwen2.5-coder:7b"))
# Nos testes, forcar Ollama como backend (mockado nos testes) para evitar
# tentar iniciar o llama-server real.
os.environ["ASSISTANT_DEFAULT_BACKEND"] = "ollama"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.memory.database import init_db  # noqa: E402

init_db()


def _ollama_up() -> bool:
    import httpx
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        return httpx.get(f"{url}/api/version", timeout=1.0).status_code == 200
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live_ollama: needs a running Ollama server; skipped when offline"
    )


def pytest_collection_modifyitems(config, items):
    marked = [item for item in items if item.get_closest_marker("live_ollama")]
    if marked and not _ollama_up():
        skip = pytest.mark.skip(reason="Ollama offline")
        for item in marked:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    return _TEST_DATA


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app
    return TestClient(app, base_url="http://127.0.0.1:8765")


@pytest.fixture
def library(tmp_path, monkeypatch):
    """An empty library.json and a fake home with some of the default folders."""
    from app.library import activity, sections
    from app.security.path_guard import path_guard
    store = tmp_path / "library.json"
    home = tmp_path / "home"
    for name in ("Downloads", "Documents", "Pictures"):
        (home / name).mkdir(parents=True)
    monkeypatch.setattr(sections, "_store_path", lambda: store)
    monkeypatch.setattr(sections, "default_folders", lambda: [
        (ident, label, home / folder)
        for ident, label, _guid, folder in sections._DEFAULTS
        if (home / folder).is_dir()
    ])
    monkeypatch.setenv("ASSISTANT_LIBRARY_DEFAULTS", "1")
    monkeypatch.delenv("ASSISTANT_AUTHORIZED_DIRS", raising=False)
    before = list(path_guard.authorized_dirs)
    activity.clear()
    yield {"home": home, "store": store, "root": tmp_path}
    path_guard.authorized_dirs[:] = before
    sections._authorized.clear()
    activity.clear()
