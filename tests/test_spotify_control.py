"""Pedir coisas do Spotify pelos chats (app/spotify/control.py, tools.py): the
bridge's command channel, the control layer with and without the bridge, the
tools in the registry (local models) and in the Claude Code MCP server, and the
WebSocket end to end. No Spotify, no Spicetify, no Windows: all fakes."""
import asyncio
import json
import subprocess
import threading

import pytest

from app.spotify import nowplaying, spicetify
from app.spotify import tools as spotify_tools
from app.spotify.bridge import Bridge, BridgeCommandError, BridgeOffline, bridge as app_bridge
from app.spotify.control import (SpotifyControl, SpotifyError, describe_state, kind_of, parse_volume,
                                 spotify_uri)
from app.spotify.track import Track

from test_spotify import SPOTIFY_ORIGIN, FakeCli, _Async, _Manager, report

NOW = {"title": "Bohemian Rhapsody", "artist": "Queen", "album": "A Night at the Opera", "playing": True}
TRACK_URI = "spotify:track:4u7EnebtmKWzUH433cf5Qv"


def bridge_at(tmp_path):
    return Bridge(path=tmp_path / "spotify_bridge.json")


class Extension:
    """Plays victorique.js: answers each command the app sends with `answer`."""

    def __init__(self, bridge, answer=None, fail=None):
        self.bridge = bridge
        self.answer = answer or (lambda cmd, args: {})
        self.fail = fail
        self.sent = []
        self.link = None

    def connect(self):
        self.link = self.bridge.attach(self.send)
        self.bridge.receive(report("x"))          # its first report: fresh and linked

    async def send(self, text):
        msg = json.loads(text)
        self.sent.append((msg["cmd"], msg["args"]))
        if self.fail:
            reply = {"reply": msg["id"], "ok": False, "error": self.fail}
        else:
            reply = {"reply": msg["id"], "ok": True, "result": self.answer(msg["cmd"], msg["args"])}
        reply["token"] = self.bridge.token()
        asyncio.get_running_loop().call_soon(self.bridge.receive_text, json.dumps(reply))


def control_with(bridge, **kw):
    said = {"opened": [], "smtc": [], "skipped": [], "launched": 0}
    defaults = dict(
        should_launch=lambda: False,
        launch=lambda: said.__setitem__("launched", said["launched"] + 1) or True,
        smtc=lambda action: said["smtc"].append(action) or True,
        reader=lambda: None,
        opener=lambda target: said["opened"].append(target) or True,
        skip_comment=lambda track: said["skipped"].append(track),
        launch_wait=0.5,
    )
    defaults.update(kw)
    return SpotifyControl(bridge, **defaults), said


# ----------------- The command channel -----------------
async def test_a_command_goes_out_and_its_reply_comes_back(tmp_path):
    b = bridge_at(tmp_path)
    ext = Extension(b, lambda cmd, args: {"echo": [cmd, args]})
    ext.connect()
    assert b.linked and b.status()["commands"]
    assert await b.command("search", {"query": "Queen"}) == {"echo": ["search", {"query": "Queen"}]}
    ext.fail = "nada encontrado"
    with pytest.raises(BridgeCommandError, match="nada encontrado"):
        await b.command("play", {})
    assert not b._pending                                   # nothing left waiting


async def test_no_link_a_silent_extension_and_a_closing_one(tmp_path):
    b = bridge_at(tmp_path)
    with pytest.raises(BridgeOffline):
        await b.command("state")
    sent = []

    async def silent(text):
        sent.append(text)

    link = b.attach(silent)
    with pytest.raises(BridgeCommandError, match="a tempo"):
        await b.command("state", timeout=0.05)
    waiting = asyncio.create_task(b.command("state", timeout=5))
    await asyncio.sleep(0.01)
    b.detach(link)
    with pytest.raises(BridgeOffline):
        await waiting
    assert not b.linked and len(sent) == 2


async def test_replies_need_the_token_and_a_known_id_and_the_newest_link_wins(tmp_path):
    b = bridge_at(tmp_path)
    token = b.token()
    assert not b.receive_text(json.dumps({"token": token, "reply": "nope", "ok": True}))
    assert not b.receive_text(json.dumps({"token": "errado", "reply": "x", "ok": True}))

    async def nothing(text):
        pass

    old = b.attach(nothing)
    new = b.attach(nothing)
    b.detach(old)                                        # an old socket closing late
    assert b.linked
    b.detach(new)
    assert not b.linked


async def test_a_command_from_another_thread_uses_the_bridge_loop(tmp_path):
    b = bridge_at(tmp_path)
    Extension(b, lambda cmd, args: {"ok": cmd}).connect()
    result = await asyncio.to_thread(lambda: asyncio.run(b.command("state")))
    assert result == {"ok": "state"}


# ----------------- The control layer -----------------
def test_requests_types_links_and_volume_words():
    assert kind_of("") == "track" and kind_of("Música") == "track" and kind_of("álbum") == "album"
    assert kind_of("curtidas") == "liked" and kind_of("podcast") == "show"
    with pytest.raises(SpotifyError):
        kind_of("vídeo")
    assert spotify_uri("https://open.spotify.com/intl-pt/track/4u7EnebtmKWzUH433cf5Qv?si=abc") == TRACK_URI
    assert spotify_uri(f"toca {TRACK_URI} aí") == TRACK_URI and spotify_uri("Queen") is None
    assert parse_volume("45%") == {"level": 45} and parse_volume(120) == {"level": 100}
    assert parse_volume("mais") == {"delta": 10} and parse_volume("-5") == {"delta": -5}
    assert parse_volume("mudo") == {"level": 0}
    for bad in ("alto demais", True, "1000"):
        with pytest.raises(SpotifyError):
            parse_volume(bad)


async def test_play_searches_inside_spotify_and_says_what_plays(tmp_path):
    b = bridge_at(tmp_path)
    chosen = {"uri": TRACK_URI, "type": "track", "name": "Bohemian Rhapsody", "by": "Queen"}
    other = {"uri": "spotify:track:1AhDOtG9vPSOmsWgNW0BEY", "type": "track", "name": "Live Aid", "by": "Queen"}
    ext = Extension(b, lambda cmd, args: {"chosen": chosen, "others": [other], "now": NOW})
    ext.connect()
    control, said = control_with(b)
    out = await control.play("Bohemian Rhapsody Queen")
    assert ext.sent == [("play", {"query": "Bohemian Rhapsody Queen", "type": "track"})]
    assert out["ok"] and out["mensagem"] == "Tocando agora: Bohemian Rhapsody — Queen."
    assert out["escolhido"]["uri"] == TRACK_URI and out["outras_opcoes"][0]["nome"] == "Live Aid"
    assert said["skipped"] == [Track("Bohemian Rhapsody", "Queen", "A Night at the Opera", True, "spicetify")]
    await control.play("https://open.spotify.com/track/4u7EnebtmKWzUH433cf5Qv")
    assert ext.sent[-1] == ("play", {"uri": TRACK_URI})
    await control.play("", "curtidas")
    assert ext.sent[-1] == ("play", {"query": "", "type": "liked"})
    with pytest.raises(SpotifyError):
        await control.play("")


async def test_play_says_the_album_or_playlist_and_a_failure_in_portuguese(tmp_path):
    b = bridge_at(tmp_path)
    playlist = {"uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "type": "playlist", "name": "Estudos",
                "by": "eu", "mine": True}
    ext = Extension(b, lambda cmd, args: {"chosen": playlist, "others": [], "now": NOW})
    ext.connect()
    control, _ = control_with(b)
    out = await control.play("estudos", "playlist")
    assert "(playlist: Estudos, da sua biblioteca)" in out["mensagem"]
    ext.fail = 'nada encontrado no Spotify para "xyz"'
    with pytest.raises(SpotifyError, match="O Spotify não conseguiu: nada encontrado"):
        await control.play("xyz")


async def test_without_the_bridge_play_opens_the_search_for_the_user(tmp_path):
    control, said = control_with(bridge_at(tmp_path))
    out = await control.play("Clair de Lune")
    assert not out["ok"] and out["ponte"] is False
    assert said["opened"] == ["spotify:search:Clair%20de%20Lune"] and said["launched"] == 0
    assert "abri a busca" in out["mensagem"] and "Reaplicar a ponte" in out["mensagem"]
    await control.play("", "curtidas")
    assert said["opened"][-1] == "spotify:collection:tracks"


async def test_closed_spotify_is_opened_through_spicetify_and_the_request_waits(tmp_path):
    b = bridge_at(tmp_path)
    ext = Extension(b, lambda cmd, args: {"chosen": {"uri": TRACK_URI, "type": "track", "name": "S", "by": "B"},
                                          "now": NOW})

    def launch():
        threading.Timer(0.1, lambda: loop.call_soon_threadsafe(ext.connect)).start()
        return True

    loop = asyncio.get_running_loop()
    control, said = control_with(b, should_launch=lambda: True, launch=launch, launch_wait=3)
    out = await control.play("Bohemian Rhapsody")
    assert out["ok"] and said["opened"] == []


async def test_controls_with_the_bridge_and_through_windows_without_it(tmp_path):
    b = bridge_at(tmp_path)
    state = {"now": NOW, "volume": 40, "shuffle": True, "repeat": 2, "liked": True}
    ext = Extension(b, lambda cmd, args: state)
    control, said = control_with(b)
    out = await control.control("pausar")                     # no bridge: Windows' media controls
    assert out["ok"] and said["smtc"] == ["pause"] and "Windows" in out["mensagem"]
    with pytest.raises(SpotifyError, match="Sem a ponte"):
        await control.control("volume", "50")
    no_smtc, _ = control_with(b, smtc=lambda action: None)
    with pytest.raises(SpotifyError):
        await no_smtc.control("proxima")
    ext.connect()
    assert (await control.control("volume", "40"))["mensagem"] == "Volume em 40%."
    assert (await control.control("aleatorio", "ligar"))["mensagem"] == "Aleatório ligado."
    assert (await control.control("repetir", "faixa"))["mensagem"] == "Repetição: só esta faixa."
    await control.control("aleatorio")
    await control.control("descurtir")
    assert ext.sent == [("volume", {"level": 40}), ("shuffle", {"on": True}), ("repeat", {"mode": 2}),
                        ("shuffle", {}), ("like", {"on": False})]
    assert (await control.control("proxima"))["mensagem"] == "Tocando agora: Bohemian Rhapsody — Queen."
    with pytest.raises(SpotifyError, match="Ação desconhecida"):
        await control.control("dançar")


async def test_what_is_playing_with_and_without_the_bridge(tmp_path):
    b = bridge_at(tmp_path)
    control, _ = control_with(b, reader=lambda: Track("Song", "Band", source="smtc"))
    out = await control.now_playing()
    assert out["mensagem"].startswith("Tocando agora: Song — Band.") and "Windows" in out["mensagem"]
    nothing, _ = control_with(b)
    assert "Nada tocando" in (await nothing.now_playing())["mensagem"]
    Extension(b, lambda cmd, args: {"now": NOW, "progress": 83, "duration": 354, "volume": 60,
                                    "shuffle": False, "repeat": 0, "liked": True,
                                    "next": [{"title": "Love of My Life", "artist": "Queen"}]}).connect()
    text = (await control.now_playing())["mensagem"]
    assert text == ("Tocando agora: Bohemian Rhapsody — Queen (álbum A Night at the Opera), em 1:23 de 5:54. "
                    "Volume 60%, aleatório desligado, repetição desligada, curtida. "
                    "Próximas: Love of My Life — Queen.")
    assert describe_state({"now": None}) == "Nada tocando no Spotify agora."


# ----------------- The tools, in each mode -----------------
async def test_tools_drop_unknown_arguments_and_need_the_required_ones(monkeypatch):
    calls = []

    async def fake_queue(pedido, tipo="musica"):
        calls.append((pedido, tipo))
        return {"ok": True, "mensagem": "Na fila: X.",
                "outras_opcoes": [{"nome": "Y", "de": "Z", "uri": TRACK_URI}]}

    monkeypatch.setitem(spotify_tools.FUNCTIONS, "spotify_fila", fake_queue)
    out = await spotify_tools.run("spotify_fila", {"pedido": "X", "hack": 1, "tipo": None})
    assert calls == [("X", "musica")]
    assert spotify_tools.as_text(out) == ("Na fila: X.\nOutras opções (para trocar, chame spotify_tocar com o URI):"
                                          f"\n- Y — Z ({TRACK_URI})")
    with pytest.raises(SpotifyError, match="Faltou: pedido"):
        await spotify_tools.run("spotify_fila", {})


async def test_local_models_get_free_spotify_tools(monkeypatch):
    from app.tools.registry import tool_registry
    names = [t["function"]["name"] for t in tool_registry.get_ollama_tools()]
    assert {"spotify_tocar", "spotify_fila", "spotify_buscar", "spotify_controlar", "spotify_tocando"} <= set(names)
    assert not any(tool_registry.tools[n].needs_approval for n in spotify_tools.NAMES)

    async def fake(acao, valor=None):
        return {"ok": True, "mensagem": f"{acao}:{valor}"}

    monkeypatch.setattr(tool_registry.tools["spotify_controlar"], "func", fake)
    out = await tool_registry.execute_tool("spotify_controlar", {"acao": "volume", "valor": "30"})
    assert out == {"status": "success", "result": {"ok": True, "mensagem": "volume:30"}}


async def test_claude_code_gets_them_preapproved_with_errors_marked(monkeypatch):
    from app.claude_code import victorique_tools

    async def playing():
        return {"ok": True, "mensagem": "Tocando agora: Song — Band."}

    async def broken():
        raise SpotifyError("A ponte do Spicetify não está conectada.")

    monkeypatch.setitem(spotify_tools.FUNCTIONS, "spotify_tocando", playing)
    out = await victorique_tools.spotify("spotify_tocando", {})
    assert out == {"content": [{"type": "text", "text": "Tocando agora: Song — Band."}]}
    monkeypatch.setitem(spotify_tools.FUNCTIONS, "spotify_tocando", broken)
    out = await victorique_tools.spotify("spotify_tocando", {})
    assert out["is_error"] and "ponte" in out["content"][0]["text"]
    assert "mcp__victorique__spotify_tocar" in victorique_tools.VICTORIQUE_TOOL_NAMES


# ----------------- End to end through the app's WebSocket -----------------
def test_a_command_reaches_the_extension_over_the_websocket(client):
    token = app_bridge.token()
    results = {}
    with client.websocket_connect(f"/api/spotify/ws?t={token}", headers={"Origin": SPOTIFY_ORIGIN}) as ws:
        ws.send_text(json.dumps(report(token, track={"title": "Song", "artist": "Band"})))
        for _ in range(50):                                   # the server handles the report
            if app_bridge.linked and app_bridge.connected:
                break
            threading.Event().wait(0.02)
        worker = threading.Thread(target=lambda: results.update(
            out=asyncio.run(app_bridge.command("pause", {}, timeout=5))))
        worker.start()
        msg = json.loads(ws.receive_text())
        assert msg["cmd"] == "pause" and msg["args"] == {} and len(msg["id"]) == 16
        ws.send_text(json.dumps({"token": token, "reply": msg["id"], "ok": True, "result": {"now": None}}))
        worker.join(5)
    assert results["out"] == {"now": None}
    assert not app_bridge.linked                               # closed with the socket


# ----------------- Spicetify: updates, reopening, Windows' controls -----------------
RESTORE = ("\x1b[33mwarning\x1b[0m Preprocessed Spotify data is outdated. "
           "Please run \"spicetify restore backup apply\" to receive new features and bug fixes\r\n")


def test_install_runs_restore_backup_apply_after_a_spicetify_update(tmp_path):
    assert spicetify.recovery(RESTORE) == ["restore", "backup", "apply"]
    assert spicetify.recovery("error: Cannot find Spotify") is None
    cli = FakeCli(tmp_path / "config-xpui.ini", errors=[("apply", RESTORE)])
    result = spicetify.install(8765, "t", runner=cli, cli="spicetify")
    assert cli.calls[-2:] == [["apply"], ["restore", "backup", "apply"]]
    assert result["rebacked"]


def test_store_spotify_opened_from_the_start_menu_has_no_bridge(monkeypatch):
    monkeypatch.setattr(spicetify.os, "name", "nt")

    def ps(output):
        return lambda args, **kw: subprocess.CompletedProcess(args, 0, output, "")

    start_menu = json.dumps(['"C:\\WindowsApps\\Spotify.exe"', '"C:\\WindowsApps\\Spotify.exe" --type=gpu-process',
                             None])
    spicetified = json.dumps(["Spotify.exe --app-directory=C:\\spicetify\\AppX", "Spotify.exe --type=renderer"])
    assert spicetify.store_without_bridge(ps(start_menu))
    assert spicetify.store_without_bridge(ps(json.dumps('"C:\\WindowsApps\\Spotify.exe"')))   # just one
    assert not spicetify.store_without_bridge(ps(spicetified))
    assert not spicetify.store_without_bridge(ps(""))
    assert not spicetify.store_without_bridge(ps("not json"))
    launched = FakeCli("x")
    assert spicetify.launch(runner=launched, cli="spicetify") and launched.calls == [["restart"]]
    assert not spicetify.launch(runner=FakeCli("x", fail="restart"), cli="spicetify")


class _Controllable:
    def __init__(self, app):
        self.source_app_user_model_id = app
        self.done = []

    def __getattr__(self, name):
        if name.startswith("try_"):
            return lambda: self.done.append(name) or _Async(True)
        raise AttributeError(name)


def test_windows_media_controls_pause_and_skip_spotify_only(monkeypatch):
    other, spotify = _Controllable("Brave"), _Controllable("SpotifyAB.SpotifyMusic_x!Spotify")
    manager = _Manager([other, spotify])
    assert asyncio.run(nowplaying._smtc_control(manager, "try_skip_next_async")) is True
    assert spotify.done == ["try_skip_next_async"] and other.done == []
    assert asyncio.run(nowplaying._smtc_control(_Manager([other]), "try_pause_async")) is False
    monkeypatch.setattr(nowplaying.os, "name", "posix")
    assert nowplaying.smtc_control("pause") is None
    with pytest.raises(ValueError):
        nowplaying.smtc_control("explode")
