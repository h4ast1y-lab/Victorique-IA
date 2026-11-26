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
    assert b.status() == {"connected": True, "elements": MAX_ELEMENTS}
    b.disconnected()
    assert b.track() is None and not b.connected


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


def test_now_playing_prefers_the_bridge_then_the_other_readers(tmp_path):
    b = fresh_bridge(tmp_path)
    window = lambda: Track("Janela", "X", source="janela")    # noqa: E731
    assert nowplaying.current(b, [lambda: None, window]).source == "janela"
    b.receive(report("x", track={"title": "Ponte", "artist": "Y"}))
    assert nowplaying.current(b, [window]).title == "Ponte"
    assert nowplaying.title_track(lambda: [(1, "Spotify Premium"), (2, "Band - Song")]).title == "Song"


# ----------------- Spicetify installer -----------------
class FakeCli:
    def __init__(self, config, fail=None):
        self.config = config
        self.fail = fail
        self.calls = []

    def __call__(self, args, **kw):
        self.calls.append(args[1:])
        code = 1 if self.fail and args[1:2] == [self.fail] else 0
        out = f"{self.config}\n" if args[1:] == ["-c"] else "ok\n"
        return subprocess.CompletedProcess(args, code, out, "error: backup needed\n" if code else "")


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


def test_status_and_preferences(client):
    s = client.get("/api/spotify/status").json()
    assert {"connected", "elements", "track", "running", "spicetify"} <= set(s)
    prefs = client.get("/api/preferences").json()
    prefs = prefs.get("preferences", prefs)
    assert prefs["spotify_enabled"] is True and prefs["spotify_comments"] is True
