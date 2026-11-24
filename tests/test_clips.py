"""Clipes do retrato: só estados conhecidos, só mídia, nunca fora da pasta."""
import pytest
from fastapi.testclient import TestClient

from app.core import clips
from app.main import app


@pytest.fixture
def clip_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(clips, "CLIPS_DIR", tmp_path / "clips")
    clips.ensure_dirs()
    return tmp_path / "clips"


def test_lists_media_per_state_and_ignores_other_files(clip_dir):
    (clip_dir / "pensando" / "cachimbo.webm").write_bytes(b"\x1a\x45")
    (clip_dir / "pensando" / "notas.txt").write_text("x", encoding="utf-8")
    (clip_dir / "acordada" / "retrato.png").write_bytes(b"\x89PNG")
    found = clips.list_clips()
    assert set(found) == set(clips.STATES)
    assert found["pensando"] == [{"name": "cachimbo.webm", "kind": "video"}]
    assert found["acordada"] == [{"name": "retrato.png", "kind": "image"}]
    assert found["dormindo"] == []


def test_clip_path_refuses_traversal_unknown_state_and_other_types(clip_dir, tmp_path):
    (clip_dir / "erro" / "ok.mp4").write_bytes(b"0")
    (tmp_path / "segredo.mp4").write_bytes(b"0")
    (clip_dir / "erro" / "script.js").write_text("x", encoding="utf-8")
    assert clips.clip_path("erro", "ok.mp4") is not None
    assert clips.clip_path("erro", "../../segredo.mp4") is None
    assert clips.clip_path("erro", "..\\..\\segredo.mp4") is None
    assert clips.clip_path("outro", "ok.mp4") is None
    assert clips.clip_path("erro", "script.js") is None
    assert clips.clip_path("erro", "falta.mp4") is None


def test_clip_endpoints(clip_dir):
    (clip_dir / "falando" / "fala.webm").write_bytes(b"webm-bytes")
    client = TestClient(app)
    data = client.get("/api/clips").json()
    assert data["states"]["falando"][0]["name"] == "fala.webm"
    ok = client.get("/api/clips/falando/fala.webm")
    assert ok.status_code == 200 and ok.content == b"webm-bytes"
    assert client.get("/api/clips/falando/nada.webm").status_code == 404
    assert client.get("/api/clips/sistema/fala.webm").status_code == 404
