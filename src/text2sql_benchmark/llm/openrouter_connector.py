from __future__ import annotations

import time

from openai import APIStatusError, OpenAI, RateLimitError

from .base import LLMConnector, LLMResponse
from .sql_extract import extract_sql

_BASE_URL = "https://openrouter.ai/api/v1"

# Teto de saida. Com raciocinio desligado a resposta esperada e o SQL puro
# (~320 tokens), entao 4000 e folga de mais de 10x e ao mesmo tempo um limite
# de gasto: se um modelo ignorar `reasoning.effort=none`, o estrago para aqui
# em vez de consumir o credito inteiro. O corte e detectado em `truncated`.
_MAX_OUTPUT_TOKENS = 4000

_MAX_ATTEMPTS = 5
_BASE_BACKOFF_SECONDS = 10.0


class OpenRouterConnector(LLMConnector):
    """Acesso a qualquer modelo do OpenRouter pela API compativel com a OpenAI.

    O ponto sensivel e o roteamento. Por padrao o OpenRouter faz balanceamento
    entre os provedores upstream com peso inverso ao quadrado do preco, ou
    seja, troca de provedor entre requisicoes. Numa rodada de 500 questoes isso
    espalha o experimento por provedores e quantizacoes diferentes, e a
    comparacao entre modelos perde validade. Por isso `provider_pin`.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        provider_pin: str = "",
        quantization: str = "",
        reasoning_effort: str = "none",
        max_output_tokens: int = _MAX_OUTPUT_TOKENS,
    ) -> None:
        self.model_name = model_name
        self.provider_pin = provider_pin
        self.quantization = quantization
        # "none" desliga o raciocinio. A tarefa e produzir SQL, nao expor
        # deliberacao: numa medicao o DeepSeek gastou 2.986 tokens de saida
        # raciocinando para devolver 6 linhas de SQL — 35x o que o Sonnet
        # gastou na mesma tarefa. `exclude: true` NAO serve, porque so esconde
        # o raciocinio da resposta e continua cobrando por ele.
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def _provider_body(self) -> dict:
        """Monta o bloco `provider` da requisicao.

        `only` restringe os provedores aceitos; `allow_fallbacks: false` faz a
        chamada falhar em vez de cair silenciosamente em outro provedor. Falhar
        e o comportamento desejado: um erro visivel custa uma repeticao, um
        fallback silencioso invalida a rodada inteira.
        """
        bloco: dict = {}
        if self.provider_pin:
            bloco["only"] = [self.provider_pin]
            bloco["allow_fallbacks"] = False
        if self.quantization:
            bloco["quantizations"] = [self.quantization]
        return bloco

    def _retry_after_seconds(self, exc: APIStatusError, attempt: int) -> float:
        header = (exc.response.headers or {}).get("retry-after")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        return _BASE_BACKOFF_SECONDS * attempt

    def generate(self, prompt: str) -> LLMResponse:
        start = time.perf_counter()
        extra_body: dict = {}
        provider_body = self._provider_body()
        if provider_body:
            extra_body["provider"] = provider_body
        # `usage.include` faz o OpenRouter devolver a contagem normalizada de
        # tokens, necessaria para a tabela de custo do TCC.
        extra_body["usage"] = {"include": True}
        if self.reasoning_effort:
            extra_body["reasoning"] = {"effort": self.reasoning_effort}

        ultimo_erro: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_name,
                    max_completion_tokens=self.max_output_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body=extra_body,
                )
                break
            except (RateLimitError, APIStatusError) as exc:
                status = getattr(exc, "status_code", None)
                # 429 e 502/503 sao transitorios; 4xx de requisicao nao sao e
                # repetir so gasta tempo.
                if status not in (429, 502, 503) or attempt == _MAX_ATTEMPTS:
                    raise
                ultimo_erro = exc
                time.sleep(self._retry_after_seconds(exc, attempt))
        else:  # pragma: no cover - o loop sempre sai por break ou raise
            raise RuntimeError(f"Falha apos {_MAX_ATTEMPTS} tentativas") from ultimo_erro

        latency_ms = (time.perf_counter() - start) * 1000

        # O OpenRouter as vezes responde 200 com um campo `error` no corpo, sem
        # `choices`. Sem esta checagem isso viraria IndexError e seria
        # classificado como system_error, escondendo a causa real.
        if not response.choices:
            erro = getattr(response, "error", None) or getattr(
                response, "model_extra", {}
            ).get("error")
            raise RuntimeError(f"OpenRouter respondeu sem choices: {erro}")

        choice = response.choices[0]
        sql = extract_sql(choice.message.content or "")
        usage = response.usage
        return LLMResponse(
            sql=sql,
            model=self.model_name,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            truncated=choice.finish_reason == "length",
            provider=self._extrair_provider(response),
        )

    @staticmethod
    def _extrair_provider(response) -> str:
        """Le o provedor upstream que atendeu a chamada.

        Campo proprio do OpenRouter, fora do schema da OpenAI — o SDK o guarda
        em `model_extra`. Sem ele nao da para declarar na metodologia sob qual
        provedor a rodada correu.
        """
        direto = getattr(response, "provider", None)
        if isinstance(direto, str):
            return direto
        extra = getattr(response, "model_extra", None) or {}
        return str(extra.get("provider") or "")
