from __future__ import annotations

import os
import time

import anthropic

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql


class AnthropicConnector(LLMConnector):
    def __init__(self, model_name: str, api_key: str) -> None:
        self.model_name = model_name
        # Chaves "identity-linked" exigem o header anthropic-workspace-id em
        # toda requisicao; sem ele a API responde 400. Chaves comuns ignoram.
        workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self._client = anthropic.Anthropic(api_key=api_key, default_headers=headers)

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        # Sem `temperature`: os modelos Claude atuais rejeitam parametros de
        # sampling com 400. O thinking adaptativo e ligado por padrao e consome
        # do mesmo max_tokens, por isso a folga acima da saida esperada (~320).
        message = self._client.messages.create(
            model=self.model_name,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        # A resposta e uma lista de blocos. Com thinking ligado (padrao nos
        # modelos atuais) o primeiro bloco e um ThinkingBlock, que nao tem
        # .text — por isso e preciso filtrar pelos blocos de texto.
        texto = "\n".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        )
        sql = extract_sql(texto)
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=latency_ms,
            truncated=message.stop_reason == "max_tokens",
        )
