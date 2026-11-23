"""
When Victorique may speak on her own. Deterministic: every decision here is
made before any model is called, from the clock, the app's state and the
Windows presence signals. Observed data never bypasses a gate.

Gates (any one blocks): features off, "não perturbar", «Silêncio», user away
from the PC, window hidden, settings open, a reply in progress, typing,
fullscreen app, quiet-listed app in front, minimum gap, hourly cap, recent
failed attempt. Silence chosen by the model is a valid outcome.
(Rules studied in CapriCore's initiative policy; this code is our own.)
"""
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

AWAY_AFTER = 5 * 60            # PC idle this long: the user is away
PRESENT_WITHIN = 2 * 60        # PC input this recent: the user is right there
RETURN_AFTER = 45 * 60         # an absence this long earns a "welcome back"
LAUNCH_RETURN_AFTER = 6 * 3600  # app reopened after this long
ATTEMPT_COOLDOWN = 60
SCAN_EVERY = 30 * 60
FOLDER_REPEAT = 7 * 24 * 3600
QUEUE_TTL = {"organizado": 10 * 60, "retorno": 5 * 60}
RECENT_KEEP = 12
HOUR = 3600

REASONS = {
    "pronta": "Pode falar quando houver assunto.",
    "sem_assunto": "Sem assunto no momento.",
    "preparando": "Preparando uma fala…",
    "desligada": "Vida própria desligada.",
    "nao_perturbe": "Modo não perturbar ligado.",
    "silencio": "Em silêncio, a seu pedido.",
    "ausente": "Você está longe do computador.",
    "oculta": "A janela está minimizada.",
    "configuracoes": "As configurações estão abertas.",
    "ocupada": "Ela está respondendo.",
    "digitando": "Você está digitando.",
    "tela_cheia": "Há um app em tela cheia.",
    "app_calado": "Um app da lista de silêncio está em primeiro plano.",
    "intervalo": "Respeitando o intervalo mínimo entre falas.",
    "limite_hora": "Limite de falas por hora atingido.",
    "tentativa": "Aguardando um minuto após a última tentativa.",
}


@dataclass
class LifeConfig:
    boredom: bool = True
    comments: bool = True
    boredom_min: int = 20          # minutes
    boredom_max: int = 45
    max_per_hour: int = 2
    min_gap: int = 15              # minutes
    dnd: bool = False
    quiet_apps: Set[str] = field(default_factory=set)

    @classmethod
    def from_prefs(cls, prefs: Dict[str, Any]) -> "LifeConfig":
        low, high = sorted((int(prefs["life_boredom_min"]), int(prefs["life_boredom_max"])))
        apps = {a.strip().lower() for a in str(prefs["life_quiet_apps"]).replace(";", ",").split(",")}
        return cls(
            boredom=bool(prefs["life_boredom"]),
            comments=bool(prefs["life_comments"]),
            boredom_min=low,
            boredom_max=high,
            max_per_hour=int(prefs["life_max_per_hour"]),
            min_gap=int(prefs["life_min_gap"]),
            dnd=bool(prefs["life_dnd"]),
            quiet_apps={a if a.endswith(".exe") else f"{a}.exe" for a in apps if a},
        )


@dataclass
class Signals:
    now: float
    app_idle: float                       # seconds since the last interaction with the app
    system_idle: Optional[float] = None   # seconds since the last input on the PC
    foreground: Optional[Dict[str, Any]] = None
    typing: bool = False
    generating: bool = False
    visible: bool = True
    settings_open: bool = False


def _empty_state() -> Dict[str, Any]:
    return {
        "spoken": [], "last_spoken": 0.0, "last_attempt": 0.0, "recent": [],
        "silenced_until": 0.0, "last_presence": 0.0, "boredom_threshold": 0.0,
        "boredom_anchor": 0.0, "late_night": "", "folders": {}, "last_scan": 0.0,
    }


def night_key(now: float) -> str:
    """The evening a late hour belongs to: 01:00 on the 5th counts as the 4th's night."""
    t = time.localtime(now - (12 * HOUR if time.localtime(now).tm_hour < 12 else 0))
    return time.strftime("%Y-%m-%d", t)


def is_late(now: float) -> bool:
    t = time.localtime(now)
    return t.tm_hour < 5 or (t.tm_hour == 23 and t.tm_min >= 30)


class LifePolicy:
    def __init__(self, state: Optional[Dict[str, Any]] = None, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.state = _empty_state()
        self.restore(state or {})
        self.queue: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._prev_system_idle: Optional[float] = None
        self._first_tick = True

    # ---------- persistence ----------
    def restore(self, saved: Dict[str, Any]) -> None:
        base = _empty_state()
        for key, default in base.items():
            value = saved.get(key, default)
            if isinstance(default, float) and isinstance(value, (int, float)):
                base[key] = float(value)
            elif isinstance(default, list) and isinstance(value, list):
                base[key] = [v for v in value if isinstance(v, (int, float, str))]
            elif isinstance(default, dict) and isinstance(value, dict):
                base[key] = {str(k): float(v) for k, v in value.items() if isinstance(v, (int, float))}
            elif isinstance(default, str) and isinstance(value, str):
                base[key] = value[:20]
        base["recent"] = [str(t)[:400] for t in base["recent"]][-RECENT_KEEP:]
        base["spoken"] = [float(t) for t in base["spoken"] if isinstance(t, (int, float))][-30:]
        self.state = base

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.state)

    # ---------- external events ----------
    def notify(self, category: str, facts: Dict[str, Any], now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self.queue = [c for c in self.queue if c["category"] != category]
            self.queue.append({"category": category, "facts": facts,
                               "expires": now + QUEUE_TTL.get(category, 300)})

    def silence(self, minutes: int, now: float) -> float:
        self.state["silenced_until"] = now + max(1, minutes) * 60
        return self.state["silenced_until"]

    def resume(self) -> None:
        self.state["silenced_until"] = 0.0

    # ---------- per-tick observation ----------
    def observe(self, s: Signals, cfg: LifeConfig) -> None:
        idle = s.system_idle
        if idle is not None and idle < AWAY_AFTER:
            prev = self._prev_system_idle
            if prev is not None and prev >= RETURN_AFTER and idle < PRESENT_WITHIN:
                self.notify("retorno", {"ausencia": prev}, s.now)
            elif self._first_tick and self.state["last_presence"] and \
                    s.now - self.state["last_presence"] >= LAUNCH_RETURN_AFTER:
                self.notify("retorno", {"ausencia": s.now - self.state["last_presence"]}, s.now)
            self.state["last_presence"] = s.now
        self._prev_system_idle = idle
        self._first_tick = False
        if not self.state["boredom_threshold"]:
            self._resample_boredom(cfg)

    def _resample_boredom(self, cfg: LifeConfig) -> None:
        minutes = self.rng.uniform(cfg.boredom_min, cfg.boredom_max)
        self.state["boredom_threshold"] = minutes * 60

    # ---------- gates ----------
    def gate(self, s: Signals, cfg: LifeConfig, *, rates: bool = True) -> str:
        fg = s.foreground or {}
        checks = [
            (not (cfg.boredom or cfg.comments), "desligada"),
            (cfg.dnd, "nao_perturbe"),
            (self.state["silenced_until"] > s.now, "silencio"),
            (s.system_idle is not None and s.system_idle >= AWAY_AFTER, "ausente"),
            (not s.visible, "oculta"),
            (s.settings_open, "configuracoes"),
            (s.generating, "ocupada"),
            (s.typing, "digitando"),
            (bool(fg.get("fullscreen")) and not fg.get("own"), "tela_cheia"),
            (not fg.get("own") and str(fg.get("process", "")).lower() in cfg.quiet_apps,
             "app_calado"),
        ]
        if rates:
            spoken = [t for t in self.state["spoken"] if t > s.now - HOUR]
            self.state["spoken"] = spoken
            checks += [
                (s.now - self.state["last_spoken"] < cfg.min_gap * 60, "intervalo"),
                (len(spoken) >= cfg.max_per_hour, "limite_hora"),
                (s.now - self.state["last_attempt"] < ATTEMPT_COOLDOWN, "tentativa"),
            ]
        for blocked, reason in checks:
            if blocked:
                return reason
        return "pronta"

    # ---------- what to talk about ----------
    def boredom_due_in(self, s: Signals, cfg: LifeConfig) -> Optional[float]:
        """Seconds until boredom may strike (0 = due), or None if it already spoke
        during this stretch of inactivity."""
        if not cfg.boredom:
            return None
        if not self.state["boredom_threshold"]:
            self._resample_boredom(cfg)
        activity = s.now - s.app_idle
        if activity <= self.state["boredom_anchor"] + 5:
            return None
        return max(0.0, self.state["boredom_threshold"] - s.app_idle)

    def candidate(
        self,
        s: Signals,
        cfg: LifeConfig,
        scan_folders: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if cfg.comments:
            with self._lock:
                self.queue = [c for c in self.queue if c["expires"] > s.now]
                if self.queue:
                    return self.queue.pop(0)
            present = s.system_idle is None or s.system_idle < PRESENT_WITHIN
            if present and is_late(s.now) and self.state["late_night"] != night_key(s.now):
                return {"category": "tarde", "facts": {"hora": time.strftime("%H:%M", time.localtime(s.now))}}
            if scan_folders and s.now - self.state["last_scan"] >= SCAN_EVERY:
                self.state["last_scan"] = s.now
                for folder in scan_folders():
                    last = self.state["folders"].get(folder["path"], 0.0)
                    if s.now - last >= FOLDER_REPEAT:
                        return {"category": "bagunca", "facts": folder}
        if self.boredom_due_in(s, cfg) == 0.0:
            return {"category": "tedio", "facts": {}}
        return None

    # ---------- outcomes ----------
    def attempted(self, now: float) -> None:
        self.state["last_attempt"] = now

    def delivered(self, candidate: Dict[str, Any], text: str, s: Signals,
                  cfg: LifeConfig, *, forced: bool = False) -> None:
        category = candidate["category"]
        if text:
            self.state["recent"] = (self.state["recent"] + [text[:400]])[-RECENT_KEEP:]
        if forced:
            return
        self.state["last_spoken"] = s.now
        self.state["spoken"] = [t for t in self.state["spoken"] if t > s.now - HOUR] + [s.now]
        if category == "tarde":
            self.state["late_night"] = night_key(s.now)
        elif category == "bagunca":
            self.state["folders"][candidate["facts"].get("path", "")] = s.now
            # Keep the folder memory small.
            folders = sorted(self.state["folders"].items(), key=lambda kv: kv[1])[-50:]
            self.state["folders"] = dict(folders)
        elif category == "tedio":
            self.state["boredom_anchor"] = s.now - s.app_idle
            self._resample_boredom(cfg)

    def consumed_candidate(self, candidate: Dict[str, Any], s: Signals, cfg: LifeConfig) -> None:
        """The model chose silence: do not ask again about the same moment."""
        category = candidate["category"]
        if category == "tarde":
            self.state["late_night"] = night_key(s.now)
        elif category == "bagunca":
            self.state["folders"][candidate["facts"].get("path", "")] = s.now
        elif category == "tedio":
            self.state["boredom_anchor"] = s.now - s.app_idle
            self._resample_boredom(cfg)
