def test_voice_sample_uses_selected_reference(client, monkeypatch):
    from app import main
    class Voice:
        available = True
        def audio(self, text, language, emotion):
            assert (text, language, emotion) == ("こんにちは", "ja", "séria")
            return b"RIFFtest"
    monkeypatch.setattr(main, "tts_engine", Voice())
    monkeypatch.setattr(main.settings, "tts_enabled", True)
    response = client.post("/api/tts/audio", json={"text":"こんにちは", "language":"ja", "emotion":"séria"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFtest"


def test_empty_voice_request_is_rejected(client):
    assert client.post("/api/tts/audio", json={"text":""}).status_code == 422


def test_voice_disabled(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings, "tts_enabled", False)
    assert client.post("/api/tts/audio", json={"text":"Olá"}).status_code == 503

