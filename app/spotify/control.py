"""
What the chats can ask of Spotify (the spotify_* tools, in every mode that has
tools): play something, queue a track, search, pause, resume, skip, volume,
shuffle, repeat, like, and what is playing.

The Spicetify extension does it inside Spotify (victorique.js, through the
bridge's WebSocket), with Spotify's own search and player. Without the bridge:
- Spotify closed, or the Microsoft Store build opened from the Start menu (it
  comes up without Spicetify): Spicetify reopens it and the request waits for
  the bridge (up to LAUNCH_WAIT seconds), when the bridge installed is this
  app's (same port and token);
- pause, resume and the skips still work through Windows' media controls (SMTC);
- a play request opens Spotify's search for the user to pick the track.

Every answer is a small dict with a "mensagem" in Portuguese for the model;
what cannot be done raises SpotifyError with the reason, in Portuguese too.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

from app.spotify.bridge import Bridge, BridgeCommandError, BridgeOffline, bridge as default_bridge
from app.spotify.track import Track, clean, make

logger = logging.getLogger(__name__)

LAUNCH_WAIT = 25.0       # Spotify opening until the extension connects
RELAUNCH_GAP = 90.0      # do not reopen Spotify again while it is still coming up
# The extension may first wait (up to 10 s) for Spotify's player and queries,
# right after Spotify opens; then search + play + the song changing.
PLAY_TIMEOUT = 30.0
COMMAND_TIMEOUT = 15.0

TYPES = {
    "": "track", "musica": "track", "música": "track", "faixa": "track", "cancao": "track",
    "canção": "track", "track": "track", "song": "track",
    "artista": "artist", "banda": "artist", "artist": "artist",
    "album": "album", "álbum": "album", "disco": "album",
    "playlist": "playlist", "lista": "playlist",
    "podcast": "show", "show": "show",
    "episodio": "episode", "episódio": "episode", "episode": "episode",
    "curtidas": "liked", "musicas curtidas": "liked", "músicas curtidas": "liked", "liked": "liked",
}
LABELS = {"track": "música", "artist": "artista", "album": "álbum", "playlist": "playlist",
          "show": "podcast", "episode": "episódio", "liked": "Músicas Curtidas"}
ACTIONS = {
    "pausar": "pause", "pause": "pause", "parar": "pause",
    "continuar": "resume", "retomar": "resume", "despausar": "resume", "resume": "resume", "play": "resume",
    "alternar": "toggle", "toggle": "toggle",
    "proxima": "next", "próxima": "next", "pular": "next", "avancar": "next", "avançar": "next",
    "next": "next", "skip": "next",
    "anterior": "previous", "voltar": "previous", "previous": "previous", "back": "previous",
    "volume": "volume",
    "aleatorio": "shuffle", "aleatório": "shuffle", "embaralhar": "shuffle", "shuffle": "shuffle",
    "repetir": "repeat", "repeat": "repeat",
    "curtir": "like", "like": "like", "descurtir": "unlike", "unlike": "unlike",
}
SMTC_ACTIONS = {"pause", "resume", "toggle", "next", "previous"}
ON = {"on", "ligar", "ligado", "liga", "sim", "true", "1", "ativar", "ativado"}
OFF = {"off", "desligar", "desligado", "desliga", "nao", "não", "false", "0", "desativar", "desativado"}
REPEAT_MODES = {
    "off": 0, "desligar": 0, "desligado": 0, "nao": 0, "não": 0, "false": 0, "0": 0, "nenhum": 0,
    "on": 1, "ligar": 1, "sim": 1, "true": 1, "1": 1, "contexto": 1, "context": 1, "tudo": 1,
    "playlist": 1, "album": 1, "álbum": 1, "lista": 1,
    "faixa": 2, "musica": 2, "música": 2, "uma": 2, "track": 2, "2": 2,
}
REPEAT_NAMES = {0: "desligada", 1: "a lista toda", 2: "só esta faixa"}
VOLUME_STEP = 10
_URI = re.compile(r"spotify:(track|album|artist|playlist|episode|show):([A-Za-z0-9]{22})")
_LINK = re.compile(r"open\.spotify\.com/(?:intl-[a-z-]+/)?(track|album|artist|playlist|episode|show)/"
                   r"([A-Za-z0-9]{22})")
OFFLINE_HINT = ("Para eu controlar o Spotify por dentro, ele precisa estar aberto com a ponte do "
                "Spicetify (Configurações → Na área de trabalho → «Reaplicar a ponte do Spicetify»).")


class SpotifyError(RuntimeError):
    """What could not be done, said for the user (Portuguese)."""


def _key(text: Any) -> str:
    return " ".join(clean(text, 60).lower().split())


def kind_of(tipo: Any) -> str:
    key = _key(tipo)
    if key in TYPES:
        return TYPES[key]
    raise SpotifyError(f"Tipo desconhecido: «{clean(tipo, 40)}». Use musica, artista, album, playlist, "
                       "podcast, episodio ou curtidas.")


def spotify_uri(text: Any) -> Optional[str]:
    """A Spotify link or URI in the request, as a URI."""
    value = str(text or "")
    found = _URI.search(value) or _LINK.search(value)
    return f"spotify:{found.group(1)}:{found.group(2)}" if found else None


def _seconds(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return ""
    value = int(value)
    return f"{value // 60}:{value % 60:02d}"


def _song(item: Any) -> str:
    """«Title — Artist» from what the extension reports (now playing or a result)."""
    if not isinstance(item, dict):
        return ""
    title = clean(item.get("title") or item.get("name"), 200)
    artist = clean(item.get("artist") or item.get("by"), 200)
    return f"{title} — {artist}" if title and artist else title


def _track_of(now: Any) -> Optional[Track]:
    if not isinstance(now, dict):
        return None
    return make(now.get("title"), now.get("artist"), now.get("album"), bool(now.get("playing", True)),
                "spicetify")


def _results(items: Any) -> List[Dict[str, str]]:
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not spotify_uri(item.get("uri")):
            continue
        out.append({"nome": clean(item.get("name"), 200), "de": clean(item.get("by"), 200),
                    "tipo": LABELS.get(str(item.get("type")), str(item.get("type"))),
                    "uri": spotify_uri(item.get("uri")) or ""})
    return out


def parse_volume(valor: Any) -> Dict[str, int]:
    """{"level": 0-100} or {"delta": ±n} from 50, "50%", "+10", "mais", "menos", "mudo"."""
    if isinstance(valor, bool):
        raise SpotifyError("Diga o volume de 0 a 100, ou «mais» / «menos».")
    if isinstance(valor, (int, float)):
        return {"level": max(0, min(100, int(round(valor))))}
    text = _key(valor).replace("%", "").replace(" ", "")
    if text in {"mais", "aumentar", "aumenta", "subir", "sobe", "alto", "up"}:
        return {"delta": VOLUME_STEP}
    if text in {"menos", "diminuir", "diminui", "abaixar", "abaixa", "baixar", "baixo", "down"}:
        return {"delta": -VOLUME_STEP}
    if text in {"mudo", "silenciar", "silencio", "silêncio", "mute"}:
        return {"level": 0}
    if text in {"maximo", "máximo", "max"}:
        return {"level": 100}
    if re.fullmatch(r"[+-]\d{1,3}", text):
        return {"delta": max(-100, min(100, int(text)))}
    if re.fullmatch(r"\d{1,3}", text):
        return {"level": max(0, min(100, int(text)))}
    raise SpotifyError("Diga o volume de 0 a 100, ou «mais» / «menos».")


def _switch(valor: Any) -> Optional[bool]:
    """True/False from on/off words; None (toggle) when not given."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    text = _key(valor)
    if text in ON:
        return True
    if text in OFF:
        return False
    raise SpotifyError("Diga «ligar» ou «desligar».")


def _repeat(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return 1 if valor else 0
    text = _key(valor)
    if text in REPEAT_MODES:
        return REPEAT_MODES[text]
    raise SpotifyError("Diga «desligar», «lista» (repete a lista toda) ou «faixa» (repete só esta).")


def describe_state(state: Dict[str, Any]) -> str:
    """The player, in one paragraph."""
    now = state.get("now") if isinstance(state.get("now"), dict) else None
    if not now:
        return "Nada tocando no Spotify agora."
    parts = [("Tocando agora: " if now.get("playing") else "Pausado em: ") + _song(now)]
    if now.get("album"):
        parts[0] += f" (álbum {clean(now.get('album'), 200)})"
    position, total = _seconds(state.get("progress")), _seconds(state.get("duration"))
    if position and total:
        parts[0] += f", em {position} de {total}"
    parts[0] += "."
    details = []
    if isinstance(state.get("volume"), (int, float)):
        details.append(f"volume {int(state['volume'])}%")
    if isinstance(state.get("shuffle"), bool):
        details.append("aleatório " + ("ligado" if state["shuffle"] else "desligado"))
    if state.get("repeat") in REPEAT_NAMES:
        details.append("repetição " + REPEAT_NAMES[state["repeat"]])
    if isinstance(state.get("liked"), bool):
        details.append("curtida" if state["liked"] else "não curtida")
    if details:
        parts.append(details[0][0].upper() + ", ".join(details)[1:] + ".")
    upcoming = [_song(t) for t in state.get("next") or [] if isinstance(t, dict)]
    upcoming = [s for s in upcoming if s][:3]
    if upcoming:
        parts.append("Próximas: " + "; ".join(upcoming) + ".")
    return " ".join(parts)


# ----------------- defaults (real Spotify, real Spicetify) -----------------
def _default_should_launch() -> bool:
    """Opening Spotify through Spicetify would bring this app's bridge up."""
    from app.config import settings
    from app.spotify import nowplaying, spicetify
    state = spicetify.state(settings.port, default_bridge.token())
    if not state.get("current"):
        return False               # no bridge, or one made for another port/token
    if not nowplaying.spotify_windows():
        return True                # closed (or only in the tray)
    return bool(state.get("store")) and spicetify.store_without_bridge()


def _default_launch() -> bool:
    from app.spotify import spicetify
    return spicetify.launch()


def _default_smtc(action: str) -> Optional[bool]:
    from app.spotify.nowplaying import smtc_control
    return smtc_control(action)


def _default_reader() -> Optional[Track]:
    from app.spotify.nowplaying import current
    return current()


def _default_open(target: str) -> bool:
    if os.name != "nt":
        return False
    try:
        os.startfile(target)  # spotify: links open the Spotify app
        return True
    except OSError as exc:
        logger.info("não consegui abrir %s: %s", target, exc)
        return False


def _default_skip(track: Optional[Track]) -> None:
    from app.spotify.watcher import spotify_watcher
    spotify_watcher.skip_comment(track)


class SpotifyControl:
    def __init__(self, bridge: Optional[Bridge] = None, *,
                 should_launch: Callable[[], bool] = _default_should_launch,
                 launch: Callable[[], bool] = _default_launch,
                 smtc: Callable[[str], Optional[bool]] = _default_smtc,
                 reader: Callable[[], Optional[Track]] = _default_reader,
                 opener: Callable[[str], bool] = _default_open,
                 skip_comment: Callable[[Optional[Track]], None] = _default_skip,
                 clock: Callable[[], float] = time.monotonic,
                 launch_wait: float = LAUNCH_WAIT):
        self._bridge = bridge
        self.should_launch = should_launch
        self.launch = launch
        self.smtc = smtc
        self.reader = reader
        self.opener = opener
        self.skip_comment = skip_comment
        self.clock = clock
        self.launch_wait = launch_wait
        self._launched_at: Optional[float] = None

    @property
    def bridge(self) -> Bridge:
        return self._bridge or default_bridge

    async def _ready(self, launch: bool) -> bool:
        """The extension can take requests; with `launch`, Spotify is opened
        through Spicetify first when that would bring the bridge up."""
        if self.bridge.linked:
            return True
        if not launch:
            return False
        now = self.clock()
        recent = self._launched_at is not None and now - self._launched_at < RELAUNCH_GAP
        if not recent:
            try:
                if not await asyncio.to_thread(self.should_launch):
                    return False
                self._launched_at = now
                if not await asyncio.to_thread(self.launch):
                    return False
            except Exception:
                logger.exception("Spotify: não consegui abrir pelo Spicetify")
                return False
        return await self.bridge.wait_linked(self.launch_wait)

    async def _send(self, name: str, args: Dict[str, Any], timeout: float = COMMAND_TIMEOUT) -> Dict[str, Any]:
        try:
            return await self.bridge.command(name, args, timeout)
        except BridgeOffline as exc:
            raise SpotifyError(f"{exc} {OFFLINE_HINT}") from exc
        except BridgeCommandError as exc:
            raise SpotifyError(f"O Spotify não conseguiu: {exc}") from exc

    # --- play / queue / search ---
    async def play(self, pedido: Any = "", tipo: Any = "musica") -> Dict[str, Any]:
        kind = kind_of(tipo)
        query = clean(pedido, 200)
        uri = spotify_uri(query)
        if not uri and kind != "liked" and not query:
            raise SpotifyError("Diga o que tocar (nome da música, artista, álbum ou playlist).")
        args: Dict[str, Any] = {"uri": uri} if uri else {"query": query, "type": kind}
        if not await self._ready(launch=True):
            return self._open_instead(query, uri, kind)
        result = await self._send("play", args, PLAY_TIMEOUT)
        chosen = result.get("chosen") if isinstance(result.get("chosen"), dict) else {}
        now = result.get("now") if isinstance(result.get("now"), dict) else None
        if now:
            message = f"Tocando agora: {_song(now)}."
        elif kind == "liked":
            message = "Mandei tocar as Músicas Curtidas."
        else:
            message = f"Mandei tocar {_song(chosen) or 'o que você pediu'}."
        if chosen.get("type") in ("album", "artist", "playlist", "show", "liked") and chosen.get("name"):
            message += f" ({LABELS.get(chosen['type'], '')}: {clean(chosen['name'], 200)}"
            message += ", da sua biblioteca)" if chosen.get("mine") else ")"
        self.skip_comment(_track_of(now))
        out: Dict[str, Any] = {"ok": True, "mensagem": message, "tocando": now,
                               "escolhido": (_results([chosen]) or [None])[0]}
        others = _results(result.get("others"))
        if others:
            out["outras_opcoes"] = others
        return out

    def _open_instead(self, query: str, uri: Optional[str], kind: str) -> Dict[str, Any]:
        """No bridge: open the item, or the search, in Spotify for the user."""
        if kind == "liked" and not uri:
            target, what = "spotify:collection:tracks", "as Músicas Curtidas"
        elif uri:
            target, what = uri, "o link"
        else:
            target, what = f"spotify:search:{urllib.parse.quote(query)}", f"a busca por «{query}»"
        if self.opener(target):
            message = (f"Não consegui dar o play sozinha porque a ponte do Spicetify não está "
                       f"conectada, então abri {what} no Spotify para você escolher. {OFFLINE_HINT}")
        else:
            message = f"Não consegui falar com o Spotify. {OFFLINE_HINT}"
        return {"ok": False, "mensagem": message, "ponte": False}

    async def queue(self, pedido: Any, tipo: Any = "musica") -> Dict[str, Any]:
        kind = kind_of(tipo)
        if kind not in ("track", "episode"):
            raise SpotifyError("Só músicas e episódios entram na fila.")
        query = clean(pedido, 200)
        uri = spotify_uri(query)
        if not uri and not query:
            raise SpotifyError("Diga qual música pôr na fila.")
        if not await self._ready(launch=True):
            raise SpotifyError(f"A ponte do Spicetify não está conectada. {OFFLINE_HINT}")
        result = await self._send("queue", {"uri": uri} if uri else {"query": query, "type": kind}, PLAY_TIMEOUT)
        chosen = result.get("chosen") if isinstance(result.get("chosen"), dict) else {}
        out: Dict[str, Any] = {"ok": True, "mensagem": f"Na fila: {_song(chosen) or 'o que você pediu'}.",
                               "escolhido": (_results([chosen]) or [None])[0]}
        others = _results(result.get("others"))
        if others:
            out["outras_opcoes"] = others
        return out

    async def search(self, pedido: Any, tipo: Any = "musica", limite: Any = 5) -> Dict[str, Any]:
        kind = kind_of(tipo)
        if kind == "liked":
            raise SpotifyError("Para as Músicas Curtidas, use spotify_tocar com tipo «curtidas».")
        query = clean(pedido, 200)
        if not query:
            raise SpotifyError("Diga o que procurar no Spotify.")
        try:
            limit = max(1, min(10, int(limite)))
        except (TypeError, ValueError):
            limit = 5
        if not await self._ready(launch=False):
            raise SpotifyError(f"A ponte do Spicetify não está conectada, então não consigo buscar. {OFFLINE_HINT}")
        items = _results((await self._send("search", {"query": query, "type": kind, "limit": limit},
                                           PLAY_TIMEOUT)).get("items"))
        if not items:
            return {"ok": True, "mensagem": f"Nada encontrado no Spotify para «{query}».", "resultados": []}
        lines = [f"{i}. {r['nome']}" + (f" — {r['de']}" if r["de"] else "") for i, r in enumerate(items, 1)]
        return {"ok": True, "mensagem": f"Resultados ({LABELS[kind]}):\n" + "\n".join(lines),
                "resultados": items}

    # --- player controls ---
    async def control(self, acao: Any, valor: Any = None) -> Dict[str, Any]:
        action = ACTIONS.get(_key(acao))
        if action is None:
            raise SpotifyError("Ação desconhecida. Use pausar, continuar, proxima, anterior, volume, "
                               "aleatorio, repetir, curtir ou descurtir.")
        if action == "volume":
            name, args = "volume", parse_volume(valor if valor not in (None, "") else "mais")
        elif action == "shuffle":
            name, args = "shuffle", {"on": _switch(valor)}
        elif action == "repeat":
            name, args = "repeat", {"mode": _repeat(valor)}
        elif action in ("like", "unlike"):
            name, args = "like", {"on": action == "like"}
        else:
            name, args = action, {}
        if self.bridge.linked:
            state = await self._send(name, {k: v for k, v in args.items() if v is not None})
            if action in ("next", "previous", "resume"):
                self.skip_comment(_track_of(state.get("now")))
            return {"ok": True, "mensagem": self._done(action, state), "estado": state}
        if action in SMTC_ACTIONS:
            done = await asyncio.to_thread(self.smtc, action)
            if done:
                return {"ok": True, "mensagem": SMTC_DONE[action] + " (pelos controles de mídia do Windows)"}
            if done is False:
                raise SpotifyError("O Spotify não está aberto (ou não aceitou o comando).")
        raise SpotifyError(f"Sem a ponte do Spicetify não consigo fazer isso. {OFFLINE_HINT}")

    @staticmethod
    def _done(action: str, state: Dict[str, Any]) -> str:
        now = state.get("now") if isinstance(state.get("now"), dict) else None
        song = _song(now) if now else ""
        if action == "pause":
            return f"Pausado{': ' + song if song else ''}."
        if action in ("resume", "toggle", "next", "previous"):
            if not now:
                return "Pronto, mas não vejo nada tocando agora."
            return ("Tocando agora: " if now.get("playing") else "Pausado em: ") + song + "."
        if action == "volume":
            return f"Volume em {state.get('volume')}%." if isinstance(state.get("volume"), (int, float)) \
                else "Volume ajustado."
        if action == "shuffle":
            return "Aleatório " + ("ligado." if state.get("shuffle") else "desligado.")
        if action == "repeat":
            return "Repetição: " + REPEAT_NAMES.get(state.get("repeat"), "ajustada") + "."
        if action == "like":
            return f"Curtida{': ' + song if song else ''} (está nas suas Músicas Curtidas)."
        return f"Tirei das Músicas Curtidas{': ' + song if song else ''}."

    async def now_playing(self) -> Dict[str, Any]:
        if self.bridge.linked:
            state = await self._send("state", {})
            return {"ok": True, "mensagem": describe_state(state), "estado": state}
        track = await asyncio.to_thread(self.reader)
        if track is None:
            return {"ok": True, "mensagem": "Nada tocando no Spotify agora (ou ele está fechado).",
                    "estado": None}
        state = {"now": track.public()}
        message = describe_state(state) + " (lido pelo Windows; sem a ponte não vejo volume nem fila)"
        return {"ok": True, "mensagem": message, "estado": state}


SMTC_DONE = {"pause": "Pausado", "resume": "Continuando", "toggle": "Pronto",
             "next": "Pulei para a próxima", "previous": "Voltei para a anterior"}

spotify_control = SpotifyControl()
