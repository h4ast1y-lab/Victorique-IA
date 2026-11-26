"""
Sem console (pythonw.exe), sys.stdout e sys.stderr são None. O run.py precisa
dar um destino a eles antes de subir o uvicorn, senão a thread do servidor
morre calada e a janela fica esperando o backend para sempre.
"""
import sys

from uvicorn.logging import DefaultFormatter

import run


def test_without_a_console_the_backend_logger_still_starts(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    run.configure_console()

    assert sys.stdout is not None and sys.stderr is not None
    print("Iniciando Victorique (Desktop)")   # não pode quebrar
    DefaultFormatter(fmt="%(levelprefix)s %(message)s")   # chama sys.stdout.isatty()


def test_a_real_console_is_left_alone(monkeypatch):
    before = sys.stdout
    run.configure_console()
    assert sys.stdout is before
