from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    temperature: float = 0.0
    max_tokens: int = 1024


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


def load_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        bird_data_path=Path(os.getenv("BIRD_DATA_PATH", "./data/bird/by_db")),
        use_evidence=os.getenv("BIRD_USE_EVIDENCE", "true").lower() == "true",
        timeout_seconds=int(os.getenv("BENCHMARK_TIMEOUT_SECONDS", "30")),
        output_dir=Path(os.getenv("BENCHMARK_OUTPUT_DIR", "./results/runs")),
        llms=[
            LLMConfig("claude-sonnet-5", os.getenv("ANTHROPIC_API_KEY", "")),
            # TODO: confirmar os IDs atuais de OpenAI e Google ao adicionar as chaves.
            # Os modelos da Groq usados ate 06/2026 foram descontinuados sem aviso e
            # passaram a retornar 404 — verificar antes de rodar o benchmark pago.
            LLMConfig("gpt-5.2", os.getenv("OPENAI_API_KEY", "")),
            LLMConfig("gemini-2.5-pro", os.getenv("GOOGLE_API_KEY", "")),
            LLMConfig("qwen/qwen3.8-27b", os.getenv("GROQ_API_KEY", "")),
        ],
        databases=[
            DBConfig("postgresql", os.getenv("POSTGRES_URL", "")),
            DBConfig("mariadb", os.getenv("MARIADB_URL", "")),
            DBConfig("sqlite", os.getenv("SQLITE_DB_DIR", "./data/bird/dev_databases")),
        ],
    )
