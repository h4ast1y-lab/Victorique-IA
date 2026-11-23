"""Settings screen: user preferences and profile customization."""
from app.config import settings
from app.core import preferences
from app.core.personality import personality_manager


def _restore(client, original):
    client.post("/api/preferences", json=original)


def test_preferences_roundtrip_and_live_settings(client):
    original = client.get("/api/preferences").json()
    try:
        r = client.post("/api/preferences", json={
            "temperature": 1.2, "max_output_tokens": 2048, "theme": "light", "user_name": "Ana",
        })
        assert r.status_code == 200
        body = client.get("/api/preferences").json()
        assert body["temperature"] == 1.2 and body["theme"] == "light" and body["user_name"] == "Ana"
        # Generation values reach the live settings the model clients read.
        assert settings.temperature == 1.2 and settings.max_output_tokens == 2048
    finally:
        _restore(client, original)


def test_invalid_preferences_are_rejected_without_partial_save(client):
    before = client.get("/api/preferences").json()
    for bad in ({"temperature": 9}, {"theme": "neon"}, {"unknown": 1},
                {"enter_to_send": "yes"}, {"claude_code_model": "a b"},
                {"temperature": 0.5, "accent": "x"}):
        assert client.post("/api/preferences", json=bad).status_code == 400, bad
    assert client.get("/api/preferences").json() == before


def test_user_preferences_reach_the_system_prompt(client):
    original = client.get("/api/preferences").json()
    try:
        client.post("/api/preferences", json={
            "user_name": "Ana", "user_about": "Sou designer.", "response_language": "en",
        })
        prompt = personality_manager.build_system_prompt()
        assert "Ana" in prompt and "Sou designer." in prompt and "English" in prompt
    finally:
        _restore(client, original)
    assert "Sou designer." not in personality_manager.build_system_prompt()


def test_profile_avatar_emoji_and_set_default(client):
    default_before = personality_manager.get_default_personality()["id"]
    created = client.post("/api/personalities", json={
        "name": "Revisora", "system_instructions": "Revise textos.",
        "avatar": "📝", "emoji_level": 1, "tone": "meticulosa",
    }).json()
    try:
        assert created["avatar"] == "📝" and created["emoji_level"] == 1
        assert created["tone"] == "meticulosa"  # free text, not a fixed list
        assert "Emojis: não use emojis" in personality_manager.build_system_prompt(created)

        assert client.post(f"/api/personalities/{created['id']}/default").status_code == 200
        assert personality_manager.get_default_personality()["id"] == created["id"]
        assert sum(p["is_default"] for p in personality_manager.list_personalities()) == 1
        assert client.post("/api/personalities/nao-existe/default").status_code == 404
    finally:
        client.post(f"/api/personalities/{default_before}/default")
        client.delete(f"/api/personalities/{created['id']}")


def test_preference_defaults_cover_schema():
    assert set(preferences.defaults()) == set(preferences.SCHEMA)


def test_victorique_factory_profile(client):
    from app.core import victorique_persona as vp
    body = client.get("/api/personalities/victorique/factory").json()
    assert body["tone"] == vp.VICTORIQUE_TONE and body["description"] == vp.VICTORIQUE_DESCRIPTION
    assert client.get("/api/personalities/default/factory").status_code == 404


def test_document_search_failure_does_not_break_the_turn(monkeypatch):
    """Embeddings come from Ollama; when it is off the answer must still go out."""
    import asyncio
    from app.core.context_builder import context_builder

    async def boom(**_kwargs):
        raise ConnectionError("Ollama offline")

    monkeypatch.setattr("app.core.context_builder.vector_store.search", boom)
    ctx = asyncio.run(context_builder.build_context("qual o prazo?", [], enable_rag=True))
    assert ctx["sources"] == [] and ctx["system_prompt"]


def test_engine_failure_reaches_the_ui_as_an_error_event(client, monkeypatch):
    async def broken_stream(**_kwargs):
        raise ConnectionError("motor desligado")
        yield  # pragma: no cover

    monkeypatch.setattr("app.main.assistant_engine.chat_stream", broken_stream)
    r = client.post("/api/chat", json={"message": "oi", "backend": "ollama"})
    assert r.status_code == 200
    assert '"type": "error"' in r.text and "motor desligado" in r.text
    assert '"type": "done"' in r.text
