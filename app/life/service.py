"""
Victorique's "vida própria": the piece the API talks to.

The UI calls ``tick`` every few seconds with its own state (typing, replying,
visible...). The service reads the Windows presence signals, asks the policy
whether she may speak and about what, writes the line in the background and
hands it to the UI on a later tick, after checking the gates again.
"""
import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.config import DATA_DIR
from app.life import folders, generator, lines, observer
from app.life.policy import REASONS, LifeConfig, LifePolicy, Signals

logger = logging.getLogger(__name__)

DELIVERY_TTL = 120.0
SAVE_EVERY = 300.0


def state_path() -> Path:
    return DATA_DIR / "vida_propria.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".vida-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _default_scan() -> list:
    from app.security.path_guard import path_guard
    return folders.messy_folders(path_guard.authorized_dirs, path_guard.is_protected)


class LifeService:
    def __init__(
        self,
        *,
        path: Optional[Path] = None,
        prefs_loader: Optional[Callable[[], Dict[str, Any]]] = None,
        presence: Callable[[], Dict[str, Any]] = observer.snapshot,
        scan: Callable[[], list] = _default_scan,
        clock: Callable[[], float] = time.time,
        asker=generator.ask_model,
    ):
        self.path = path or state_path()
        self.policy = LifePolicy(_read_json(self.path))
        self._prefs_loader = prefs_loader
        self.presence = presence
        self.scan = scan
        self.clock = clock
        self.asker = asker
        self.task: Optional[asyncio.Task] = None
        self.outbox: Optional[Dict[str, Any]] = None
        self.last_reason = "pronta"
        self._saved_at = 0.0
        self._boredom_range = None

    # ---------- helpers ----------
    def prefs(self) -> Dict[str, Any]:
        if self._prefs_loader:
            return self._prefs_loader()
        from app.core import preferences
        return preferences.load()

    def save(self) -> None:
        try:
            _write_json(self.path, self.policy.snapshot())
            self._saved_at = self.clock()
        except OSError as exc:
            logger.warning("Vida própria: não consegui salvar o estado (%s).", exc)

    def _config(self, prefs: Dict[str, Any]) -> LifeConfig:
        cfg = LifeConfig.from_prefs(prefs)
        rng = (cfg.boredom_min, cfg.boredom_max)
        if self._boredom_range is not None and rng != self._boredom_range:
            self.policy._resample_boredom(cfg)  # the range changed in Settings
        self._boredom_range = rng
        return cfg

    def _signals(self, ui: Dict[str, Any]) -> Signals:
        seen = self.presence() or {}
        return Signals(
            now=self.clock(),
            app_idle=max(0.0, float(ui.get("app_idle_seconds") or 0.0)),
            system_idle=seen.get("system_idle"),
            foreground=seen.get("foreground"),
            typing=bool(ui.get("typing")),
            generating=bool(ui.get("generating")),
            visible=ui.get("visible", True) is not False,
            settings_open=bool(ui.get("settings_open")),
        )

    def _context(self, prefs: Dict[str, Any], ui: Dict[str, Any], category: str):
        from app.core.personality import personality_manager
        backend = str(ui.get("backend") or "").strip().lower()
        profile_id = ui.get("personality_id")
        profile = personality_manager.get_personality(profile_id) if profile_id else None
        mode = "claude-code" if backend == "claude-code" else "local"
        persona = personality_manager.build_system_prompt(profile, mode=mode)
        extra: Dict[str, Any] = {"nome": prefs.get("user_name", "")}
        if category == "tedio":
            extra.update(self._boredom_facts(prefs))
        return persona, backend, extra

    @staticmethod
    def _boredom_facts(prefs: Dict[str, Any]) -> Dict[str, Any]:
        from app.memory.project_store import project_store
        try:
            cases = [p["name"] for p in project_store.list_projects() if not p.get("archived")][:8]
        except Exception:
            cases = []
        about = str(prefs.get("user_about") or "").strip()[:500]
        return {"casos_abertos": cases, "sobre_o_usuario": about}

    # ---------- public API ----------
    def notify(self, category: str, facts: Dict[str, Any]) -> None:
        """Called by other parts of the app (e.g. the organizer)."""
        self.policy.notify(category, facts, self.clock())

    def silence(self, minutes: int) -> float:
        until = self.policy.silence(minutes, self.clock())
        self.outbox = None
        self.save()
        return until

    def resume(self) -> None:
        self.policy.resume()
        self.save()

    def status(self, reason: Optional[str] = None, prefs: Optional[Dict[str, Any]] = None,
               signals: Optional[Signals] = None) -> Dict[str, Any]:
        prefs = prefs or self.prefs()
        reason = reason or self.last_reason
        cfg = LifeConfig.from_prefs(prefs)
        state = self.policy.state
        boredom = None
        if signals is not None:
            boredom = self.policy.boredom_due_in(signals, cfg)
        return {
            "reason": reason,
            "label": REASONS.get(reason, reason),
            "silenced_until": state["silenced_until"] if state["silenced_until"] > self.clock() else 0,
            "dnd": cfg.dnd,
            "spoken_last_hour": len([t for t in state["spoken"] if t > self.clock() - 3600]),
            "max_per_hour": cfg.max_per_hour,
            "boredom_in": boredom,
            "lines_file": str(lines.ensure_bank()),
        }

    async def tick(self, ui: Dict[str, Any]) -> Dict[str, Any]:
        prefs = self.prefs()
        cfg = self._config(prefs)
        s = self._signals(ui)
        self.policy.observe(s, cfg)
        event = None

        if self.outbox is not None:
            if self.outbox["expires"] <= s.now:
                self.outbox = None
            elif self.policy.gate(s, cfg, rates=False) == "pronta":
                event, self.outbox = self.outbox, None
                self.policy.delivered(event["candidate"], event["fala"], s, cfg)
                self.save()

        if self.task is not None and not self.task.done():
            reason = "preparando"
        else:
            reason = self.policy.gate(s, cfg)
            if reason == "pronta" and self.outbox is None and event is None:
                candidate = self.policy.candidate(s, cfg, self.scan)
                if candidate:
                    self.policy.attempted(s.now)
                    self.task = asyncio.create_task(self._prepare(candidate, prefs, ui, s, cfg))
                    reason = "preparando"
                else:
                    reason = "sem_assunto"
        self.last_reason = reason

        if s.now - self._saved_at >= SAVE_EVERY:
            self.save()
        return {"status": self.status(reason, prefs, s), "event": self._public(event)}

    async def _prepare(self, candidate, prefs, ui, s: Signals, cfg: LifeConfig) -> None:
        try:
            result = await self._write(candidate, prefs, ui, allow_silence=True)
        except Exception:
            logger.exception("Vida própria: falha ao preparar a fala")
            result = None
        if not result:
            self.policy.consumed_candidate(candidate, s, cfg)
            self.save()
            return
        self.outbox = {**result, "candidate": candidate, "expires": self.clock() + DELIVERY_TTL}

    async def _write(self, candidate, prefs, ui, *, allow_silence: bool):
        category = candidate["category"]
        persona, backend, extra = self._context(prefs, ui, category)
        return await generator.generate(
            category,
            candidate.get("facts") or {},
            recent=list(self.policy.state["recent"]),
            persona=persona,
            backend=backend,
            use_model=bool(prefs.get("life_generate", True)),
            extra=extra,
            allow_silence=allow_silence,
            asker=self.asker,
        )

    async def test(self, category: str, ui: Dict[str, Any]) -> Dict[str, Any]:
        """«Testar agora» in Settings: ignores gates and limits, never counts
        toward them, and always says something (falls back to the bank)."""
        if category not in generator.MOMENTS:
            raise ValueError("Tipo de fala desconhecido.")
        samples = {
            "tarde": {"hora": time.strftime("%H:%M", time.localtime(self.clock()))},
            "bagunca": {"pasta": "Downloads", "n": 48, "tipos": ["pdf", "jpg", "zip", "docx"]},
            "organizado": {"n": 12, "descricao": "arquivos agrupados por tipo"},
            "retorno": {"ausencia": 95 * 60},
            "tedio": {},
        }
        candidate = {"category": category, "facts": samples[category]}
        prefs = self.prefs()
        cfg = LifeConfig.from_prefs(prefs)
        result = await self._write(candidate, prefs, ui, allow_silence=False)
        if not result:
            raise ValueError("Não há falas desse tipo no banco.")
        s = self._signals(ui)
        self.policy.delivered(candidate, result["fala"], s, cfg, forced=True)
        self.save()
        return self._public({**result, "candidate": candidate, "test": True})

    @staticmethod
    def _public(event: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not event:
            return None
        out = {
            "category": event["candidate"]["category"],
            "text": event["fala"],
            "source": event.get("fonte", "banco"),
            "test": bool(event.get("test")),
        }
        if event.get("caso"):
            out["case"] = event["caso"]
        return out


life_service = LifeService()
