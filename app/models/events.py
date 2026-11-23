"""Itens que um cliente de modelo pode emitir além do texto da resposta."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningDelta:
    """
    Trecho do raciocínio interno do modelo (ex.: ``reasoning_content`` do
    Qwen 3.5). Nunca faz parte da resposta: não é salvo, não é falado pelo
    TTS e não volta para o modelo nas rodadas seguintes.
    """
    text: str
