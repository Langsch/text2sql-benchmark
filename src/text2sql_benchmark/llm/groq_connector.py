from __future__ import annotations

import re
import time

from groq import Groq

from .base import LLMConnector, LLMResponse

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _extract_sql(text: str) -> str:
    text = _THINK_RE.sub("", text).strip()
    # strip ```sql ... ``` fences if present
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


class GroqConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        self._client = Groq(api_key=api_key)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0.0,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        raw = response.choices[0].message.content or ""
        return LLMResponse(
            sql=_extract_sql(raw),
            model=self.model_name,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
        )
