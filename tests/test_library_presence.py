"""Uma Victorique só: o servidor sabe se ela está na área de trabalho ou na Biblioteca."""
from app.library import presence as presence_mod
from app.library.presence import Presence


class FakeBus:
    def __init__(self, visible=True):
        self.visible = visible
        self.commands = []

    def command(self, action):
        self.commands.append(action)
        return True


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(visible=True):
    bus, clock = FakeBus(visible), FakeClock()
    return Presence(clock=clock, bus=bus), bus, clock


def test_starts_on_the_desktop():
    p, bus, _ = make()
    snap = p.snapshot()
    assert snap["state"] == "desktop" and snap["hall_open"] is False
    assert bus.commands == []


def test_enter_with_visible_mascot_waits_for_the_door():
    p, bus, clock = make(visible=True)
    assert p.enter("aba")["state"] == "entrando"
    assert bus.commands == ["enter-library"]
    p.mascot_left()
    assert p.snapshot()["state"] == "biblioteca"


def test_enter_without_mascot_goes_straight_in():
    p, bus, clock = make(visible=False)
    assert p.enter("aba")["state"] == "biblioteca"
    assert bus.commands == ["enter-library"]        # a hidden mascot vanishes at once


def test_door_timeout_finishes_entering_and_leaving():
    p, bus, clock = make(visible=True)
    p.set_hall_open(True)
    clock.t += 6.1
    assert p.tick()["state"] == "entrando"            # still walking to her door on the desktop
    clock.t += 24
    assert p.tick()["state"] == "biblioteca"
    p.leave("aba")                                    # tab open: the hall plays the exit
    assert p.snapshot()["state"] == "saindo"
    clock.t += 6.1
    assert p.tick()["state"] == "desktop"
    assert bus.commands[-1] == "return-from-library"


def test_closing_the_tab_returns_her_at_once():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    assert p.set_hall_open(False)["state"] == "desktop"
    assert bus.commands == ["enter-library", "return-from-library"]


def test_left_hall_completes_the_exit():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    p.leave("menu")
    p.left_hall()
    assert p.snapshot()["state"] == "desktop"
    assert bus.commands[-1] == "return-from-library"


def test_work_with_the_tab_closed_sends_her_out_of_sight_and_announces():
    p, bus, clock = make(visible=True)
    p.note_work()
    snap = p.snapshot()
    assert snap["state"] == "entrando" and snap["out_of_sight"] and snap["reason"] == "trabalho"
    assert bus.commands == ["enter-library-announce"]


def test_out_of_sight_returns_after_30s_without_work_and_work_renews_it():
    p, bus, clock = make(visible=False)
    p.note_work()
    clock.t += 20
    p.note_work()
    clock.t += 20
    assert p.tick()["state"] == "biblioteca"
    clock.t += 11
    assert p.tick()["state"] == "desktop"


def test_open_tab_idle_for_five_minutes_sends_her_home():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    clock.t += 299
    assert p.tick()["state"] == "biblioteca"
    clock.t += 2
    assert p.tick()["state"] == "saindo"


def test_leave_while_entering_cancels_and_enter_while_leaving_stays():
    p, bus, clock = make(visible=True)
    p.enter("aba")
    p.leave("aba")
    assert p.snapshot()["state"] == "desktop"
    assert bus.commands == ["enter-library", "return-from-library"]
    p2, bus2, _ = make(visible=False)
    p2.set_hall_open(True)
    p2.leave("menu")
    assert p2.enter("aba")["state"] == "biblioteca"


def test_opening_the_tab_after_work_brings_her_into_view():
    p, bus, clock = make(visible=False)
    p.note_work()
    assert p.set_hall_open(True)["out_of_sight"] is False


def test_leave_on_the_desktop_does_nothing():
    p, bus, clock = make()
    assert p.leave("aba")["state"] == "desktop"
    assert bus.commands == []


def test_closing_the_tab_during_the_exit_finishes_it_at_once():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    p.leave("menu")
    assert p.set_hall_open(False)["state"] == "desktop"
    assert bus.commands[-1] == "return-from-library"


# ----------------- Wired to the activity and the routes -----------------
def test_recording_shelf_work_notifies_presence(monkeypatch, library):
    from app.library import activity
    calls = []
    monkeypatch.setattr(presence_mod.presence, "note_work", lambda: calls.append(1))
    book = library["home"] / "Downloads" / "a.txt"
    book.write_text("x")
    activity.record("read", str(book))
    activity.record("read", str(library["root"] / "fora.txt"))   # not on any shelf
    assert calls == [1]


def test_activity_route_carries_presence(client, monkeypatch):
    monkeypatch.setattr(presence_mod, "presence", Presence(bus=FakeBus(visible=False)))
    data = client.get("/api/library/activity?since=0").json()
    assert data["presence"]["state"] == "desktop"


def test_presence_route_opens_and_closes_the_hall(client, monkeypatch):
    p = Presence(bus=FakeBus(visible=False))
    monkeypatch.setattr(presence_mod, "presence", p)
    assert client.post("/api/library/presence", json={"hall_open": True}).json()["state"] == "biblioteca"
    assert client.post("/api/library/presence", json={"hall_open": False}).json()["state"] == "desktop"


def test_presence_route_calls_her_and_hears_she_left(client, monkeypatch):
    p = Presence(bus=FakeBus(visible=False))
    monkeypatch.setattr(presence_mod, "presence", p)
    assert client.post("/api/library/presence", json={"hall_open": True}).json()["state"] == "biblioteca"
    p.leave("menu")
    assert client.post("/api/library/presence", json={"left_hall": True}).json()["state"] == "desktop"
    assert client.post("/api/library/presence", json={"enter": True}).json()["state"] == "biblioteca"
