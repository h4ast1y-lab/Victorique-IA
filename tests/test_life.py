"""Vida própria: portões, limites, gatilhos, banco de falas, geração e API."""
import asyncio
import time

import pytest

from app.core import preferences
from app.life import folders, generator, lines
from app.life.policy import (
    AWAY_AFTER, RETURN_AFTER, LifeConfig, LifePolicy, Signals, is_late, night_key,
)
from app.life.service import LifeService

NOON = time.mktime((2026, 11, 23, 12, 0, 0, 0, 0, -1))
LATE = time.mktime((2026, 11, 24, 1, 30, 0, 0, 0, -1))


def cfg(**kw):
    base = dict(boredom=True, comments=True, boredom_min=20, boredom_max=20,
                max_per_hour=2, min_gap=15, dnd=False, quiet_apps={"zoom.exe"})
    base.update(kw)
    return LifeConfig(**base)


def sig(now=NOON, **kw):
    base = dict(now=now, app_idle=0.0, system_idle=10.0, foreground=None)
    base.update(kw)
    return Signals(**base)


# ---------------- policy: gates ----------------
@pytest.mark.parametrize("change,reason", [
    (dict(cfg=dict(boredom=False, comments=False)), "desligada"),
    (dict(cfg=dict(dnd=True)), "nao_perturbe"),
    (dict(sig=dict(system_idle=AWAY_AFTER + 1)), "ausente"),
    (dict(sig=dict(visible=False)), "oculta"),
    (dict(sig=dict(settings_open=True)), "configuracoes"),
    (dict(sig=dict(generating=True)), "ocupada"),
    (dict(sig=dict(typing=True)), "digitando"),
    (dict(sig=dict(foreground={"process": "game.exe", "fullscreen": True, "own": False})), "tela_cheia"),
    (dict(sig=dict(foreground={"process": "Zoom.exe", "fullscreen": False, "own": False})), "app_calado"),
])
def test_each_gate_blocks(change, reason):
    policy = LifePolicy()
    assert policy.gate(sig(**change.get("sig", {})), cfg(**change.get("cfg", {}))) == reason


def test_own_fullscreen_window_does_not_block():
    fg = {"process": "python.exe", "fullscreen": True, "own": True}
    assert LifePolicy().gate(sig(foreground=fg), cfg()) == "pronta"


def test_silence_blocks_until_it_ends_and_resume_lifts_it():
    policy = LifePolicy()
    policy.silence(120, NOON)
    assert policy.gate(sig(), cfg()) == "silencio"
    assert policy.gate(sig(now=NOON + 121 * 60), cfg()) == "pronta"
    policy.silence(120, NOON)
    policy.resume()
    assert policy.gate(sig(), cfg()) == "pronta"


def test_min_gap_hourly_cap_and_attempt_cooldown():
    policy = LifePolicy()
    c = cfg(max_per_hour=2, min_gap=5)
    policy.delivered({"category": "retorno", "facts": {}}, "a", sig(), c)
    assert policy.gate(sig(now=NOON + 60), c) == "intervalo"
    policy.delivered({"category": "retorno", "facts": {}}, "b", sig(now=NOON + 6 * 60), c)
    assert policy.gate(sig(now=NOON + 12 * 60), c) == "limite_hora"
    assert policy.gate(sig(now=NOON + 61 * 60), c) == "pronta"
    policy.attempted(NOON + 61 * 60)
    assert policy.gate(sig(now=NOON + 61 * 60 + 30), c) == "tentativa"


def test_forced_lines_do_not_count_toward_limits():
    policy = LifePolicy()
    policy.delivered({"category": "tedio", "facts": {}}, "teste", sig(), cfg(), forced=True)
    assert policy.gate(sig(now=NOON + 1), cfg()) == "pronta"
    assert policy.state["recent"] == ["teste"]


# ---------------- policy: triggers ----------------
def test_boredom_after_threshold_and_only_once_per_idle_stretch():
    policy = LifePolicy()
    c = cfg(boredom_min=20, boredom_max=20, comments=False)
    policy.observe(sig(), c)
    assert policy.candidate(sig(app_idle=19 * 60), c) is None
    s = sig(app_idle=21 * 60)
    candidate = policy.candidate(s, c)
    assert candidate["category"] == "tedio"
    policy.delivered(candidate, "enigma", s, c)
    later = sig(now=NOON + 3600, app_idle=21 * 60 + 3600)
    assert policy.candidate(later, c) is None          # still the same idle stretch
    after_activity = sig(now=NOON + 3 * 3600, app_idle=21 * 60)
    assert policy.candidate(after_activity, c)["category"] == "tedio"


def test_boredom_range_is_respected():
    policy = LifePolicy()
    c = cfg(boredom_min=20, boredom_max=45)
    for _ in range(20):
        policy._resample_boredom(c)
        assert 20 * 60 <= policy.state["boredom_threshold"] <= 45 * 60


def test_return_after_long_absence():
    policy = LifePolicy()
    c = cfg()
    policy.observe(sig(system_idle=RETURN_AFTER + 100), c)
    policy.observe(sig(now=NOON + 20, system_idle=3), c)
    candidate = policy.candidate(sig(now=NOON + 20, system_idle=3), c)
    assert candidate["category"] == "retorno"
    assert candidate["facts"]["ausencia"] >= RETURN_AFTER


def test_short_absence_is_not_a_return():
    policy = LifePolicy()
    c = cfg(boredom=False)
    policy.observe(sig(system_idle=10 * 60), c)
    policy.observe(sig(now=NOON + 20, system_idle=3), c)
    assert policy.candidate(sig(now=NOON + 20, system_idle=3), c) is None


def test_reopening_the_app_after_hours_counts_as_return():
    policy = LifePolicy({"last_presence": NOON - 8 * 3600})
    policy.observe(sig(), cfg())
    assert policy.candidate(sig(), cfg())["category"] == "retorno"


def test_late_night_once_per_night():
    assert is_late(LATE) and not is_late(NOON)
    assert night_key(LATE) == "2026-11-23"
    policy = LifePolicy()
    c = cfg(boredom=False)
    candidate = policy.candidate(sig(now=LATE), c)
    assert candidate["category"] == "tarde"
    policy.delivered(candidate, "vá dormir", sig(now=LATE), c)
    assert policy.candidate(sig(now=LATE + 3 * 3600), c) is None


def test_organizer_event_is_queued_and_expires():
    policy = LifePolicy()
    c = cfg(boredom=False)
    policy.notify("organizado", {"n": 7}, NOON)
    assert policy.candidate(sig(), c)["category"] == "organizado"
    policy.notify("organizado", {"n": 7}, NOON)
    assert policy.candidate(sig(now=NOON + 11 * 60), c) is None


def test_messy_folder_is_commented_once_a_week():
    policy = LifePolicy()
    c = cfg(boredom=False)
    found = [{"path": "C:/x/Downloads", "pasta": "Downloads", "n": 40, "tipos": ["pdf"]}]
    candidate = policy.candidate(sig(), c, scan_folders=lambda: found)
    assert candidate["category"] == "bagunca"
    policy.delivered(candidate, "que bagunça", sig(), c)
    policy.state["last_scan"] = 0
    assert policy.candidate(sig(now=NOON + 3 * 86400), c, scan_folders=lambda: found) is None
    policy.state["last_scan"] = 0
    assert policy.candidate(sig(now=NOON + 8 * 86400), c, scan_folders=lambda: found)


def test_comments_off_keeps_only_boredom():
    policy = LifePolicy()
    c = cfg(comments=False)
    policy.notify("organizado", {"n": 7}, NOON)
    assert policy.candidate(sig(now=LATE), c) is None


def test_state_survives_restore():
    policy = LifePolicy()
    policy.delivered({"category": "retorno", "facts": {}}, "olá", sig(), cfg())
    copy = LifePolicy(policy.snapshot())
    assert copy.state["recent"] == ["olá"]
    assert copy.gate(sig(now=NOON + 60), cfg()) == "intervalo"


def test_config_from_prefs():
    prefs = preferences.defaults()
    prefs.update(life_boredom_min=50, life_boredom_max=30, life_quiet_apps="Zoom; obs64.exe")
    c = LifeConfig.from_prefs(prefs)
    assert (c.boredom_min, c.boredom_max) == (30, 50)
    assert c.quiet_apps == {"zoom.exe", "obs64.exe"}


# ---------------- folders ----------------
def test_messy_folders_counts_only_loose_files(tmp_path):
    messy = tmp_path / "Downloads"
    messy.mkdir()
    for i, ext in enumerate(["pdf", "jpg", "zip", "docx", "mp3"] * 6):
        (messy / f"arquivo{i}.{ext}").write_text("x")
    tidy = tmp_path / "Arrumada"
    (tidy / "sub").mkdir(parents=True)
    for i in range(40):
        (tidy / "sub" / f"a{i}.txt").write_text("x")
    (tmp_path / "_Quarentena").mkdir()
    found = folders.messy_folders([tmp_path])
    assert [f["pasta"] for f in found] == ["Downloads"]
    assert found[0]["n"] == 30 and len(found[0]["tipos"]) == 4


def test_messy_folders_skip_protected(tmp_path):
    for i, ext in enumerate(["a", "b", "c", "d", "e"] * 6):
        (tmp_path / f"f{i}.{ext}").write_text("x")
    assert folders.messy_folders([tmp_path], is_protected=lambda p: True) == []


# ---------------- bank of lines ----------------
def test_bank_parses_all_categories_and_fills_markers():
    bank = lines.parse_bank(lines.FACTORY_FILE.read_text(encoding="utf-8"))
    assert all(bank[c] for c in lines.CATEGORIES)
    text = lines.fill("A pasta {pasta} tem {n} arquivos de {tipos}.", {"pasta": "X", "n": 3, "tipos": ["pdf", "jpg"]})
    assert text == "A pasta X tem 3 arquivos de pdf, jpg."
    assert lines.fill("Ah, {nome}, voltou.", {}) == "Ah, voltou."


def test_bank_avoids_recent_lines():
    bank = {"retorno": ["Um.", "Dois."], **{c: [] for c in lines.CATEGORIES if c != "retorno"}}
    for _ in range(10):
        assert lines.pick("retorno", {}, ["Um."], bank=bank)["fala"] == "Dois."


def test_boredom_bank_lines_carry_a_case():
    bank = lines.load_bank()
    picked = lines.pick("tedio", {}, [], bank=bank)
    assert picked["caso"]["titulo"] and picked["fala"]
    # Every factory challenge has its own question, not the whole speech.
    for entry in lines.parse_bank(lines.FACTORY_FILE.read_text(encoding="utf-8"))["tedio"]:
        parts = lines.split_boredom(entry)
        assert parts["pergunta"] and parts["pergunta"] != parts["fala"]


def test_boredom_line_without_question_uses_the_speech():
    assert lines.split_boredom("Título :: Fala só.") == {"titulo": "Título", "fala": "Fala só.", "pergunta": ""}
    bank = {c: [] for c in lines.CATEGORIES}
    bank["tedio"] = ["Título :: Fala só."]
    assert lines.pick("tedio", {}, [], bank=bank)["caso"]["pergunta"] == "Fala só."


def test_user_bank_is_created_and_edits_apply(tmp_path):
    path = tmp_path / "falas.md"
    lines.ensure_bank(path)
    assert path.exists()
    path.write_text("## retorno\n- Só esta.\n", encoding="utf-8")
    bank = lines.load_bank(path)
    assert bank["retorno"] == ["Só esta."]
    assert bank["tarde"]  # emptied section falls back to the factory lines


# ---------------- generator ----------------
def run(coro):
    return asyncio.run(coro)


def asker_returning(text):
    async def ask(system, user, backend):
        ask.calls.append((system, user, backend))
        return text
    ask.calls = []
    return ask


def test_model_line_is_used_and_paths_never_reach_it():
    ask = asker_returning('{"fala": "Quarenta volumes no chão de Downloads. Lamentável."}')
    result = run(generator.generate(
        "bagunca", {"path": "C:/Users/ana/Downloads", "pasta": "Downloads", "n": 40},
        recent=[], persona="P", backend="claude-code", use_model=True, asker=ask))
    assert result == {"fala": "Quarenta volumes no chão de Downloads. Lamentável.", "fonte": "modelo"}
    system, user, backend = ask.calls[0]
    assert "C:/Users/ana" not in user and "Downloads" in user and backend == "claude-code"


def test_model_silence_is_respected_but_not_in_tests():
    ask = asker_returning('{"fala": ""}')
    assert run(generator.generate("tarde", {"hora": "01:00"}, recent=[], persona="P",
                                  backend="ollama", use_model=True, asker=ask)) is None
    forced = run(generator.generate("tarde", {"hora": "01:00"}, recent=[], persona="P",
                                    backend="ollama", use_model=True, asker=ask, allow_silence=False))
    assert forced["fonte"] == "banco"


@pytest.mark.parametrize("reply", [
    '{"fala": "Recebi um evento do sistema, que tédio."}',
    '{"fala": "' + "palavra " * 80 + '"}',
    "isto não é json {",
])
def test_bad_model_lines_fall_back_to_the_bank(reply):
    result = run(generator.generate("retorno", {"ausencia": 3600}, recent=[], persona="P",
                                    backend="ollama", use_model=True, asker=asker_returning(reply)))
    assert result["fonte"] == "banco" and result["fala"]


def test_repeated_model_line_falls_back():
    reply = '{"fala": "Ah, voltou depois de uma hora."}'
    result = run(generator.generate("retorno", {"ausencia": 3600}, recent=["Ah, voltou depois de uma hora."],
                                    persona="P", backend="ollama", use_model=True,
                                    asker=asker_returning(reply)))
    assert result["fonte"] == "banco"


def test_model_failure_falls_back():
    async def broken(system, user, backend):
        raise RuntimeError("sem login")
    result = run(generator.generate("organizado", {"n": 5}, recent=[], persona="P",
                                    backend="claude-code", use_model=True, asker=broken))
    assert result["fonte"] == "banco" and result["fala"] and "{" not in result["fala"]


def test_boredom_model_reply_carries_the_case():
    reply = ('{"fala": "Que tédio. Por que o céu fica laranja ao entardecer? Investigue comigo.",'
             ' "caso": {"titulo": "O céu laranja", "pergunta": "Por que o pôr do sol é laranja?"}}')
    result = run(generator.generate("tedio", {}, recent=[], persona="P", backend="ollama",
                                    use_model=True, asker=asker_returning(reply)))
    assert result["caso"] == {"titulo": "O céu laranja", "pergunta": "Por que o pôr do sol é laranja?"}


def test_model_off_uses_the_bank_without_calling_it():
    ask = asker_returning('{"fala": "x"}')
    result = run(generator.generate("retorno", {"ausencia": 7200}, recent=[], persona="P",
                                    backend="ollama", use_model=False, asker=ask))
    assert result["fonte"] == "banco" and not ask.calls
    assert "2 horas" in result["fala"]


def test_duration_text():
    assert generator.duration_text(95 * 60) == "1 hora e 35 minutos"
    assert generator.duration_text(60) == "1 minuto"
    assert generator.duration_text(3 * 86400) == "3 dias"


# ---------------- service ----------------
class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make_service(tmp_path, clock, *, presence=None, reply='{"fala": "Voltou, enfim."}', **prefs_changes):
    prefs = preferences.defaults()
    prefs.update(prefs_changes)
    return LifeService(
        path=tmp_path / "vida.json",
        prefs_loader=lambda: prefs,
        presence=presence or (lambda: {"system_idle": 5.0, "foreground": None}),
        scan=lambda: [],
        clock=clock,
        asker=asker_returning(reply),
    )


UI = {"app_idle_seconds": 0, "visible": True, "backend": "ollama"}


def test_service_prepares_then_delivers_on_a_later_tick(tmp_path):
    async def scenario():
        clock = Clock(NOON)
        service = make_service(tmp_path, clock)
        service.notify("organizado", {"n": 9})
        first = await service.tick(UI)
        assert first["status"]["reason"] == "preparando" and first["event"] is None
        await service.task
        second = await service.tick(UI)
        assert second["event"]["category"] == "organizado"
        assert second["event"]["text"] == "Voltou, enfim."
        clock.now += 30
        third = await service.tick(UI)
        assert third["event"] is None and third["status"]["reason"] == "intervalo"
        return service
    service = run(scenario())
    saved = LifePolicy(__import__("json").loads((tmp_path / "vida.json").read_text(encoding="utf-8")))
    assert saved.state["recent"] == ["Voltou, enfim."]


def test_service_holds_a_ready_line_while_the_user_types(tmp_path):
    async def scenario():
        clock = Clock(NOON)
        service = make_service(tmp_path, clock)
        service.notify("organizado", {"n": 9})
        await service.tick(UI)
        await service.task
        typing = await service.tick({**UI, "typing": True})
        assert typing["event"] is None and typing["status"]["reason"] == "digitando"
        clock.now += 200  # past the delivery window: dropped, never stale
        late = await service.tick(UI)
        assert late["event"] is None
    run(scenario())


def test_service_silence_drops_the_pending_line(tmp_path):
    async def scenario():
        clock = Clock(NOON)
        service = make_service(tmp_path, clock)
        service.notify("organizado", {"n": 9})
        await service.tick(UI)
        await service.task
        service.silence(120)
        result = await service.tick(UI)
        assert result["event"] is None and result["status"]["reason"] == "silencio"
        assert result["status"]["silenced_until"] == NOON + 7200
    run(scenario())


def test_service_dnd_from_preferences(tmp_path):
    async def scenario():
        service = make_service(tmp_path, Clock(NOON), life_dnd=True)
        service.notify("organizado", {"n": 9})
        result = await service.tick(UI)
        assert result["status"]["reason"] == "nao_perturbe" and service.task is None
    run(scenario())


def test_service_test_ignores_limits_and_returns_a_line(tmp_path):
    async def scenario():
        service = make_service(tmp_path, Clock(NOON), life_dnd=True,
                               reply='{"fala": "", "caso": null}')
        event = await service.test("tedio", UI)
        assert event["test"] and event["text"] and event["case"]["titulo"]
        assert service.policy.state["spoken"] == []
    run(scenario())


# ---------------- API ----------------
def test_life_api_tick_status_silence(client):
    tick = client.post("/api/life/tick", json={"app_idle_seconds": 1, "visible": True})
    assert tick.status_code == 200
    body = tick.json()
    assert "reason" in body["status"] and "event" in body
    silenced = client.post("/api/life/silence", json={"minutes": 30}).json()
    assert silenced["silenced_until"] > time.time()
    assert client.get("/api/life/status").json()["silenced_until"] == silenced["silenced_until"]
    resumed = client.post("/api/life/resume").json()
    assert resumed["silenced_until"] == 0
    assert resumed["lines_file"].endswith("falas.md")


def test_life_api_rejects_unknown_test_category(client):
    assert client.post("/api/life/test", json={"category": "nada"}).status_code == 400


def test_life_preferences_are_validated(client):
    assert client.post("/api/preferences", json={"life_max_per_hour": 99}).status_code == 400
    ok = client.post("/api/preferences", json={"life_max_per_hour": 3})
    assert ok.status_code == 200 and ok.json()["life_max_per_hour"] == 3
    client.post("/api/preferences", json={"life_max_per_hour": 2})


def test_organizer_moves_notify_victorique(tmp_path, monkeypatch):
    from app.tools import organizer
    seen = []
    from app.life import service as service_module
    monkeypatch.setattr(service_module.life_service, "notify", lambda c, f: seen.append((c, f)))
    organizer._tell_life("move", "Agrupar fotos", 5)
    organizer._tell_life("rename", "Renomear", 1)
    organizer._tell_life("move", "Pouca coisa", 2)
    assert seen == [("organizado", {"n": 5, "descricao": "Agrupar fotos"})]
