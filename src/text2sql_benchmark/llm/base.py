from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    sql: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    # True quando o provedor cortou a resposta por atingir max_tokens. Sem isso
    # o corte passa despercebido: o parser descarta o statement incompleto e o
    # resultado parece integro.
    truncated: bool = False


class LLMConnector(ABC):
    model_name: str

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse: ...
