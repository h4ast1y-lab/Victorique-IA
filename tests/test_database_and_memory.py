import pytest
from app.memory.database import init_db
from app.memory.conversation_store import conversation_store
from app.memory.memory_store import memory_store
from app.memory.project_store import project_store
from app.core.personality import personality_manager

def test_database_initialization():
    init_db()
    # Check default personality exists
    p = personality_manager.get_default_personality()
    assert p is not None
    assert p["name"] == "Victorique"
    # The stock profile is kept as an alternative.
    assert personality_manager.get_personality("default")["name"] == "Assistente Pessoal"

def test_conversation_crud():
    conv = conversation_store.create_conversation(title="Conversa de Teste")
    assert conv["id"] is not None
    assert conv["title"] == "Conversa de Teste"

    # Add messages
    m1 = conversation_store.add_message(conv["id"], role="user", content="Olá!")
    m2 = conversation_store.add_message(conv["id"], role="assistant", content="Olá! Como posso ajudar?")

    messages = conversation_store.get_messages(conv["id"])
    assert len(messages) == 2
    assert messages[0]["content"] == "Olá!"
    assert messages[1]["content"] == "Olá! Como posso ajudar?"

    # Update title
    ok = conversation_store.update_title(conv["id"], "Conversa Atualizada")
    assert ok is True
    updated = conversation_store.get_conversation(conv["id"])
    assert updated["title"] == "Conversa Atualizada"

    # Delete
    deleted = conversation_store.delete_conversation(conv["id"])
    assert deleted is True
    assert conversation_store.get_conversation(conv["id"]) is None

def test_persistent_memories():
    mem = memory_store.add_memory(category="preference", content="O usuário prefere respostas em português.")
    assert mem["id"] is not None
    assert mem["category"] == "preference"

    memories = memory_store.list_memories()
    assert any(m["id"] == mem["id"] for m in memories)

    # Context formatting
    ctx = memory_store.get_context_for_prompt()
    assert "PREFERENCE" in ctx

    # Clean up
    memory_store.delete_memory(mem["id"])

def test_project_crud():
    proj = project_store.create_project(name="Projeto Alpha", description="Teste de projeto")
    assert proj["name"] == "Projeto Alpha"

    projects = project_store.list_projects()
    assert any(p["id"] == proj["id"] for p in projects)

    project_store.delete_project(proj["id"])
