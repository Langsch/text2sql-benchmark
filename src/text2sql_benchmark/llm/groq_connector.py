from __future__ import annotations

import time

from groq import APIStatusError, Groq, RateLimitError

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql

# A Groq soma `max_tokens` ao tamanho do prompt para decidir o limite de
# tokens por minuto. Reservar 4096 fazia o prompt de 3.3k estourar o teto de
# 6k/min (erro 413) mesmo com a saida real usando ~320 tokens.
_MAX_OUTPUT_TOKENS = 1024

_MAX_ATTEMPTS = 5
_BASE_BACKOFF_SECONDS = 20.0


class GroqConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = Groq(api_key=api_key)

    def _retry_after_seconds(self, exc: APIStatusError, attempt: int) -> float:
        """Prefer the server's retry-after; fall back to linear backoff."""
        header = (exc.response.headers or {}).get("retry-after")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        # O limite da Groq e por minuto, entao esperar menos que isso nao ajuda.
        return _BASE_BACKOFF_SECONDS * attempt

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_name,
                    temperature=0.0,
                    max_tokens=_MAX_OUTPUT_TOKENS,
                    messages=[{"role": "user", "content": prompt}],
                )
                break
            except (RateLimitError, APIStatusError) as exc:
                # 413 = prompt + max_tokens acima do teto por minuto; 429 = cota
                # estourada. Ambos passam depois que a janela de 1 min rola.
                status = getattr(exc, "status_code", None)
                if status not in (413, 429) or attempt == _MAX_ATTEMPTS:
                    raise
                time.sleep(self._retry_after_seconds(exc, attempt))
        latency_ms = (time.perf_counter() - start) * 1000
        raw = response.choices[0].message.content or ""
        return LLMResponse(
            sql=extract_sql(raw),
            model=self.model_name,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            truncated=response.choices[0].finish_reason == "length",
        )
