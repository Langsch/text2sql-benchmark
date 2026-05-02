from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="text2sql",
    help="Benchmark comparativo de LLMs na geração de SQL para múltiplos SGBDs.",
    no_args_is_help=True,
)


@app.command()
def run(
    limit: Optional[int] = typer.Option(None, help="Limitar número de instâncias do dataset."),
    difficulty: Optional[str] = typer.Option(None, help="Filtrar por dificuldade: simple|moderate|challenging."),
    model: Optional[str] = typer.Option(None, help="Rodar apenas um modelo específico."),
    sgbd: Optional[str] = typer.Option(None, help="Rodar apenas um SGBD específico: postgresql|mariadb|sqlite."),
    db: Optional[str] = typer.Option(None, help="Rodar apenas um banco: student_club|formula_1|thrombosis_prediction|..."),
) -> None:
    """Executa o benchmark completo (dataset × LLMs × SGBDs)."""
    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.runner import BenchmarkRunner

    cfg = load_config()
    runner = BenchmarkRunner(cfg)
    runner.run(limit=limit, difficulty=difficulty, db_id=db)


@app.command()
def report(
    results_file: Path = typer.Argument(..., help="Caminho para o arquivo JSON de resultados."),
) -> None:
    """Exibe relatório resumido de um arquivo de resultados."""
    from src.text2sql_benchmark.report import ReportGenerator

    gen = ReportGenerator.from_file(results_file)
    gen.summary_table()


if __name__ == "__main__":
    app()
