"""
The spotify_* tools the chats get (app/spotify/control.py does the work): the
same names, descriptions and parameters for the local models (tool registry)
and for Claude Code (the in-process MCP server). Controlling the music is
harmless, so none of them asks for approval.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from app.spotify.control import SpotifyError, spotify_control

TYPE_PARAM = {
    "type": "string",
    "enum": ["musica", "artista", "album", "playlist", "podcast", "episodio", "curtidas"],
    "description": "O que é o pedido. Padrão: musica. 'curtidas' toca as Músicas Curtidas (sem pedido).",
}
REQUEST_PARAM = {
    "type": "string",
    "description": "O que buscar no Spotify (ex.: 'Bohemian Rhapsody Queen', 'Taylor Swift', 'lo-fi para estudar') "
                   "ou um link/URI do Spotify (open.spotify.com/... ou spotify:track:...).",
}

DESCRIPTIONS: Dict[str, str] = {
    "spotify_tocar": (
        "Toca no Spotify do usuário uma música, um artista, um álbum, uma playlist (as da biblioteca dele "
        "vêm primeiro), um podcast ou as Músicas Curtidas. Busca no próprio Spotify e toca o melhor "
        "resultado; devolve o que ficou tocando e outras opções. Se o Spotify estiver fechado, ele abre."
    ),
    "spotify_fila": "Põe uma música (ou episódio) na fila do Spotify, para tocar depois da atual.",
    "spotify_buscar": (
        "Busca no Spotify sem tocar nada e devolve as opções com o URI de cada uma (para o usuário "
        "escolher; depois passe o URI escolhido a spotify_tocar)."
    ),
    "spotify_controlar": (
        "Controla o player do Spotify. acao: pausar, continuar, proxima, anterior, volume (valor: 0 a "
        "100, '+10', '-10', 'mais', 'menos' ou 'mudo'), aleatorio (valor: ligar/desligar; sem valor "
        "alterna), repetir (valor: desligar, lista ou faixa), curtir ou descurtir (a música atual)."
    ),
    "spotify_tocando": (
        "Diz o que está tocando no Spotify agora: música, artista, álbum, posição, volume, aleatório, "
        "repetição, se está curtida e as próximas da fila."
    ),
}

SCHEMAS: Dict[str, Dict[str, Any]] = {
    "spotify_tocar": {
        "type": "object",
        "properties": {"pedido": REQUEST_PARAM, "tipo": TYPE_PARAM},
        "required": [],
    },
    "spotify_fila": {
        "type": "object",
        "properties": {
            "pedido": REQUEST_PARAM,
            "tipo": {"type": "string", "enum": ["musica", "episodio"], "description": "Padrão: musica."},
        },
        "required": ["pedido"],
    },
    "spotify_buscar": {
        "type": "object",
        "properties": {
            "pedido": REQUEST_PARAM,
            "tipo": {**TYPE_PARAM, "enum": ["musica", "artista", "album", "playlist", "podcast", "episodio"]},
            "limite": {"type": "integer", "description": "Quantos resultados (1 a 10). Padrão: 5."},
        },
        "required": ["pedido"],
    },
    "spotify_controlar": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["pausar", "continuar", "proxima", "anterior", "volume", "aleatorio", "repetir",
                         "curtir", "descurtir"],
                "description": "O que fazer.",
            },
            "valor": {
                "type": "string",
                "description": "Para volume (0-100, '+10', 'mais', 'menos', 'mudo'), aleatorio (ligar/desligar) "
                               "e repetir (desligar/lista/faixa). As outras ações não usam.",
            },
        },
        "required": ["acao"],
    },
    "spotify_tocando": {"type": "object", "properties": {}, "required": []},
}


async def spotify_tocar(pedido: str = "", tipo: str = "musica") -> Dict[str, Any]:
    return await spotify_control.play(pedido, tipo)


async def spotify_fila(pedido: str, tipo: str = "musica") -> Dict[str, Any]:
    return await spotify_control.queue(pedido, tipo)


async def spotify_buscar(pedido: str, tipo: str = "musica", limite: int = 5) -> Dict[str, Any]:
    return await spotify_control.search(pedido, tipo, limite)


async def spotify_controlar(acao: str, valor: Any = None) -> Dict[str, Any]:
    return await spotify_control.control(acao, valor)


async def spotify_tocando() -> Dict[str, Any]:
    return await spotify_control.now_playing()


FUNCTIONS: Dict[str, Callable[..., Awaitable[Dict[str, Any]]]] = {
    "spotify_tocar": spotify_tocar,
    "spotify_fila": spotify_fila,
    "spotify_buscar": spotify_buscar,
    "spotify_controlar": spotify_controlar,
    "spotify_tocando": spotify_tocando,
}
NAMES: List[str] = list(FUNCTIONS)


def as_text(result: Dict[str, Any]) -> str:
    """A tool result for a model that reads text: the message, then the choices."""
    lines = [str(result.get("mensagem") or "Pronto.")]
    others = result.get("outras_opcoes") or []
    if others:
        lines.append("Outras opções (para trocar, chame spotify_tocar com o URI):")
        lines.extend(f"- {o['nome']}" + (f" — {o['de']}" if o.get("de") else "") + f" ({o['uri']})"
                     for o in others)
    found = result.get("resultados") or []
    if found:
        lines.append("URIs: " + "; ".join(f"{i}. {r['uri']}" for i, r in enumerate(found, 1)))
    return "\n".join(lines)


async def run(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Calls a tool by name with the model's arguments (unknown keys dropped).
    SpotifyError says what went wrong, for the user."""
    func = FUNCTIONS.get(name)
    if func is None:
        raise SpotifyError(f"Ferramenta do Spotify desconhecida: {name}")
    allowed = SCHEMAS[name]["properties"]
    params = {k: v for k, v in (args or {}).items() if k in allowed and v is not None}
    missing = [k for k in SCHEMAS[name]["required"] if not params.get(k)]
    if missing:
        raise SpotifyError("Faltou: " + ", ".join(missing))
    return await func(**params)
