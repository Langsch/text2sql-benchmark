from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# Modelos servidos por mais de um provedor upstream no OpenRouter, com a
# contagem observada em 31/08/2026. Para estes, rodar sem `provider_pin` faz o
# roteamento trocar de provedor no meio da rodada — e provedores diferentes
# servem quantizacoes diferentes. O runner recusa a rodada nesse caso.
# Ver docs/arquitetura.md, 5.4.
PROVEDORES_POR_MODELO: dict[str, int] = {
    "deepseek/deepseek-v4-flash-0731": 30,
    "qwen/qwen3.8-27b": 11,
    "anthropic/claude-sonnet-5": 5,
    "openai/gpt-5.6-luna": 3,
    "google/gemini-3.1-flash-lite": 2,
}


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    # Como o modelo e acessado. Determina o conector; nao inferir do nome, que
    # colide: a slug "openai/gpt-5.6-luna" e do OpenRouter, nao da OpenAI.
    provider: str = "openrouter"
    # Provedor upstream fixado no OpenRouter. Vazio = roteamento automatico.
    provider_pin: str = ""
    # Quantizacao exigida, ex. "fp8". So faz sentido para modelos abertos.
    quantization: str = ""
    # Esforco de raciocinio no OpenRouter: none|minimal|low|medium|high.
    # "none" e o padrao do projeto — ver docs/arquitetura.md, 5.7.
    reasoning_effort: str = "none"

    @property
    def exige_pin(self) -> bool:
        """True quando rodar sem pinagem produziria dado nao reproduzivel."""
        if self.provider != "openrouter":
            return False
        return PROVEDORES_POR_MODELO.get(self.model_name, 1) > 1


@dataclass
class DBConfig:
    dialect: str  # "postgresql" | "mariadb" | "sqlite"
    url: str      # connection string ou caminho para .db


@dataclass
class BenchmarkConfig:
    bird_data_path: Path
    use_evidence: bool
    timeout_seconds: int
    output_dir: Path
    llms: list[LLMConfig] = field(default_factory=list)
    databases: list[DBConfig] = field(default_factory=list)


def _pin(slug: str) -> str:
    """Le a pinagem de provedor da env.

    A chave e derivada da slug: "qwen/qwen3.8-27b" ->
    OPENROUTER_PIN_QWEN_QWEN3_8_27B. Descubra o valor rodando
    `python cli.py smoke --model <slug>`, que imprime quem atendeu.
    """
    chave = "OPENROUTER_PIN_" + slug.upper().replace("/", "_").replace("-", "_").replace(".", "_")
    return os.getenv(chave, "").strip()


def load_config() -> BenchmarkConfig:
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # O Claude Sonnet 5 rodou pela API nativa da Anthropic em 30/08/2026 e nao
    # sera reexecutado. A entrada nativa fica para reproduzir aquela rodada; a
    # entrada via OpenRouter existe para a subamostra de validacao entre rotas.
    llms = [
        LLMConfig("claude-sonnet-5", os.getenv("ANTHROPIC_API_KEY", ""), provider="anthropic"),
    ]
    for slug, quant in (
        ("openai/gpt-5.6-luna", ""),
        ("google/gemini-3.1-flash-lite", ""),
        ("qwen/qwen3.8-27b", os.getenv("OPENROUTER_QUANT_QWEN", "")),
        ("deepseek/deepseek-v4-flash-0731", os.getenv("OPENROUTER_QUANT_DEEPSEEK", "")),
        ("anthropic/claude-sonnet-5", ""),
    ):
        llms.append(
            LLMConfig(
                slug,
                openrouter_key,
                provider="openrouter",
                provider_pin=_pin(slug),
                quantization=quant,
                reasoning_effort=os.getenv("OPENROUTER_REASONING_EFFORT", "none"),
            )
        )

    return BenchmarkConfig(
        bird_data_path=Path(os.getenv("BIRD_DATA_PATH", "./data/bird/by_db")),
        use_evidence=os.getenv("BIRD_USE_EVIDENCE", "true").lower() == "true",
        timeout_seconds=int(os.getenv("BENCHMARK_TIMEOUT_SECONDS", "30")),
        output_dir=Path(os.getenv("BENCHMARK_OUTPUT_DIR", "./results/runs")),
        llms=llms,
        databases=[
            DBConfig("postgresql", os.getenv("POSTGRES_URL", "")),
            DBConfig("mariadb", os.getenv("MARIADB_URL", "")),
            DBConfig("sqlite", os.getenv("SQLITE_DB_DIR", "./data/bird/dev_databases")),
        ],
    )
