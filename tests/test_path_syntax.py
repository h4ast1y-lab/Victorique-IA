"""Formas de caminho do Windows que driblam as regras de pasta: rede, dispositivos, ADS, hard links."""
import os

import pytest

from app.security.path_guard import PathGuard, check_windows_path_syntax
from app.tools import file_tools


@pytest.mark.parametrize("raw", [
    r"\\servidor\pasta\arquivo.txt",
    "//servidor/pasta/arquivo.txt",
    r"\\?\C:\Windows\system.ini",
    r"\\.\PhysicalDrive0",
])
def test_network_and_device_paths_are_refused(raw):
    with pytest.raises(PermissionError):
        check_windows_path_syntax(raw)


@pytest.mark.parametrize("raw", [
    r"C:\Users\ana\CON",
    r"C:\Users\ana\nul.txt",
    r"C:\Users\ana\com1\notas.txt",
    r"C:\Users\ana\LPT9.log",
    r"C:\Users\ana\aux .txt",
])
def test_reserved_device_names_are_refused(raw):
    with pytest.raises(PermissionError):
        check_windows_path_syntax(raw)


def test_alternate_data_streams_are_refused():
    with pytest.raises(PermissionError):
        check_windows_path_syntax(r"C:\Users\ana\notas.txt:escondido")
    with pytest.raises(PermissionError):
        check_windows_path_syntax(r"C:\Users\ana\notas.txt::$DATA")


def test_trailing_dot_or_space_only_blocks_writes():
    check_windows_path_syntax(r"C:\Users\ana\relatorio.")
    with pytest.raises(PermissionError):
        check_windows_path_syntax(r"C:\Users\ana\relatorio.", for_write=True)
    with pytest.raises(PermissionError):
        check_windows_path_syntax(r"C:\Users\ana\pasta \a.txt", for_write=True)


@pytest.mark.parametrize("raw", [
    r"C:\Users\ana\console.log",
    r"C:\Users\ana\Documentos\auxiliar.txt",
    r"C:\Users\ana\com10.txt",
    "C:/Users/ana/notas/../outra/arquivo.md",
    "relativo/arquivo.txt",
])
def test_ordinary_names_still_pass(raw):
    check_windows_path_syntax(raw, for_write=True)


def test_guard_applies_the_syntax_check(tmp_path):
    guard = PathGuard([str(tmp_path)])
    with pytest.raises(PermissionError):
        guard.validate_and_resolve(str(tmp_path / "nul.txt"), for_write=True)
    with pytest.raises(PermissionError):
        guard.validate_and_resolve(str(tmp_path / "a.txt") + ":stream")
    assert guard.validate_and_resolve(str(tmp_path / "ok.txt"), for_write=True)


def test_write_file_refuses_hardlinked_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(file_tools, "path_guard", PathGuard([str(tmp_path)]))
    original = tmp_path / "original.txt"
    original.write_text("antes", encoding="utf-8")
    link = tmp_path / "vinculo.txt"
    try:
        os.link(original, link)
    except OSError:
        pytest.skip("o sistema de arquivos não suporta hard links")
    with pytest.raises(PermissionError):
        file_tools.write_file(str(link), "depois")
    assert original.read_text(encoding="utf-8") == "antes"
    single = tmp_path / "sozinho.txt"
    single.write_text("x", encoding="utf-8")
    assert file_tools.write_file(str(single), "y")["overwritten"] is True
