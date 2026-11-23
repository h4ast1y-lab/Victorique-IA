"""Persona Victorique: perfil padrão, modo real no prompt e regras de qualidade."""
import os
import subprocess
import sys
from pathlib import Path

from app.core.personality import personality_manager
from app.memory.database import get_connection, init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_victorique_profile_is_seeded():
    profile = personality_manager.get_personality("victorique")
    assert profile is not None
    assert profile["name"] == "Victorique"


def test_victorique_is_default_on_fresh_db(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ASSISTANT_")}
    env["ASSISTANT_DATA_DIR"] = str(tmp_path / "data")
    code = (
        "from app.memory.database import init_db; init_db(); "
        "from app.core.personality import personality_manager as pm; "
        "print(pm.get_default_personality()['id'])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env,
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip().splitlines()[-1] == "victorique"


def test_user_profile_default_is_preserved():
    mine = personality_manager.save_personality(
        name="Minha", system_instructions="Seja breve.", is_default=True,
        personality_id="perfil-do-usuario",
    )
    try:
        init_db()
        assert personality_manager.get_default_personality()["id"] == mine["id"]
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM personalities WHERE id = 'perfil-do-usuario'")
            conn.execute("UPDATE personalities SET is_default = (id = 'victorique')")


def test_prompt_states_real_mode():
    profile = personality_manager.get_personality("victorique")
    claude = personality_manager.build_system_prompt(profile, mode="claude-code")
    local = personality_manager.build_system_prompt(profile, mode="local")
    assert "Claude Code" in claude
    assert "localmente" not in claude
    assert "localmente" in local


def test_persona_keeps_work_quality_rules():
    text = personality_manager.get_personality("victorique")["system_instructions"]
    assert "tédio" in text
    assert "inventa" in text


def test_persona_v2_has_her_voice_and_examples():
    from app.core import victorique_persona as vp
    text = vp.VICTORIQUE_INSTRUCTIONS
    for marker in ("Fonte da Sabedoria", "fragmentos do caos".upper(), "cachimbo", "Hmph", "EXEMPLOS"):
        assert marker.lower() in text.lower(), marker
    # The voice never costs the work or honesty.
    assert "nunca recusa" in text.lower() and "não inventa" in text.lower()


def test_style_sliders_do_not_impose_a_polite_temperament():
    profile = personality_manager.get_personality("victorique")
    prompt = personality_manager.build_system_prompt(profile, mode="local")
    assert "profissional, educado" not in prompt and "cordialidade" not in prompt
    assert "a personalidade vence" in prompt


def test_claude_mode_keeps_the_persona_voice():
    profile = personality_manager.get_personality("victorique")
    prompt = personality_manager.build_system_prompt(profile, mode="claude-code")
    assert "VOZ NO CLAUDE CODE" in prompt and "Victorique" in prompt


def test_unedited_legacy_profile_is_upgraded_but_edited_one_is_kept():
    from app.core import victorique_persona as vp
    with get_connection() as conn:
        conn.execute(
            "UPDATE personalities SET system_instructions = ?, tone = 'prestativo', description = '' "
            "WHERE id = 'victorique'", (vp.LEGACY_INSTRUCTIONS[0],),
        )
    init_db()
    upgraded = personality_manager.get_personality("victorique")
    assert upgraded["system_instructions"] == vp.VICTORIQUE_INSTRUCTIONS
    assert upgraded["tone"] == vp.VICTORIQUE_TONE and upgraded["emoji_level"] == 1

    with get_connection() as conn:
        conn.execute("UPDATE personalities SET system_instructions = 'Meu texto.' WHERE id = 'victorique'")
    try:
        init_db()
        assert personality_manager.get_personality("victorique")["system_instructions"] == "Meu texto."
    finally:
        with get_connection() as conn:
            conn.execute(
                "UPDATE personalities SET system_instructions = ? WHERE id = 'victorique'",
                (vp.VICTORIQUE_INSTRUCTIONS,),
            )
