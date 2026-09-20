from __future__ import annotations

from dataclasses import dataclass

import httpx

_ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{model}/endpoints"


@dataclass
class Endpoint:
    """Um provedor upstream que serve um modelo no OpenRouter."""

    provider_name: str   # como aparece na resposta: "Sail Research"
    slug: str            # como se escreve em provider.only: "sail-research"
    quantization: str    # fp4 | fp8 | bf16 | unknown
    uptime_30d: float
    context_length: int

    @property
    def rotulo(self) -> str:
        return f"{self.provider_name} ({self.quantization})"


def listar_endpoints(model: str, timeout: float = 20.0) -> list[Endpoint]:
    """Lista os provedores que servem um modelo, com a quantizacao de cada um.

    Existe porque a mesma slug pode ser servida em fp4, fp8 ou bf16 conforme o
    provedor, e a quantizacao muda a fidelidade do modelo. Escolher o provedor
    no olho, sabendo a quantizacao, e parte da metodologia — nao detalhe de
    infraestrutura.
    """
    resp = httpx.get(_ENDPOINTS_URL.format(model=model), timeout=timeout)
    resp.raise_for_status()
    dados = resp.json().get("data", {}).get("endpoints", [])
    saida: list[Endpoint] = []
    for e in dados:
        # O slug so aparece dentro de `tag`, no formato "<slug>/<quant>" ou
        # apenas "<slug>" quando o provedor nao declara quantizacao.
        tag = str(e.get("tag") or "")
        saida.append(
            Endpoint(
                provider_name=str(e.get("provider_name") or ""),
                slug=tag.split("/")[0],
                quantization=str(e.get("quantization") or "unknown"),
                uptime_30d=float(e.get("uptime_last_1d") or 0.0),
                context_length=int(e.get("context_length") or 0),
            )
        )
    return saida


def slug_do_provedor(model: str, provider_name: str) -> Endpoint | None:
    """Encontra o endpoint pelo nome que veio na resposta da chamada.

    A resposta traz o nome de exibicao ("Sail Research"), mas `provider.only`
    exige o slug ("sail-research"). Colar o nome de exibicao no .env produz uma
    pinagem que nao casa com provedor nenhum.
    """
    alvo = provider_name.strip().lower()
    for ep in listar_endpoints(model):
        if ep.provider_name.strip().lower() == alvo:
            return ep
    return None
