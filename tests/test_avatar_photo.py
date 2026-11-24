"""Foto do avatar: padrão, envio (com validação real) e restauração."""
import io

import pytest
from PIL import Image

from app.core import avatar_photo, preferences


def _image_bytes(fmt="PNG", size=(300, 200), color=(200, 30, 30)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


@pytest.fixture(autouse=True)
def _restore(client):
    client.delete("/api/avatar/photo")
    yield
    client.delete("/api/avatar/photo")


def test_default_photo_is_served(client):
    info = client.get("/api/avatar/photo/info").json()
    assert info["source"] == "default"
    res = client.get("/api/avatar/photo")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/webp")
    with Image.open(io.BytesIO(res.content)) as img:
        assert img.size[0] == img.size[1]


def test_favicon_is_the_photo(client):
    res = client.get("/favicon.ico")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_upload_valid_image_is_squared_and_persisted(client, fmt):
    files = {"file": (f"foto.{fmt.lower()}", _image_bytes(fmt), "image/png")}
    res = client.post("/api/avatar/photo", files=files)
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "custom"
    assert preferences.load()["avatar_photo"] == "custom"
    assert avatar_photo.CUSTOM_PATH.is_file()

    served = client.get("/api/avatar/photo")
    assert served.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(served.content)) as img:
        assert img.format == "PNG"
        assert img.size == (200, 200)


def test_large_image_is_reduced(client):
    files = {"file": ("big.png", _image_bytes("PNG", size=(1600, 1200)), "image/png")}
    assert client.post("/api/avatar/photo", files=files).status_code == 200
    with Image.open(io.BytesIO(client.get("/api/avatar/photo").content)) as img:
        assert img.size == (avatar_photo.OUTPUT_SIZE, avatar_photo.OUTPUT_SIZE)


def test_rejects_file_that_is_not_an_image(client):
    files = {"file": ("foto.png", b"isto nao e uma imagem" * 10, "image/png")}
    res = client.post("/api/avatar/photo", files=files)
    assert res.status_code == 400
    assert "imagem" in res.json()["detail"].lower()
    assert client.get("/api/avatar/photo/info").json()["source"] == "default"


def test_rejects_unsupported_image_format(client):
    files = {"file": ("foto.gif", _image_bytes("GIF"), "image/gif")}
    res = client.post("/api/avatar/photo", files=files)
    assert res.status_code == 400
    assert "formato" in res.json()["detail"].lower()


def test_rejects_too_large_file(client):
    data = b"\x89PNG\r\n\x1a\n" + b"0" * (avatar_photo.MAX_BYTES + 10)
    res = client.post("/api/avatar/photo", files={"file": ("grande.png", data, "image/png")})
    assert res.status_code == 413
    assert client.get("/api/avatar/photo/info").json()["source"] == "default"


def test_rejects_tiny_image(client):
    files = {"file": ("mini.png", _image_bytes("PNG", size=(10, 10)), "image/png")}
    assert client.post("/api/avatar/photo", files=files).status_code == 400


def test_restore_default_removes_custom_photo(client):
    files = {"file": ("foto.png", _image_bytes(), "image/png")}
    assert client.post("/api/avatar/photo", files=files).status_code == 200
    res = client.delete("/api/avatar/photo")
    assert res.status_code == 200
    assert res.json()["source"] == "default"
    assert not avatar_photo.CUSTOM_PATH.exists()
    assert preferences.load()["avatar_photo"] == "default"
    assert client.get("/api/avatar/photo").headers["content-type"].startswith("image/webp")


def test_missing_custom_file_falls_back_to_default(client):
    preferences.update({"avatar_photo": "custom"})
    avatar_photo.CUSTOM_PATH.unlink(missing_ok=True)
    assert client.get("/api/avatar/photo/info").json()["source"] == "default"
    assert client.get("/api/avatar/photo").status_code == 200
