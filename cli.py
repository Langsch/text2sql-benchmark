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
    resume: Optional[Path] = typer.Option(None, help="Retomar uma rodada interrompida a partir do seu JSON."),
) -> None:
    """Executa o benchmark completo (dataset × LLMs × SGBDs)."""
    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.runner import BenchmarkRunner

    cfg = load_config()
    runner = BenchmarkRunner(cfg)
    runner.run(limit=limit, difficulty=difficulty, db_id=db, sgbd=sgbd, model=model, resume=resume)


@app.command()
def report(
    results_file: Path = typer.Argument(..., help="Caminho para o arquivo JSON de resultados."),
) -> None:
    """Exibe relatório resumido de um arquivo de resultados."""
    from src.text2sql_benchmark.report import ReportGenerator

    gen = ReportGenerator.from_file(results_file)
    gen.summary_table()


@app.command()
def index(
    limit: Optional[int] = typer.Option(None, help="Limitar número de instâncias por banco."),
    difficulty: Optional[str] = typer.Option(None, help="Filtrar por dificuldade: simple|moderate|challenging."),
    model: Optional[str] = typer.Option(None, help="Rodar apenas um modelo específico."),
    db: Optional[str] = typer.Option(None, help="Rodar apenas um banco: student_club|formula_1|..."),
    sgbd: str = typer.Option("sqlite", help="SGBD alvo: sqlite|postgresql|mariadb."),
) -> None:
    """Executa o benchmark de sugestão de índices."""
    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.runner.index_runner import IndexBenchmarkRunner

    cfg = load_config()
    runner = IndexBenchmarkRunner(cfg, dialect=sgbd)
    runner.run(limit=limit, difficulty=difficulty, db_id=db, model=model)


@app.command()
def revalidate(
    stage1: Path = typer.Option(..., help="JSON da Etapa 1 (queries geradas)."),
    stage2: Path = typer.Option(..., help="JSON da Etapa 2 (índices sugeridos)."),
    model: str = typer.Option(..., help="Modelo a revalidar. Ex: claude-sonnet-5"),
    db: Optional[str] = typer.Option(None, help="Rodar apenas um banco."),
    sgbd: str = typer.Option("sqlite", help="SGBD alvo: sqlite|postgresql|mariadb."),
) -> None:
    """Etapa 3: aplica os índices da Etapa 2 e re-executa as queries da Etapa 1."""
    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.runner.revalidation_runner import RevalidationRunner

    cfg = load_config()
    runner = RevalidationRunner(cfg, dialect=sgbd)
    runner.run(stage1_path=stage1, stage2_path=stage2, model=model, db_id=db)


@app.command()
def index_report(
    results_file: Path = typer.Argument(..., help="Caminho para o arquivo JSON de resultados de índices."),
) -> None:
    """Exibe relatório resumido de benchmark de índices."""
    from src.text2sql_benchmark.report.index_report import IndexReportGenerator

    gen = IndexReportGenerator.from_file(results_file)
    gen.summary_table()
    gen.model_summary_table()


@app.command()
def consolidated(
    stage1: Path = typer.Option(..., help="JSON da Etapa 1 (text2sql)."),
    stage2: Path = typer.Option(..., help="JSON da Etapa 2 (índices)."),
    model: str = typer.Option(..., help="Modelo. Ex: claude-sonnet-5"),
    stage3: Optional[Path] = typer.Option(None, help="JSON da Etapa 3 (revalidação)."),
    csv_dir: Optional[Path] = typer.Option(None, help="Diretório para exportar CSVs."),
) -> None:
    """Relatório consolidado das três etapas para um modelo."""
    from src.text2sql_benchmark.report.consolidated_report import ConsolidatedReport

    rep = ConsolidatedReport.from_files(model, stage1, stage2, stage3)
    rep.imprimir()

    if csv_dir:
        gerados = rep.exportar_csv(csv_dir)
        typer.echo("")
        for g in gerados:
            typer.echo(f"CSV: {g}")


@app.command()
def pipeline(
    model: str = typer.Option(..., help="Modelo. Ex: claude-sonnet-5"),
    sgbd: str = typer.Option("sqlite", help="SGBD alvo: sqlite|postgresql|mariadb."),
    db: Optional[str] = typer.Option(None, help="Rodar apenas um banco."),
    limit: Optional[int] = typer.Option(None, help="Limitar questões (para teste barato)."),
    csv_dir: Optional[Path] = typer.Option(Path("results/csv"), help="Onde exportar os CSVs."),
    skip_stage1: Optional[Path] = typer.Option(None, help="Reaproveitar uma Etapa 1 já feita."),
    skip_stage2: Optional[Path] = typer.Option(None, help="Reaproveitar uma Etapa 2 já feita."),
) -> None:
    """Executa as três etapas em sequência e emite o relatório consolidado.

    Encadeia os arquivos automaticamente: a saída da Etapa 1 e da Etapa 2
    alimentam a Etapa 3 sem intervenção manual, que é onde é fácil cruzar o
    JSON errado sem perceber.
    """
    from rich.console import Console

    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.report.consolidated_report import ConsolidatedReport
    from src.text2sql_benchmark.runner import BenchmarkRunner
    from src.text2sql_benchmark.runner.index_runner import IndexBenchmarkRunner
    from src.text2sql_benchmark.runner.revalidation_runner import RevalidationRunner

    console = Console()
    cfg = load_config()

    def cabecalho(n: int, titulo: str) -> None:
        console.rule(f"[bold]Etapa {n} — {titulo}  ·  {model} · {sgbd}")

    if skip_stage1:
        e1 = Path(skip_stage1)
        console.print(f"[cyan]Etapa 1 reaproveitada:[/cyan] {e1}")
    else:
        cabecalho(1, "Text2SQL")
        e1 = BenchmarkRunner(cfg).run(limit=limit, db_id=db, sgbd=sgbd, model=model)

    if skip_stage2:
        e2 = Path(skip_stage2)
        console.print(f"[cyan]Etapa 2 reaproveitada:[/cyan] {e2}")
    else:
        cabecalho(2, "Sugestão de índices")
        e2 = IndexBenchmarkRunner(cfg, dialect=sgbd).run(
            limit=limit, db_id=db, model=model
        )

    cabecalho(3, "Revalidação")
    e3 = RevalidationRunner(cfg, dialect=sgbd).run(
        stage1_path=e1, stage2_path=e2, model=model, db_id=db
    )

    console.rule("[bold]Relatório consolidado")
    rep = ConsolidatedReport.from_files(model, e1, e2, e3)
    rep.imprimir()

    if csv_dir:
        for g in rep.exportar_csv(csv_dir):
            console.print(f"[green]CSV:[/green] {g}")

    console.print()
    console.print("[bold]Arquivos desta execução:[/bold]")
    for n, caminho in (("Etapa 1", e1), ("Etapa 2", e2), ("Etapa 3", e3)):
        console.print(f"  {n}: {caminho}")


if __name__ == "__main__":
    app()
