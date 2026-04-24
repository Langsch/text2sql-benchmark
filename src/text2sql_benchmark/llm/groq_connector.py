from __future__ import annotations

import time

from groq import Groq

from .base import LLMConnector, LLMResponse

GROQ_MODELS = {
    "llama": "llama-3.3-70b-versatile",
    "qwen": "qwen-2.5-72b-instruct",
}


class GroqConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = Groq(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0.0,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        sql = response.choices[0].message.content or ""
        return LLMResponse(
            sql=sql.strip(),
            model=self.model_name,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
        )
