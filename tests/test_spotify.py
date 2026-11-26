"""Victorique no Spotify (app/spotify): ledges inside its window, the Spicetify
bridge, the track watcher, the installer and the API. No Windows, no Spotify:
windows, clock, readers and the Spicetify CLI are fakes."""
import json
import random
import subprocess
from pathlib import Path

import pytest

from app.life import generator, lines
from app.mascot.behavior import Brain
from app.mascot.desktop import DesktopMascot
from app.mascot.surfaces import WindowBox, build_world, window_hwnd
from app.spotify import layout, nowplaying, spicetify
from app.spotify.bridge import MAX_ELEMENTS, STALE, Bridge, bridge as app_bridge
from app.spotify.track import Track, from_window_title, make
from app.spotify.watcher import DWELL, SpotifyWatcher, TrackTracker

from test_mascot import AREA, H, Clock, FakeBridge, FakeLife, FakePresence, FakeWindow, _drag, tick

SPOTIFY_ORIGIN = "https://xpui.app.spotify.com"
MAXED = WindowBox(9, 0, 0, 1920, 1032, True, "spotify")
FLOATING = WindowBox(9, 300, 200, 1500, 900, False, "spotify")


class Ticker:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


def report(token, elements=(), view=(1920, 1032), track=None, playing=True):
    return {"token": token, "view": {"w": view[0], "h": view[1]}, "elements": list(elements),
            "track": track, "playing": playing}


def fresh_bridge(tmp_path, clock=None):
    return Bridge(path=tmp_path / "spotify_bridge.json", clock=clock or Ticker())


# ----------------- The track -----------------
def test_window_title_gives_artist_and_song_and_idle_titles_give_nothing():
    t = from_window_title("Daft Punk - Something About Us - Remastered")
    assert (t.artist, t.title, t.source) == ("Daft Punk", "Something About Us - Remastered", "janela")
    for idle in ("Spotify", "Spotify Premium", "Spotify Free", "Advertisement", ""):
        assert from_window_title(idle) is None
    assert make("Linha\x00um\nlinha dois", "A\tB").title == "Linha um linha dois"
    assert make("  ") is None
    assert Track("Song", "Band", "LP").facts() == {"musica": "Song", "artista": "Band", "album": "LP"}


# ----------------- Ledges inside the window -----------------
def test_maximized_spotify_keeps_its_player_bar_but_not_its_top_edge():
    w = build_world(AREA, H, [MAXED], lambda b: layout.ledges_for(b, 1.0, Bridge(clock=Ticker())))
    keys = {s.key for s in w.surfaces}
    assert "w9" not in keys                                   # no room above a maximized window
    assert "w9/player" in keys
    assert "w9/paineis" not in keys                           # 64 px from the top: no room for her
    player = w.segments("w9/player")[0]
    assert player.y == 1032 - layout.PLAYER_BAR and player.kind == "window"
    assert window_hwnd("w9/player") == 9 and window_hwnd("w9") == 9 and window_hwnd("ground") is None


def test_floating_spotify_has_its_top_edge_the_panels_and_the_player_bar():
    w = build_world(AREA, H, [FLOATING], lambda b: layout.ledges_for(b, 1.0, Bridge(clock=Ticker())))
    keys = {s.key for s in w.surfaces}
    assert {"w9", "w9/paineis", "w9/player"} <= keys
    assert w.segments("w9/paineis")[0].y == 200 + layout.TOP_BAR


def test_a_window_in_front_splits_the_ledge_and_other_apps_have_none():
    front = WindowBox(5, 800, 700, 1100, 1000)
    w = build_world(AREA, H, [front, MAXED], lambda b: layout.ledges_for(b, 1.0, Bridge(clock=Ticker())))
    spans = sorted((s.left, s.right) for s in w.segments("w9/player"))
    assert spans == [(0, 800), (1100, 1920)]
    assert layout.ledges_for(WindowBox(1, 0, 0, 900, 900), 1.0) == []


def test_bridge_elements_are_mapped_to_the_window_and_a_mismatch_falls_back(tmp_path):
    clock = Ticker()
    b = fresh_bridge(tmp_path, clock)
    box = WindowBox(9, 100, 50, 1350, 1050, False, "spotify")          # 1250 x 1000 px
    b.receive(report("x", [{"id": "c1", "kind": "card", "x": 100, "y": 200, "w": 200, "h": 260}],
                     view=(1000, 800)))                                 # scale 1.25 (DPI 120 %)
    (ledge,) = layout.ledges_for(box, 1.25, b)
    assert ledge.name == "card:c1"
    assert (ledge.left, ledge.right, ledge.y, ledge.bottom) == (225, 475, 300, 625)
    b.receive(report("x", [{"id": "c1", "kind": "card", "x": 1, "y": 1, "w": 50, "h": 50}],
                     view=(1000, 400)))                                 # another window's report
    assert [lg.name for lg in layout.ledges_for(box, 1.0, b)] == ["paineis", "player"]
    clock.t += STALE + 1                                                # Spotify went quiet
    assert b.view() is None


def test_she_lands_on_a_cover_and_rides_it_when_the_page_scrolls(tmp_path):
    clock = Clock()
    b = fresh_bridge(tmp_path, clock)

    def world_with(card_y):
        b.receive(report("x", [{"id": "c1", "kind": "card", "x": 600, "y": card_y, "w": 220, "h": 280}]))
        return build_world(AREA, H, [MAXED], lambda box: layout.ledges_for(box, 1.0, b))

    brain = Brain(random.Random(3))
    w = world_with(400)
    brain.place(w, clock.t)
    brain.grab(clock.t)
    brain.drag_to(700 + H * 0.3, 200 - H * 0.5)
    brain.drag_to(700 + H * 0.3, 200 - H * 0.5)
    brain.release(clock.t)
    for _ in range(200):
        clock.t += 0.02
        brain.step(0.02, clock.t, w)
        if brain.mode == "land":
            break
    assert brain.surface_key.startswith("w9/card:") and brain.y == 400
    assert brain.on_window() == brain.surface_key
    w = world_with(350)                                                  # scrolled up 50 px
    clock.t += 0.04
    brain.step(0.04, clock.t, w, walk=False)
    assert brain.y == 350 and brain.surface_key.startswith("w9/card:")


# ----------------- The desktop mascot -----------------
def make_mascot(prefs=None, windows=(), ledges_fn=None):
    clock = Clock()
    cursor = {"pos": (0, 0)}
    state = {"prefs": dict(prefs or {}), "windows": list(windows), "reads": []}

    def one_window(hwnd):
        state["reads"].append(hwnd)
        w = next((w for w in state["windows"] if w.hwnd == hwnd), None)
        # Like win32.window_box: the per-tick read does not know the app.
        return WindowBox(w.hwnd, w.left, w.top, w.right, w.bottom, w.maximized) if w else None

    m = DesktopMascot(
        FakeBridge(), prefs_loader=lambda: state["prefs"],
        prefs_saver=lambda changes: state["prefs"].update(changes), life=FakeLife(),
        window_factory=FakeWindow, area_fn=lambda x, y: (AREA, 1.0), cursor_fn=lambda: cursor["pos"],
        foreground_fn=lambda: None, windows_fn=lambda exclude=(): list(state["windows"]),
        window_box_fn=one_window,
        ledges_fn=ledges_fn or (lambda box, dpi: layout.ledges_for(box, dpi, Bridge(clock=Ticker()))),
        clock=clock, rng=random.Random(5), presence=FakePresence(),
    )
    return m, clock, cursor, state


def test_dropped_over_maximized_spotify_she_stands_on_its_player_bar():
    m, clock, cursor, state = make_mascot(windows=[MAXED])
    tick(m, clock)
    _drag(m, clock, cursor, (900, 300), steps=1)
    tick(m, clock, 60)
    assert m.brain.surface_key == "w9/player" and m.brain.y == 1032 - layout.PLAYER_BAR
    tick(m, clock, 20)
    # The window under her is re-read every tick by its handle, and stays Spotify's.
    assert 9 in state["reads"] and m._windows[0].app == "spotify"
    assert m.brain.surface_key == "w9/player"


def test_spotify_ledges_follow_the_preferences():
    for prefs in ({"spotify_enabled": False}, {"mascot_climb": False}):
        m, clock, cursor, _s = make_mascot(prefs=prefs, windows=[MAXED])
        tick(m, clock)
        _drag(m, clock, cursor, (900, 300), steps=1)
        tick(m, clock, 80)
        assert m.brain.surface_key == "ground"


# ----------------- The bridge -----------------
def test_bridge_token_is_kept_and_checked(tmp_path):
    b = fresh_bridge(tmp_path)
    token = b.token()
    assert len(token) >= 32 and b.check(token) and not b.check("x" * 43) and not b.check(None)
    assert Bridge(path=tmp_path / "spotify_bridge.json").token() == token     # same after restart


def test_bridge_rejects_bad_reports_and_cleans_what_it_keeps(tmp_path):
    clock = Ticker()
    b = fresh_bridge(tmp_path, clock)
    token = b.token()
    assert not b.receive_text(json.dumps(report("errado")))
    assert not b.receive_text("{not json")
    assert not b.receive_text("x" * 70_000)
    elements = [{"id": f"a/{i}", "kind": "card", "x": 10, "y": 10 * i, "w": 100, "h": 100} for i in range(80)]
    elements += [{"id": "z", "kind": "script", "x": 1, "y": 1, "w": 100, "h": 100},
                 {"id": "y", "kind": "tab", "x": "1", "y": 1, "w": 100, "h": 100}]
    track = {"title": "Song", "artist": "Band", "album": "LP"}
    assert b.receive_text(json.dumps(report(token, elements, track=track)))
    view = b.view()
    assert len(view.elements) == MAX_ELEMENTS
    assert all("/" not in e.id and e.kind == "card" for e in view.elements)
    assert b.track() == Track("Song", "Band", "LP", True, "spicetify")
    assert b.status() == {"connected": True, "elements": MAX_ELEMENTS, "kinds": {"card": MAX_ELEMENTS},
                          "reports": 1}
    detail = b.status(detail=True)
    assert detail["view"] == {"w": 1920, "h": 1032} and len(detail["items"]) == MAX_ELEMENTS
    b.disconnected()
    assert b.track() is None and not b.connected
    assert b.status(detail=True) == {"connected": False, "elements": 0, "kinds": {}, "reports": 1}


def test_bridge_refuses_a_non_ascii_token_instead_of_crashing(tmp_path):
    b = fresh_bridge(tmp_path)
    b.token()
    assert b.check("çãéü" * 11) is False                    # compare_digest raises on str here
    assert not b.receive_text(json.dumps(report("çãéü" * 11)))


def test_bridge_keeps_a_tab_and_a_card_that_share_an_id(tmp_path):
    b = fresh_bridge(tmp_path)
    same = [{"id": "abc", "kind": "tab", "x": 10, "y": 10, "w": 100, "h": 30},
            {"id": "abc", "kind": "card", "x": 10, "y": 300, "w": 200, "h": 250},
            {"id": "abc", "kind": "card", "x": 400, "y": 300, "w": 200, "h": 250}]
    b.receive(report("x", same))
    assert [(e.kind, e.id) for e in b.view().elements] == [("tab", "abc"), ("card", "abc")]


# ----------------- The track watcher -----------------
def test_tracker_offers_a_track_once_after_it_really_played():
    t = TrackTracker()
    song, other = Track("Song", "Band"), Track("Other", "Band")
    assert t.update(song, 0) is None
    assert t.update(song, 4) is None
    assert t.update(Track("Song", "Band", playing=False), 10) is None     # paused: the clock stops
    assert t.update(song, 60) is None
    offered = None
    for now in range(62, 80, 2):
        offered = offered or t.update(song, now)
    assert offered == song
    assert t.update(song, 90) is None                                     # once
    t.update(other, 100)
    t.update(other, 100 + DWELL / 2)
    assert t.update(song, 120) is None                                    # skipped `other`
    for now in range(122, 160, 2):
        assert t.update(song, now) is None                                # `song` already offered


def test_watcher_tells_the_vida_propria_and_respects_the_switches():
    clock = Ticker(0)
    prefs = {"spotify_enabled": True, "spotify_comments": True}
    reads, said = [], []

    def reader():
        reads.append(1)
        return Track("Clair de Lune", "Debussy", "Suite bergamasque")

    w = SpotifyWatcher(prefs_loader=lambda: prefs, reader=reader,
                       notify=lambda c, f: said.append((c, f)), clock=clock)
    for _ in range(15):
        w.poll()
        clock.t += 2
    assert said == [("musica", {"musica": "Clair de Lune", "artista": "Debussy", "album": "Suite bergamasque"})]
    assert w.status()["track"]["title"] == "Clair de Lune"
    prefs["spotify_comments"] = False
    n = len(reads)
    w.poll()
    assert len(reads) == n and w.status()["track"] is None
    prefs.update(spotify_comments=True, life_comments=False)           # nobody to tell
    w.poll()
    assert len(reads) == n


def test_walking_off_in_spotify_does_not_silence_her_comments():
    clock = Ticker(0)
    said = []
    w = SpotifyWatcher(prefs_loader=lambda: {"spotify_enabled": False, "spotify_comments": True},
                       reader=lambda: Track("Song", "Band"), notify=lambda c, f: said.append(c), clock=clock)
    for _ in range(15):
        w.poll()
        clock.t += 2
    assert said == ["musica"]


class _Async:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        if False:
            yield
        return self.value


class _Session:
    def __init__(self, app, title, artist="", album="", status=4):
        self.source_app_user_model_id = app
        self._props = type("P", (), {"title": title, "artist": artist, "album_title": album})()
        self._info = type("I", (), {"playback_status": status})()

    def try_get_media_properties_async(self):
        return _Async(self._props)

    def get_playback_info(self):
        return self._info


class _Manager:
    def __init__(self, sessions):
        self.sessions = sessions

    def request_async(self):
        return _Async(type("M", (), {"get_sessions": lambda _self: self.sessions})())


def test_windows_media_controls_read_only_spotify_and_skip_ads():
    import asyncio
    store_app = "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
    other = _Session("Brave", "Um vídeo", "Canal")
    playing = _Manager([other, _Session(store_app, "Sob o Luar", "Novatroop", "Sob o Luar", 4)])
    t = asyncio.run(nowplaying._smtc_read(playing))
    assert (t.title, t.artist, t.album, t.playing, t.source) == ("Sob o Luar", "Novatroop", "Sob o Luar", True, "smtc")
    paused = _Manager([_Session("Spotify.exe", "Song", "Band", status=5)])
    assert asyncio.run(nowplaying._smtc_read(paused)).playing is False
    for ad in ("Advertisement", "Spotify"):
        assert asyncio.run(nowplaying._smtc_read(_Manager([_Session(store_app, ad)]))) is None
    assert asyncio.run(nowplaying._smtc_read(_Manager([other]))) is None


def test_now_playing_prefers_the_bridge_then_the_other_readers(tmp_path):
    b = fresh_bridge(tmp_path)
    window = lambda: Track("Janela", "X", source="janela")    # noqa: E731
    assert nowplaying.current(b, [lambda: None, window]).source == "janela"
    b.receive(report("x", track={"title": "Ponte", "artist": "Y"}))
    assert nowplaying.current(b, [window]).title == "Ponte"
    assert nowplaying.title_track(lambda: [(1, "Spotify Premium"), (2, "Band - Song")]).title == "Song"


# ----------------- Spicetify installer -----------------
class FakeCli:
    def __init__(self, config, fail=None, errors=None):
        self.config = config
        self.fail = fail
        self.errors = list(errors or [])     # (command, stdout) answered once each, with exit 1
        self.calls = []
        self.kwargs = []

    def __call__(self, args, **kw):
        self.calls.append(args[1:])
        self.kwargs.append(kw)
        if self.errors and args[1:2] == [self.errors[0][0]]:
            _cmd, out = self.errors.pop(0)
            return subprocess.CompletedProcess(args, 1, out, "")
        code = 1 if self.fail and args[1:2] == [self.fail] else 0
        out = f"{self.config}\n" if args[1:] == ["-c"] else "ok\n"
        return subprocess.CompletedProcess(args, code, out, "error: backup needed\n" if code else "")


STOCK = ("\x1b[33mwarning\x1b[0m Spotify version and backup version are mismatched.\r\n"
         "\x1b[36minfo\x1b[0m Spotify client is in stock state\r\n"
         "\x1b[36minfo\x1b[0m Please run \"spicetify backup apply\"\r\n")


def test_install_redoes_the_backup_when_spotify_updated(tmp_path):
    cli = FakeCli(tmp_path / "spicetify" / "config-xpui.ini", errors=[("apply", STOCK)])
    result = spicetify.install(8765, "t", runner=cli, cli="spicetify")
    assert cli.calls[-2:] == [["apply"], ["backup", "apply"]]
    assert cli.kwargs[-1]["input"] == "y\n"                     # its Microsoft Store warning
    assert result["rebacked"] and "backup" in result["message"]
    assert "stdin" in cli.kwargs[-2] and "input" not in cli.kwargs[-2]   # no prompt ever hangs


def test_install_does_not_touch_the_backup_for_other_errors_and_strips_colours(tmp_path):
    cli = FakeCli(tmp_path / "config-xpui.ini", errors=[("apply", "\x1b[31merror\x1b[0m Cannot find Spotify\r\n")])
    with pytest.raises(spicetify.SpicetifyError) as caught:
        spicetify.install(8765, "t", runner=cli, cli="spicetify")
    assert ["backup", "apply"] not in cli.calls
    assert "\x1b" not in str(caught.value) and "Cannot find Spotify" in str(caught.value)


def test_cli_runs_without_a_console_window_and_in_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(spicetify.os, "name", "nt")
    monkeypatch.setattr(spicetify.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    cli = FakeCli(tmp_path / "config-xpui.ini")
    spicetify.install(8765, "t", runner=cli, cli="spicetify")
    for kw in cli.kwargs:
        assert kw["creationflags"] == 0x08000000 and kw["encoding"] == "utf-8" and kw["errors"] == "replace"


def test_install_does_not_list_the_extension_twice(tmp_path):
    config = tmp_path / "config-xpui.ini"
    config.write_text("[Setting]\nspotify_path = C:\\x\n\n[AdditionalOptions]\n"
                      "extensions = other.js|victorique.js\n", encoding="utf-8")
    cli = FakeCli(config)
    spicetify.install(8765, "t", runner=cli, cli="spicetify")
    assert cli.calls == [["-c"], ["apply"]]


def test_uninstall_takes_the_bridge_out(tmp_path):
    config = tmp_path / "config-xpui.ini"
    config.write_text("[AdditionalOptions]\nextensions = victorique.js\n", encoding="utf-8")
    (tmp_path / "Extensions").mkdir()
    (tmp_path / "Extensions" / "victorique.js").write_text("x", encoding="utf-8")
    cli = FakeCli(config)
    assert spicetify.uninstall(runner=cli, cli="spicetify")["ok"]
    assert cli.calls == [["-c"], ["config", "extensions", "victorique.js-"], ["apply"]]
    assert not (tmp_path / "Extensions" / "victorique.js").exists()
    # Spotify already back to stock (it updated): nothing left to take out, not an error.
    cli = FakeCli(config, errors=[("apply", STOCK)])
    assert spicetify.uninstall(runner=cli, cli="spicetify")["ok"]


def test_state_says_installed_current_store_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(spicetify, "store_spotify", lambda: False)
    config = tmp_path / "config-xpui.ini"
    gone = tmp_path / "WindowsApps" / "SpotifyAB.SpotifyMusic_1.303.264.0_x64__zpdnekdrzrea0"
    config.write_text(f"[Setting]\nspotify_path = {gone}\n\n[AdditionalOptions]\nextensions = victorique.js\n",
                      encoding="utf-8")
    cli = FakeCli(config)
    s = spicetify.state(8765, "tok", cli="spicetify", runner=cli)
    assert s == {"spicetify": True, "installed": False, "current": False, "store": True, "stale_path": True}
    (tmp_path / "Extensions").mkdir()
    (tmp_path / "Extensions" / "victorique.js").write_text(spicetify.render(8765, "tok"), encoding="utf-8")
    s = spicetify.state(8765, "tok", cli="spicetify", runner=cli)
    assert s["installed"] and s["current"]
    assert not spicetify.state(8777, "tok", cli="spicetify", runner=cli)["current"]   # other port
    monkeypatch.setattr(spicetify, "find_cli", lambda: None)
    assert spicetify.state(8765, "tok", runner=cli)["spicetify"] is False


def test_install_writes_the_extension_next_to_the_config_and_applies(tmp_path):
    cli = FakeCli(tmp_path / "spicetify" / "config-xpui.ini")
    result = spicetify.install(8765, "segredo", runner=cli, cli="spicetify")
    target = tmp_path / "spicetify" / "Extensions" / "victorique.js"
    assert Path(result["path"]) == target and result["ok"]
    text = target.read_text(encoding="utf-8")
    assert "const PORT = 8765;" in text and 'const TOKEN = "segredo";' in text and "__PORT__" not in text and "__TOKEN__" not in text
    assert cli.calls == [["-c"], ["config", "extensions", "victorique.js"], ["apply"]]


def test_install_reports_failures_plainly(tmp_path, monkeypatch):
    cli = FakeCli(tmp_path / "config-xpui.ini", fail="apply")
    with pytest.raises(spicetify.SpicetifyError, match="backup apply"):
        spicetify.install(8765, "t", runner=cli, cli="spicetify")
    monkeypatch.setattr(spicetify, "find_cli", lambda: None)
    with pytest.raises(spicetify.SpicetifyError, match="Spicetify"):
        spicetify.install(8765, "t", runner=cli)


# ----------------- Her line about the track -----------------
def test_music_is_a_moment_with_its_own_bank_lines():
    assert "musica" in generator.MOMENTS and "musica" in lines.CATEGORIES
    bank = lines.load_bank()
    assert bank["musica"]
    facts = {"musica": "Clair de Lune", "artista": "Debussy"}
    for entry in bank["musica"]:
        text = lines.fill(entry, facts)
        assert "{" not in text and ("Clair de Lune" in text or "Debussy" in text)


# ----------------- API -----------------
def test_bridge_endpoint_accepts_spotify_with_the_token_only(client):
    token = app_bridge.token()
    body = json.dumps(report(token, [{"id": "p", "kind": "player", "x": 0, "y": 950, "w": 1920, "h": 80}]))
    r = client.post("/api/spotify/bridge", content=body,
                    headers={"Origin": SPOTIFY_ORIGIN, "Content-Type": "text/plain"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == SPOTIFY_ORIGIN
    assert app_bridge.status()["connected"]
    r = client.post("/api/spotify/bridge", content=json.dumps(report("errado")),
                    headers={"Origin": SPOTIFY_ORIGIN})
    assert r.status_code == 403
    r = client.post("/api/spotify/bridge", content=body, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/life/status", headers={"Origin": SPOTIFY_ORIGIN})        # only the bridge
    assert r.status_code == 403
    r = client.options("/api/spotify/bridge", headers={"Origin": SPOTIFY_ORIGIN,
                                                       "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 204 and r.headers["access-control-allow-private-network"] == "true"
    app_bridge.disconnected()


def test_bridge_websocket_needs_the_token(client):
    from starlette.websockets import WebSocketDisconnect
    token = app_bridge.token()
    with client.websocket_connect(f"/api/spotify/ws?t={token}", headers={"Origin": SPOTIFY_ORIGIN}) as ws:
        ws.send_text(json.dumps(report(token, track={"title": "Song", "artist": "Band"})))
        ws.send_text("{}")                                           # ignored, the channel stays open
        ws.send_text(json.dumps(report(token, track={"title": "Song 2", "artist": "Band"})))
    assert not app_bridge.connected                                 # closed: no longer fresh
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/spotify/ws?t=errado") as ws:
            ws.receive_text()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/spotify/ws?t={token}", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_text()


def test_bridge_endpoint_refuses_a_bad_token_and_a_huge_body_without_crashing(client):
    r = client.post("/api/spotify/bridge", content=json.dumps(report("çãéü" * 11)),
                    headers={"Origin": SPOTIFY_ORIGIN})
    assert r.status_code == 403
    r = client.post("/api/spotify/bridge", content="x" * 70_000, headers={"Origin": SPOTIFY_ORIGIN})
    assert r.status_code == 413


def _no_real_spotify(monkeypatch):
    """The status reads Spicetify, the Spotify window and Windows' media
    controls: none of the real ones in tests."""
    monkeypatch.setattr(spicetify, "find_cli", lambda: None)
    monkeypatch.setattr(spicetify, "store_spotify", lambda: False)
    monkeypatch.setattr(nowplaying, "spotify_windows", lambda: [])
    monkeypatch.setattr(nowplaying, "current", lambda *a, **k: None)


def test_status_and_preferences(client, monkeypatch):
    _no_real_spotify(monkeypatch)
    s = client.get("/api/spotify/status").json()
    assert {"connected", "elements", "track", "running", "spicetify", "installed", "current",
            "store", "stale_path", "open"} <= set(s)
    assert s["spicetify"] is False and s["open"] is False and s["track"] is None
    prefs = client.get("/api/preferences").json()
    prefs = prefs.get("preferences", prefs)
    assert prefs["spotify_enabled"] is True and prefs["spotify_comments"] is True


def test_status_reads_the_track_itself_when_the_watcher_is_not(client, monkeypatch):
    _no_real_spotify(monkeypatch)
    monkeypatch.setattr(nowplaying, "current", lambda *a, **k: Track("Sob o Luar", "Novatroop", source="smtc"))
    s = client.get("/api/spotify/status").json()
    assert s["track"]["title"] == "Sob o Luar" and s["track"]["source"] == "smtc"


def test_uninstall_endpoint_reports_a_missing_spicetify(client, monkeypatch):
    _no_real_spotify(monkeypatch)
    r = client.post("/api/spotify/spicetify/uninstall")
    assert r.status_code == 400 and "Spicetify" in r.json()["detail"]


# ----------------- The lines bank of an older install -----------------
def test_an_older_bank_gets_the_new_section_once_keeping_its_line_endings(tmp_path):
    old = "# Falas\r\n\r\n## tarde\r\n- {hora}, minha.\r\n\r\n## tedio\r\n- A :: B :: C\r\n"
    path = tmp_path / "falas.md"
    path.write_bytes(old.encode("utf-8"))
    lines.ensure_bank(path)
    data = path.read_bytes()
    assert data.startswith(old.encode("utf-8"))                  # the user's lines untouched
    text = data.decode("utf-8")
    assert "## musica" in text and "## bagunca" in text and "\n" not in text.replace("\r\n", "")
    bank = lines.parse_bank(text)
    assert bank["tarde"] == ["{hora}, minha."] and bank["musica"] == lines.parse_bank(
        lines.FACTORY_FILE.read_text(encoding="utf-8"))["musica"]
    lines.ensure_bank(path)
    assert path.read_bytes() == data                             # only once


def test_lines_with_every_marker_filled_are_preferred():
    bank = {"musica": ["{musica}, de {artista}.", "Então é {musica} agora."]}
    for _ in range(20):
        assert lines.pick("musica", {"musica": "Podcast X"}, [], bank)["fala"] == "Então é Podcast X agora."
    bank = {"retorno": ["Ah, {nome}, voltou depois de {minutos}."]}
    assert lines.pick("retorno", {"minutos": "uma hora"}, [], bank)["fala"] == "Ah, voltou depois de uma hora."
