from __future__ import annotations

import time

from openai import OpenAI

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql

# Folga acima da saida esperada (~320 tokens de SQL). Os modelos de raciocinio
# consomem deste mesmo teto antes de emitir o primeiro token de texto; um teto
# curto corta a resposta antes do SQL aparecer.
_MAX_OUTPUT_TOKENS = 16000


class OpenAIConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = OpenAI(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        # Sem `temperature`: os modelos de raciocinio rejeitam parametros de
        # amostragem com 400, e fixa-la so onde o provedor aceita criaria
        # assimetria entre os modelos comparados (docs/arquitetura.md, 5.1).
        # `max_completion_tokens` substitui o `max_tokens` descontinuado.
        response = self._client.chat.completions.create(
            model=self.model_name,
            max_completion_tokens=_MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        choice = response.choices[0]
        sql = extract_sql(choice.message.content or "")
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            truncated=choice.finish_reason == "length",
        )
