"""
Os padrões de fábrica precisam ser seguros: sem variáveis de ambiente, nenhuma
ação protegida roda sem aprovação e só os diretórios autorizados são acessíveis.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.tools.registry import tool_registry

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _defaults_in_clean_process(tmp_path) -> dict:
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("ASSISTANT_")
    }
    env["ASSISTANT_DATA_DIR"] = str(tmp_path / "data")
    code = (
        "import json; from app.config import settings; "
        "print(json.dumps({'turbo': settings.turbo_mode, "
        "'allow_all': settings.allow_all_directories}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_factory_defaults_are_safe(tmp_path):
    defaults = _defaults_in_clean_process(tmp_path)
    assert defaults == {"turbo": False, "allow_all": False}


def test_turbo_does_not_open_every_directory(monkeypatch):
    from app.security.path_guard import path_guard
    monkeypatch.setattr(settings, "turbo_mode", True)
    monkeypatch.setattr(settings, "allow_all_directories", False)
    outside = str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "win.ini")
    assert path_guard.is_safe_path(outside) is False


@pytest.mark.asyncio
async def test_delete_always_requires_approval_even_in_turbo(monkeypatch, tmp_path):
    from app.security.path_guard import path_guard
    path_guard.add_authorized_directory(str(tmp_path))
    monkeypatch.setattr(settings, "turbo_mode", True)
    target = tmp_path / "nao_apagar.txt"
    target.write_text("x", encoding="utf-8")
    result = await tool_registry.execute_tool("delete_file", {"path": str(target)})
    assert result["status"] == "requires_authorization"
    assert target.exists()


@pytest.mark.asyncio
async def test_approved_action_runs_while_turbo_is_on(monkeypatch, tmp_path):
    """Uma ação aprovada antes de ligar o turbo não pode falhar por causa dele."""
    from app.security.path_guard import path_guard
    from app.security.permissions import security_manager
    path_guard.add_authorized_directory(str(tmp_path))
    target = tmp_path / "aprovado.txt"
    pending = await tool_registry.execute_tool(
        "write_file", {"path": str(target), "content": "ok"}
    )
    assert pending["status"] == "requires_authorization"

    monkeypatch.setattr(settings, "turbo_mode", True)
    status, action = security_manager.resolve_action_detailed(pending["action_id"], True)
    assert status == "approved"
    result = await tool_registry.execute_approved_action(action)
    assert result["status"] == "success"
    assert target.read_text(encoding="utf-8") == "ok"
