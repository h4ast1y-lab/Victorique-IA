import pytest
from app.core.assistant import assistant_engine
from app.memory.conversation_store import conversation_store

@pytest.mark.live_ollama
@pytest.mark.asyncio
async def test_live_chat_generation():
    conv = conversation_store.create_conversation(title="Teste de Conversação Real")
    assert conv["id"] is not None

    tokens = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conv["id"],
        user_message="Olá! Em uma única frase, diga quem você é e confirme que roda localmente."
    ):
        if '"type": "token"' in chunk:
            import json
            data = json.loads(chunk.replace("data: ", ""))
            tokens.append(data.get("content", ""))

    response_text = "".join(tokens)
    print("\nRESPOSTA DO MODELO LOCAL:\n", response_text)
    assert len(response_text) > 10
    # Clean up test conversation
    conversation_store.delete_conversation(conv["id"])
