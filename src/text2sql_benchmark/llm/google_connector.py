from __future__ import annotations

import time

from google import genai
from google.genai import types

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql

# Mesma folga usada nos demais conectores: os modelos com raciocinio consomem
# deste teto antes de emitir texto.
_MAX_OUTPUT_TOKENS = 16000


class GoogleConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = genai.Client(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        # Sem `temperature`, pelo mesmo motivo dos outros provedores: fixar o
        # parametro so onde ele e aceito criaria assimetria entre os modelos
        # comparados (docs/arquitetura.md, 5.1).
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=_MAX_OUTPUT_TOKENS,
            ),
        )
        latency_ms = (time.perf_counter() - start) * 1000
        # `response.text` levanta ou devolve None quando a resposta vem sem
        # bloco de texto — caso do corte por MAX_TOKENS durante o raciocinio.
        texto = response.text or ""
        sql = extract_sql(texto)
        usage = response.usage_metadata
        candidato = (response.candidates or [None])[0]
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=latency_ms,
            truncated=str(getattr(candidato, "finish_reason", "")).endswith("MAX_TOKENS"),
        )
