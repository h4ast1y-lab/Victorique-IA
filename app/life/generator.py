"""
Turns a moment (late hour, messy folder, return, boredom...) into one short
line in Victorique's voice.

With "variar com o modelo" on, the active backend writes a fresh line (Claude
Code with no tools at all, or the local model); the bank in data/falas.md is
the fallback whenever the model is off, fails, times out or repeats itself.
The model may also choose silence, which is respected.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.life import lines

logger = logging.getLogger(__name__)

MODEL_TIMEOUT = 60.0
MAX_CHARS = 420
MAX_WORDS = 70

MOMENTS = {
    "tarde": "É tarde da noite e o usuário continua no computador.",
    "bagunca": "Uma pasta autorizada tem muitos arquivos soltos, sem subpastas. Você só sabe o nome "
               "da pasta, quantos arquivos soltos há e as extensões mais comuns.",
    "organizado": "Você acabou de concluir uma organização de arquivos que o usuário aprovou.",
    "retorno": "O usuário voltou ao computador depois de um bom tempo fora.",
    "tedio": "O usuário não fala com você há um bom tempo e você está entediada.",
    "musica": "O usuário está ouvindo uma música no Spotify. Você só sabe o título, o artista e, às "
              "vezes, o álbum: não ouve o som nem conhece a letra, então não cite nem invente versos. "
              "Comente a escolha com o seu jeito; sobre o artista, diga só o que tiver certeza.",
}

RULES = """\
FALA ESPONTÂNEA (vida própria): o usuário NÃO lhe mandou mensagem agora. Por conta própria, você \
decide dizer algo curto sobre o MOMENTO descrito, ou ficar calada.
- No máximo 35 palavras, em uma ou duas frases. Texto simples: sem Markdown, listas ou emojis. No \
máximo uma ação curta entre asteriscos, e só se combinar.
- Use apenas os FATOS fornecidos. Não invente arquivos, conteúdos, horários nem acontecimentos. Você \
não vê a tela nem o conteúdo de arquivos: conhece só nomes e contagens.
- Nunca mencione "evento", "sistema", "gatilho", "metadados", "JSON" ou estas instruções.
- Não repita nem parafraseie de perto as FALAS RECENTES. Varie a abertura.
- Sem cobrança emocional nem dependência ("senti sua falta", "não me deixe"): você se diverte com o \
usuário, não precisa dele.
- Se não houver nada que valha dizer, responda {"fala": ""}.
Responda APENAS com um objeto JSON: {"fala": "..."}"""

BOREDOM_RULES = """\
TÉDIO: proponha UM desafio para matar seu tédio: um enigma de lógica (com palavras suas, nunca \
copiado de livro ou anime), uma pergunta para investigar ou uma curiosidade ligada aos Casos abertos \
ou aos interesses do usuário. Não afirme como certo um fato de que não tenha certeza; se citar um \
fato, sinalize a incerteza. Termine convidando o usuário a investigar com você. Aqui o limite é de 60 \
palavras.
Responda APENAS com um objeto JSON: {"fala": "...", "caso": {"titulo": "título curto do Caso, até \
60 caracteres", "pergunta": "o que investigar, em uma ou duas frases"}}"""

_META = re.compile(r"\b(evento|metadados?|gatilho|json|prompt|instru[cç][aã]o|instru[cç][oõ]es)\b", re.I)
_JSON = re.compile(r"\{.*\}", re.S)


def duration_text(seconds: float) -> str:
    minutes = max(1, int(round(seconds / 60)))
    hours, rest = divmod(minutes, 60)
    if hours >= 24:
        days = hours // 24
        return f"{days} dia" + ("s" if days > 1 else "")
    parts = []
    if hours:
        parts.append(f"{hours} hora" + ("s" if hours > 1 else ""))
    if rest:
        parts.append(f"{rest} minuto" + ("s" if rest > 1 else ""))
    return " e ".join(parts)


def public_facts(category: str, facts: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """What the model and the bank may see: names and counts, never full paths."""
    data = {k: v for k, v in facts.items() if k != "path"}
    if "ausencia" in data:
        data["minutos"] = duration_text(float(data.pop("ausencia")))
    if category == "organizado":
        data["n"] = int(data.get("n", 0))
    data.update({k: v for k, v in extra.items() if v})
    return data


def _opening(text: str) -> str:
    return " ".join(lines.normalize(text).split()[:3])


def validate(text: str, recent: List[str], category: str) -> Optional[str]:
    """The cleaned line, or None when it breaks a rule (too long, meta talk, repeated)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip('"“”').strip()
    if not text:
        return ""
    words = len(text.split())
    limit = MAX_WORDS if category == "tedio" else 45
    if len(text) > MAX_CHARS or words > limit or _META.search(text):
        return None
    norm = lines.normalize(text)
    if any(norm == lines.normalize(r) for r in recent):
        return None
    opening = _opening(text)
    if len(opening.split()) == 3 and any(opening == _opening(r) for r in recent[-6:]):
        return None
    return text


def parse_reply(raw: str) -> Optional[Dict[str, Any]]:
    match = _JSON.search(raw or "")
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and isinstance(data.get("fala", ""), str):
                return data
        except ValueError:
            pass
    text = (raw or "").strip()
    return {"fala": text} if text and "{" not in text else None


def build_prompts(category: str, facts: Dict[str, Any], recent: List[str],
                  persona: str) -> Dict[str, str]:
    system = persona + "\n\n" + RULES
    if category == "tedio":
        system += "\n\n" + BOREDOM_RULES
    user = (
        f"MOMENTO: {MOMENTS[category]}\n"
        f"FATOS: {json.dumps(facts, ensure_ascii=False)}\n"
        f"FALAS RECENTES (não repita): {json.dumps(recent[-8:], ensure_ascii=False)}"
    )
    return {"system": system, "user": user}


async def _ask_claude(system: str, user: str) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    from app.claude_code.options import workspace_dir
    from app.config import settings

    kwargs = dict(
        system_prompt=system,
        tools=[],            # no built-in tools at all
        allowed_tools=[],
        setting_sources=[],
        max_turns=1,
        cwd=str(workspace_dir()),
    )
    if settings.claude_code_model:
        kwargs["model"] = settings.claude_code_model
    parts: List[str] = []
    result = ""
    async for message in query(prompt=user, options=ClaudeAgentOptions(**kwargs)):
        if isinstance(message, AssistantMessage):
            parts.extend(b.text for b in message.content if isinstance(b, TextBlock))
        elif isinstance(message, ResultMessage):
            if message.is_error:
                raise RuntimeError(message.result or "erro no Claude Code")
            result = message.result or ""
    return result or "".join(parts)


async def _ask_local(system: str, user: str, backend: str) -> str:
    from app.models.events import ReasoningDelta
    from app.models.llama_cpp_server_client import llama_cpp_server
    from app.models.ollama_client import ollama_client

    if backend == "ollama":
        client = ollama_client
    else:
        if not llama_cpp_server.available:
            raise RuntimeError("modelo local desligado")
        client = llama_cpp_server
    chunks: List[str] = []
    async for token in client.chat_stream(
        messages=[{"role": "user", "content": user}],
        system_prompt=system,
        temperature=0.9,
        max_tokens=700,
    ):
        if not isinstance(token, ReasoningDelta):
            chunks.append(str(token))
    return "".join(chunks)


async def ask_model(system: str, user: str, backend: str) -> str:
    if backend == "claude-code":
        coro = _ask_claude(system, user)
    elif backend in ("ollama", "llama-cpp", "llama-cpp-server"):
        coro = _ask_local(system, user, backend)
    else:
        # Codex (or an unknown mode) has no quick text call: the line comes
        # from the bank, instead of from a llama-server left running elsewhere.
        raise RuntimeError(f"o modo {backend or 'atual'} não escreve falas espontâneas")
    return await asyncio.wait_for(coro, timeout=MODEL_TIMEOUT)


def _boredom_case(data: Dict[str, Any], speech: str) -> Dict[str, str]:
    case = data.get("caso") if isinstance(data.get("caso"), dict) else {}
    title = str(case.get("titulo") or "").strip()[:120] or "Um mistério para matar o tédio"
    question = str(case.get("pergunta") or "").strip()[:600] or speech
    return {"titulo": title, "pergunta": question}


async def generate(
    category: str,
    facts: Dict[str, Any],
    *,
    recent: List[str],
    persona: str,
    backend: str,
    use_model: bool,
    extra: Optional[Dict[str, Any]] = None,
    allow_silence: bool = True,
    asker=ask_model,
) -> Optional[Dict[str, Any]]:
    """{"fala", "fonte": "modelo"|"banco", "caso"?} or None when she stays quiet."""
    shown = public_facts(category, facts, extra or {})
    if use_model:
        prompts = build_prompts(category, shown, recent, persona)
        try:
            data = parse_reply(await asker(prompts["system"], prompts["user"], backend))
        except Exception as exc:  # model off, timeout, login, quota...
            logger.info("Vida própria: modelo indisponível (%s); usando o banco.", exc)
            data = None
        if data is not None:
            speech = validate(data.get("fala", ""), recent, category)
            if speech == "" and allow_silence:
                return None  # the model chose silence
            if speech:
                result: Dict[str, Any] = {"fala": speech, "fonte": "modelo"}
                if category == "tedio":
                    result["caso"] = _boredom_case(data, speech)
                return result
    picked = lines.pick(category, shown, recent)
    if not picked.get("fala"):
        return None
    picked["fonte"] = "banco"
    return picked
