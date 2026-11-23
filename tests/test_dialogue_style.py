"""Anti-repetição: detecta aberturas, ações e frases repetidas sem citá-las no prompt."""
from app.claude_code.backend import build_append_prompt
from app.core.dialogue_style import repeated_phrasing, style_note


def _reply(text):
    return {"role": "assistant", "content": text}


def test_no_note_for_varied_replies():
    history = [
        {"role": "user", "content": "oi"},
        _reply("Ah. Você de novo. Traga-me algo interessante."),
        _reply("Hmph. Um KeyError, que fragmento banal."),
        _reply("O relógio da torre já bateu três vezes e você ainda não decidiu."),
    ]
    assert style_note(history) == ""


def test_repeated_opening_is_detected_but_not_quoted():
    history = [
        _reply("Que tédio mortal, visitante. Pois bem, eis a resposta."),
        _reply("Que tédio mortal, outra vez? A chave não existe."),
        _reply("Que tédio mortal. Use o método get."),
    ]
    found = repeated_phrasing(history)
    assert found["openings"] == [{"text": "que tédio mortal", "count": 3}]
    note = style_note(history)
    assert "aberturas" in note
    assert "tédio mortal" not in note.lower()


def test_repeated_italic_action_is_detected():
    history = [
        _reply("*solta uma baforada do cachimbo* Isso é simples."),
        _reply("Pois bem. *solta uma baforada do cachimbo* Eis a verdade."),
    ]
    found = repeated_phrasing(history)
    assert found["actions"][0]["count"] == 2
    assert "itálico" in style_note(history)
    assert "cachimbo" not in style_note(history)


def test_code_paths_and_user_messages_are_ignored():
    code = "Veja:\n```python\nprint('ola mundo repetido aqui de novo sempre')\n```"
    history = [
        _reply("Primeira resposta. " + code),
        _reply("Outra conversa. " + code),
        _reply("O arquivo C:/Users/ana/notas/relatorio-final-de-novembro.txt foi movido para a Reserva."),
        _reply("Mais uma. O arquivo C:/Users/ana/notas/relatorio-final-de-novembro.txt foi movido para a Reserva."),
        {"role": "user", "content": "repita repita repita repita repita repita"},
        {"role": "user", "content": "repita repita repita repita repita repita"},
    ]
    assert style_note(history) == ""


def test_only_the_last_twelve_replies_count():
    old = [_reply("Frase velha que se repetia demais naquela época distante.")] * 2
    fresh = [_reply(f"Resposta número {i} sem nada em comum.") for i in range(12)]
    assert style_note(old + fresh) == ""


def test_claude_append_prompt_gets_the_note():
    history = [_reply("Que tédio mortal, A."), _reply("Que tédio mortal, B.")]
    assert "OBSERVAÇÃO DE ESTILO" in build_append_prompt(None, None, history)
    assert "OBSERVAÇÃO DE ESTILO" not in build_append_prompt(None, None, [])
