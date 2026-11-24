"""Biblioteca: sections (folders), books (files) and her activity."""
import json
import os
import time
from pathlib import Path

import pytest

from app.config import BASE_DIR, DATA_DIR
from app.library import activity, sections
from app.security.path_guard import path_guard


def test_default_sections_only_existing_folders(library):
    found = sections.list_sections()
    assert [s["id"] for s in found] == ["downloads", "documentos", "imagens"]
    assert all(s["kind"] == "default" and s["exists"] for s in found)
    assert json.loads(library["store"].read_text(encoding="utf-8"))["seeded"] is True


def test_defaults_are_skipped_when_disabled(library, monkeypatch):
    monkeypatch.setenv("ASSISTANT_LIBRARY_DEFAULTS", "0")
    assert sections.list_sections() == []


def test_link_refuses_drive_root_home_system_and_app_dirs(library, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: library["home"]))
    drive = Path(library["root"].anchor)
    windows = Path(os.environ.get("SystemRoot", "C:\\Windows"))
    cases = [
        (drive, "unidade"),
        (library["home"], "usuário"),
        (library["home"].parent, "usuário"),           # above the home folder
        (BASE_DIR / "app", "aplicativo"),
        (DATA_DIR, "aplicativo"),
        (library["root"] / "nao-existe", "não existe"),
    ]
    if windows.is_dir():
        cases.append((windows, "Windows"))
    for bad, words in cases:
        with pytest.raises(ValueError) as err:
            sections.link(str(bad))
        assert words in str(err.value), (bad, err.value)


def test_link_adds_authorized_dir_and_unlink_removes_it(library):
    folder = library["root"] / "Projetos"
    folder.mkdir()
    target = str(folder / "notas.txt")
    assert not path_guard.is_safe_path(target)
    section = sections.link(str(folder), "Meus projetos")
    assert section["name"] == "Meus projetos" and section["kind"] == "linked"
    assert path_guard.is_safe_path(target)
    assert path_guard.is_safe_path(str(library["home"] / "Downloads" / "x.zip"))  # defaults too
    with pytest.raises(ValueError):
        sections.link(str(folder))                       # already a section
    sections.unlink(section["id"])
    assert not path_guard.is_safe_path(target)
    assert section["id"] not in [s["id"] for s in sections.list_sections()]
    # A default section is hidden for good, not re-created next time.
    sections.unlink("downloads")
    assert "downloads" not in [s["id"] for s in sections.list_sections()]
    assert not path_guard.is_safe_path(str(library["home"] / "Downloads" / "x.zip"))
    with pytest.raises(KeyError):
        sections.unlink("downloads")


def test_unlink_never_drops_a_folder_authorized_by_the_config(library, tmp_path):
    configured = tmp_path / "configurada"
    configured.mkdir()
    path_guard.add_authorized_directory(str(configured))   # as if it came from the settings
    section = sections.link(str(configured))
    sections.unlink(section["id"])
    assert configured.resolve() in path_guard.authorized_dirs


def test_books_lists_files_newest_first_without_reading_content(library, monkeypatch):
    shelf = library["home"] / "Downloads"
    for i, name in enumerate(["velho.pdf", "meio.TXT", "novo.zip"]):
        f = shelf / name
        f.write_bytes(b"x" * (i + 1) * 10)
        os.utime(f, (time.time() - 1000 + i * 100,) * 2)
    (shelf / "subpasta").mkdir()
    (shelf / "desktop.ini").write_text("x")
    (shelf / ".oculto").write_text("x")
    opened = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda *a, **k: opened.append(a[0]) or real_open(*a, **k))
    data = sections.books("downloads")
    assert [f["name"] for f in data["files"]] == ["novo.zip", "meio.TXT", "velho.pdf"]
    assert data["total"] == 3 and data["files"][1]["ext"] == "txt" and data["files"][0]["size"] == 30
    assert not any(str(shelf) in str(p) for p in opened)
    assert len(sections.books("downloads", limit=2)["files"]) == 2
    with pytest.raises(KeyError):
        sections.books("nao-existe")


def test_organizer_move_records_activity_with_sections(library):
    from app.tools import organizer
    sections.list_sections()
    sections.apply_authorization()
    src = library["home"] / "Downloads" / "relatorio.pdf"
    src.write_text("pdf")
    dst = library["home"] / "Documents" / "relatorio.pdf"
    organizer.move_files([{"origem": str(src), "destino": str(dst)}], "teste")
    event = activity.since(0)["events"][-1]
    assert event["kind"] == "move" and event["name"] == "relatorio.pdf"
    assert (event["src_section"], event["dst_section"]) == ("downloads", "documentos")
    organizer.undo()
    undo = activity.since(event["seq"])["events"]
    assert [e["kind"] for e in undo] == ["undo"] and undo[0]["dst_section"] == "downloads"


@pytest.mark.asyncio
async def test_read_file_tool_records_read_activity(library):
    from app.tools.registry import tool_registry
    sections.list_sections()
    sections.apply_authorization()
    book = library["home"] / "Documents" / "conto.txt"
    book.write_text("Era uma vez.", encoding="utf-8")
    result = await tool_registry.execute_tool("read_file", {"path": str(book)})
    assert result["status"] == "success"
    event = activity.since(0)["events"][-1]
    assert event["kind"] == "read" and event["src_section"] == "documentos" and event["name"] == "conto.txt"


def test_agent_tools_map_to_library_kinds(library):
    activity.record_tool("Read", {"file_path": "C:/x/a.txt"})
    activity.record_tool("Edit", {"file_path": "C:/x/a.txt"})
    activity.record_tool("Grep", {"pattern": "x", "path": "C:/x"})
    activity.record_tool("Bash", {"command": "dir"})              # not a book scene
    activity.record_tool("move_files", {"moves": []})             # the organizer records it
    assert [e["kind"] for e in activity.since(0)["events"]] == ["read", "write", "list"]


def test_activity_since_returns_only_new_events(library):
    activity.record("read", "C:/a.txt")
    first = activity.since(0)
    assert first["last"] == 1 and len(first["events"]) == 1
    activity.record("write", "C:/b.txt")
    activity.record("nonsense", "C:/c.txt")                         # unknown kind: ignored
    activity.record("read", None)                                   # no path: ignored
    later = activity.since(first["last"])
    assert [e["name"] for e in later["events"]] == ["b.txt"] and later["last"] == 2
    for i in range(activity.KEEP + 10):
        activity.record("list", f"C:/{i}")
    assert len(activity.since(0)["events"]) == activity.KEEP


def test_library_routes(client, library):
    folder = library["root"] / "Casos"
    folder.mkdir()
    (folder / "pista.md").write_text("# pista", encoding="utf-8")
    ids = [s["id"] for s in client.get("/api/library/sections").json()]
    assert ids == ["downloads", "documentos", "imagens"]
    created = client.post("/api/library/sections", json={"path": str(folder)}).json()
    assert created["name"] == "Casos"
    books = client.get(f"/api/library/sections/{created['id']}/books").json()
    assert [b["name"] for b in books["files"]] == ["pista.md"]
    bad = client.post("/api/library/sections", json={"path": library["root"].anchor})
    assert bad.status_code == 400 and "unidade" in bad.json()["detail"]
    assert client.delete(f"/api/library/sections/{created['id']}").status_code == 200
    assert client.delete(f"/api/library/sections/{created['id']}").status_code == 404
    assert client.get("/api/library/sections/x/books").status_code == 404
    activity.record("read", str(folder / "pista.md"))
    assert client.get("/api/library/activity?since=0").json()["last"] >= 1
    assert client.post("/api/library/pick-folder").json() == {"available": False, "path": None}
    assert client.get("/api/mascot/atlas").headers["content-type"] == "image/webp"
    frames = client.get("/api/mascot/atlas.json").json()
    assert "walk" in frames["anims"] and "read" in frames["anims"]
