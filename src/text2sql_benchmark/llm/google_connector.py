from __future__ import annotations

import time

import google.generativeai as genai

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql


class GoogleConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(self.model_name)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        response = self._model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.0, max_output_tokens=1024),
        )
        latency_ms = (time.perf_counter() - start) * 1000
        sql = extract_sql(response.text)
        usage = response.usage_metadata
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            latency_ms=latency_ms,
        )
