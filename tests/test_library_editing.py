"""Biblioteca: the user moves, renames and sends books to the Reserva from the hall."""
import pytest

from app.library import activity, editing, sections
from app.tools import organizer


@pytest.fixture
def shelves(library, monkeypatch, tmp_path):
    monkeypatch.setattr(organizer, "LOG_PATH", tmp_path / "log" / "operations.json")
    sections.apply_authorization()          # each section is an authorized folder
    home = library["home"]
    return {"downloads": home / "Downloads", "documentos": home / "Documents", "root": library["root"]}


def _book(folder, name, text="x"):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_move_book_between_shelves_is_an_undoable_batch(shelves):
    src = _book(shelves["downloads"], "nota.txt")
    result = editing.move_book(str(src), "documentos")
    assert (shelves["documentos"] / "nota.txt").exists() and not src.exists()
    ev = activity.since(0)["events"][-1]
    assert ev["kind"] == "move" and ev["actor"] == "usuario"
    assert organizer.list_batches()[0]["description"].startswith("Biblioteca:")
    organizer.undo(result["batch_id"])
    assert src.exists()


def test_rename_and_reserve(shelves):
    src = _book(shelves["downloads"], "a.txt")
    editing.rename_book(str(src), "b.txt")
    renamed = shelves["downloads"] / "b.txt"
    assert renamed.exists() and not src.exists()
    editing.reserve_book(str(renamed))
    assert not renamed.exists()
    events = activity.since(0)["events"]
    assert [e["kind"] for e in events[-2:]] == ["rename", "reserve"]
    assert all(e["actor"] == "usuario" for e in events[-2:])


def _path_for(shelves, case):
    if case == "subpasta":
        sub = shelves["downloads"] / "sub"
        sub.mkdir()
        return _book(sub, "x.txt")
    if case == "fora":
        return _book(shelves["root"], "x.txt")
    return shelves["downloads"] / "nao-existe.txt"


@pytest.mark.parametrize("case", ["subpasta", "fora", "sumiu"])
def test_refuses_books_not_on_the_first_level_of_a_shelf(shelves, case):
    with pytest.raises(editing.BookNotFound):
        editing.move_book(str(_path_for(shelves, case)), "documentos")


def test_same_shelf_and_unknown_shelf_are_refused(shelves):
    src = _book(shelves["downloads"], "a.txt")
    with pytest.raises(ValueError):
        editing.move_book(str(src), "downloads")
    with pytest.raises(ValueError):
        editing.move_book(str(src), "nao-existe")
    assert src.exists()


def test_routes_move_rename_and_reserve(client, shelves):
    a = _book(shelves["downloads"], "a.txt")
    r = client.post("/api/library/books/move", json={"path": str(a), "section_id": "documentos"})
    assert r.status_code == 200 and r.json()["moved"] == 1
    moved = shelves["documentos"] / "a.txt"
    r = client.post("/api/library/books/rename", json={"path": str(moved), "new_name": "c.txt"})
    assert r.status_code == 200
    r = client.post("/api/library/books/reserve", json={"path": str(shelves["documentos"] / "c.txt")})
    assert r.status_code == 200 and not (shelves["documentos"] / "c.txt").exists()


def test_routes_map_errors(client, shelves):
    a = _book(shelves["downloads"], "a.txt")
    _book(shelves["documentos"], "a.txt", "y")
    assert client.post("/api/library/books/move",
                       json={"path": str(a), "section_id": "documentos"}).status_code == 409
    assert client.post("/api/library/books/rename",
                       json={"path": str(a), "new_name": "x/y"}).status_code == 400
    assert client.post("/api/library/books/rename",
                       json={"path": str(a), "new_name": "CON"}).status_code in (400, 403)
    assert client.post("/api/library/books/rename",
                       json={"path": str(a), "new_name": "  "}).status_code == 400
    gone = shelves["downloads"] / "sumiu.txt"
    r = client.post("/api/library/books/reserve", json={"path": str(gone)})
    assert r.status_code == 404 and "não está mais" in r.json()["detail"]
    assert a.exists()
