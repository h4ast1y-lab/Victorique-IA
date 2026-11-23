"""
Organização segura: nada é apagado, lotes são tudo-ou-nada, cada lote fica no
histórico e pode ser desfeito, e pastas do sistema ficam fora de alcance.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.claude_code import victorique_tools
from app.claude_code.permissions import describe_target
from app.config import settings
from app.main import app
from app.security.path_guard import path_guard
from app.tools import organizer
from app.tools.registry import tool_registry


@pytest.fixture
def area(tmp_path, monkeypatch):
    monkeypatch.setattr(organizer, "LOG_PATH", tmp_path / "log" / "operations.json")
    root = tmp_path / "biblioteca"
    root.mkdir()
    path_guard.add_authorized_directory(str(root))
    yield root
    path_guard.authorized_dirs = [d for d in path_guard.authorized_dirs if d != root.resolve()]


def _book(folder: Path, name: str, text: str = "x") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_move_batch_is_logged_and_undone(area):
    a = _book(area, "a.pdf", "A")
    b = _book(area, "b.txt", "B")
    result = organizer.move_files([
        {"origem": str(a), "destino": str(area / "PDFs" / "a.pdf")},
        {"origem": str(b), "destino": str(area / "Textos" / "b.txt")},
    ], "Separar por tipo")
    assert result["moved"] == 2
    assert not a.exists() and (area / "PDFs" / "a.pdf").read_text(encoding="utf-8") == "A"

    batches = organizer.list_batches()
    assert batches[0]["description"] == "Separar por tipo"
    assert batches[0]["status"] == "done"

    organizer.undo(result["batch_id"])
    assert a.read_text(encoding="utf-8") == "A" and b.exists()
    assert not (area / "PDFs").exists(), "empty folders created by the batch are removed"
    assert organizer.list_batches()[0]["status"] == "undone"
    with pytest.raises(ValueError):
        organizer.undo(result["batch_id"])


def test_plan_never_overwrites_and_moves_nothing_on_conflict(area):
    a = _book(area, "a.txt", "novo")
    b = _book(area, "b.txt", "B")
    _book(area / "dest", "b.txt", "antigo")
    with pytest.raises(FileExistsError):
        organizer.move_files([
            {"origem": str(a), "destino": str(area / "dest" / "a.txt")},
            {"origem": str(b), "destino": str(area / "dest" / "b.txt")},
        ])
    # Validated as a whole: the first item did not move either.
    assert a.exists() and b.exists()
    assert (area / "dest" / "b.txt").read_text(encoding="utf-8") == "antigo"
    assert organizer.list_batches() == []


def test_duplicate_destinations_are_refused(area):
    a = _book(area, "a.txt")
    b = _book(area / "sub", "a.txt")
    with pytest.raises(ValueError):
        organizer.move_files([
            {"origem": str(a), "destino": str(area / "x" / "a.txt")},
            {"origem": str(b), "destino": str(area / "x" / "a.txt")},
        ])


def test_failure_midway_rolls_back(area, monkeypatch):
    a = _book(area, "a.txt")
    b = _book(area, "b.txt")
    real_move = organizer.shutil.move
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disco ocupado")
        return real_move(src, dst)

    monkeypatch.setattr(organizer.shutil, "move", flaky)
    with pytest.raises(OSError):
        organizer.move_files([
            {"origem": str(a), "destino": str(area / "n" / "a.txt")},
            {"origem": str(b), "destino": str(area / "n" / "b.txt")},
        ])
    assert a.exists() and b.exists()


def test_reserve_keeps_relative_path_and_can_be_restored(area):
    doc = _book(area / "Notas", "velho.txt", "guardado")
    result = organizer.send_to_reserve([str(doc)])
    dst = Path(result["ops"][0]["dst"])
    assert not doc.exists()
    assert dst.read_text(encoding="utf-8") == "guardado"
    assert dst.parts[-2:] == ("Notas", "velho.txt")
    assert organizer.RESERVE_DIR_NAME in dst.parts
    assert area.resolve() in dst.parents
    _book(area / organizer.RESERVE_DIR_NAME, "outro.txt")  # unrelated content stays
    organizer.undo()
    assert doc.read_text(encoding="utf-8") == "guardado"
    assert (area / organizer.RESERVE_DIR_NAME / "outro.txt").exists()
    assert not dst.parent.exists()


def test_rename_refuses_folders_in_name(area):
    a = _book(area, "a.txt")
    with pytest.raises(ValueError):
        organizer.rename_file(str(a), "../fora.txt")
    organizer.rename_file(str(a), "b.txt")
    assert (area / "b.txt").exists() and not a.exists()


def test_outside_authorized_area_is_refused(area, tmp_path):
    outside = _book(tmp_path / "fora", "x.txt")
    with pytest.raises(PermissionError):
        organizer.move_files([{"origem": str(outside), "destino": str(area / "x.txt")}])
    inside = _book(area, "y.txt")
    with pytest.raises(PermissionError):
        organizer.move_files([{"origem": str(inside), "destino": str(tmp_path / "fora" / "y.txt")}])
    assert outside.exists() and inside.exists()


def test_system_folders_are_protected_but_temp_is_not(tmp_path):
    windows = os.environ.get("SystemRoot") or "C:\\Windows"
    assert path_guard.is_protected(str(Path(windows) / "System32" / "x.dll"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        assert path_guard.is_protected(str(Path(appdata) / "algo" / "config.json"))
    assert not path_guard.is_system_path(tmp_path.resolve())


@pytest.mark.asyncio
async def test_delete_tool_moves_to_reserve_after_approval(area, monkeypatch):
    from app.security.permissions import security_manager
    monkeypatch.setattr(settings, "turbo_mode", True)
    target = _book(area, "rascunho.txt", "não some")
    pending = await tool_registry.execute_tool("delete_file", {"path": str(target)})
    assert pending["status"] == "requires_authorization"
    status, action = security_manager.resolve_action_detailed(pending["action_id"], True)
    assert status == "approved"
    result = await tool_registry.execute_approved_action(action)
    assert result["status"] == "success", result
    assert result["result"]["status"] == "moved_to_reserve"
    assert not target.exists()
    assert Path(result["result"]["reserve_path"]).read_text(encoding="utf-8") == "não some"


@pytest.mark.asyncio
async def test_move_and_rename_tools_always_ask(area, monkeypatch):
    monkeypatch.setattr(settings, "turbo_mode", True)
    a = _book(area, "a.txt")
    moved = await tool_registry.execute_tool(
        "move_files", {"moves": [{"origem": str(a), "destino": str(area / "b" / "a.txt")}]}
    )
    renamed = await tool_registry.execute_tool("rename_file", {"path": str(a), "new_name": "c.txt"})
    assert moved["status"] == renamed["status"] == "requires_authorization"
    assert a.exists()


def test_organizer_mcp_tools_are_never_preapproved():
    from app.claude_code.options import build_options  # noqa: F401  (import check)
    for name in victorique_tools.ORGANIZER_TOOL_NAMES:
        assert name not in victorique_tools.VICTORIQUE_TOOL_NAMES
    assert describe_target("mcp__victorique__mover_arquivos", {"moves": [{}, {}]}) == "2 item(ns) no plano"


@pytest.mark.asyncio
async def test_mcp_move_reports_errors_without_raising(area):
    out = await victorique_tools.mover_arquivos({"moves": [{"origem": str(area / "nao.txt"),
                                                            "destino": str(area / "x.txt")}]})
    assert "Nada foi alterado" in out["content"][0]["text"]


def test_operations_api_lists_and_undoes(area):
    a = _book(area, "a.txt")
    batch = organizer.rename_file(str(a), "b.txt")
    client = TestClient(app)
    listed = client.get("/api/operations").json()
    assert listed[0]["id"] == batch["batch_id"]
    res = client.post(f"/api/operations/{batch['batch_id']}/undo")
    assert res.status_code == 200 and a.exists()
    again = client.post(f"/api/operations/{batch['batch_id']}/undo")
    assert again.status_code == 409
