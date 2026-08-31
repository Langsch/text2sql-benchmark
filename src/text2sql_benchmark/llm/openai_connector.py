from __future__ import annotations

import time

from openai import OpenAI

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql


class OpenAIConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = OpenAI(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0.0,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        sql = extract_sql(response.choices[0].message.content or "")
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
        )
