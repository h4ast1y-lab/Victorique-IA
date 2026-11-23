"""
ClaudeAgentOptions for one Victorique turn, locked down: the user's personal
Claude Code settings are ignored, every non-trivial action goes through the
permission bridge and the app's own folders are never added as work dirs.
"""
from pathlib import Path
from typing import Any, List, Optional

from claude_agent_sdk import ClaudeAgentOptions

from app.config import settings
from app.security.path_guard import path_guard
from app.claude_code.victorique_tools import VICTORIQUE_TOOL_NAMES, create_victorique_server


def workspace_dir() -> Path:
    path = Path(str(settings.claude_code_workspace)).expanduser()
    return path if path.is_dir() else Path.home()


def extra_dirs() -> List[str]:
    """Authorized directories minus the app's protected folders (code, data, backups)."""
    return [str(d) for d in path_guard.authorized_dirs if not path_guard.is_protected(str(d))]


def build_options(
    *, append_prompt: str, resume: Optional[str], bridge: Any, project_id: Optional[str]
) -> ClaudeAgentOptions:
    kwargs = dict(
        system_prompt={"type": "preset", "preset": "claude_code", "append": append_prompt},
        cwd=str(workspace_dir()),
        add_dirs=extra_dirs(),
        setting_sources=[],
        # Turbo is applied by the bridge (acceptEdits would bypass its
        # protected-path guard), so the mode is always "default".
        permission_mode="default",
        can_use_tool=bridge.can_use_tool,
        mcp_servers={"victorique": create_victorique_server(project_id)},
        allowed_tools=list(VICTORIQUE_TOOL_NAMES),
        include_partial_messages=True,
        resume=resume,
    )
    if settings.claude_code_model:
        kwargs["model"] = settings.claude_code_model
    return ClaudeAgentOptions(**kwargs)
