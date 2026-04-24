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


class LLMConnector(ABC):
    model_name: str

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse: ...
