from __future__ import annotations

import time

import anthropic

from .base import LLMConnector, LLMResponse


class AnthropicConnector(LLMConnector):
    model_name = "claude-sonnet-4-5"

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        message = self._client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        sql = message.content[0].text.strip()
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
        )
