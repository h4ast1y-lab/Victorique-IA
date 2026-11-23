"""
Bank of spontaneous lines (``data/falas.md``), editable by the user.

The factory copy ships as ``falas_padrao.md``; it is copied to the data folder
the first time and never overwritten afterwards. The file is re-read on every
use, so edits apply without restarting.
"""
import random
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.config import DATA_DIR

FACTORY_FILE = Path(__file__).with_name("falas_padrao.md")
CATEGORIES = ("tarde", "bagunca", "organizado", "retorno", "tedio")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def bank_path() -> Path:
    return DATA_DIR / "falas.md"


def ensure_bank(path: Optional[Path] = None) -> Path:
    path = path or bank_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FACTORY_FILE, path)
    return path


def parse_bank(text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {name: [] for name in CATEGORIES}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            current = name if name in sections else None
        elif current and line.startswith("- ") and len(line) > 2:
            sections[current].append(line[2:].strip())
    return sections


def load_bank(path: Optional[Path] = None) -> Dict[str, List[str]]:
    try:
        text = ensure_bank(path).read_text(encoding="utf-8")
    except OSError:
        text = FACTORY_FILE.read_text(encoding="utf-8")
    bank = parse_bank(text)
    # An emptied section falls back to the factory lines.
    factory = parse_bank(FACTORY_FILE.read_text(encoding="utf-8"))
    return {name: bank[name] or factory[name] for name in CATEGORIES}


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", str(text).lower()))


def fill(template: str, facts: Dict[str, Any]) -> str:
    """Replaces {marcadores}; an unknown or empty one becomes an ellipsis-free blank."""
    def value(match: "re.Match[str]") -> str:
        item = facts.get(match.group(1))
        if isinstance(item, (list, tuple)):
            item = ", ".join(str(x) for x in item)
        return str(item) if item not in (None, "") else ""
    text = _PLACEHOLDER.sub(value, template)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r",+([,.!?])", r"\1", text)   # "Ah, {nome}, voltou." without a name
    text = re.sub(r"^[,\s]+", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def split_boredom(entry: str) -> Dict[str, str]:
    """"Título :: fala :: pergunta" (the question is optional)."""
    parts = [p.strip() for p in entry.split("::")]
    if len(parts) == 1:
        return {"titulo": "Um mistério para matar o tédio", "fala": parts[0], "pergunta": ""}
    title, speech = parts[0][:120], parts[1]
    question = " ".join(parts[2:]).strip()
    return {"titulo": title or "Um mistério para matar o tédio", "fala": speech, "pergunta": question}


def pick(
    category: str,
    facts: Dict[str, Any],
    recent: Iterable[str],
    bank: Optional[Dict[str, List[str]]] = None,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """A bank line for the category that is not among the recent ones (when possible).
    Returns {"fala": str} and, for "tedio", {"caso": {"titulo", "pergunta"}}."""
    rng = rng or random
    bank = bank or load_bank()
    entries = list(bank.get(category) or [])
    if not entries:
        return {"fala": ""}
    seen = {normalize(t) for t in recent}

    def rendered(entry: str) -> Dict[str, Any]:
        if category == "tedio":
            parts = split_boredom(entry)
            speech = fill(parts["fala"], facts)
            question = fill(parts["pergunta"], facts) or speech
            return {"fala": speech, "caso": {"titulo": parts["titulo"], "pergunta": question}}
        return {"fala": fill(entry, facts)}

    options = [rendered(e) for e in entries]
    fresh = [o for o in options if normalize(o["fala"]) not in seen]
    return rng.choice(fresh or options)
