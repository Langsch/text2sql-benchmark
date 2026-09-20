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
    csv_dir: Optional[Path] = typer.Option(
        Path("results/csv"),
        help="Onde exportar os CSVs. Um subdiretório por SGBD é criado dentro dele.",
    ),
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
        # Um subdiretorio por SGBD: os nomes de arquivo so levam etapa e modelo,
        # entao rodar o mesmo modelo em outro SGBD sobrescrevia o anterior sem
        # aviso. Aconteceu em 31/08/2026 — o PostgreSQL comeu os CSVs do SQLite
        # do DeepSeek (os JSONs ficaram intactos, os CSVs foram refeitos).
        csv_dir = Path(csv_dir) / sgbd
        for g in rep.exportar_csv(csv_dir):
            console.print(f"[green]CSV:[/green] {g}")

    console.print()
    console.print("[bold]Arquivos desta execução:[/bold]")
    for n, caminho in (("Etapa 1", e1), ("Etapa 2", e2), ("Etapa 3", e3)):
        console.print(f"  {n}: {caminho}")



@app.command()
def smoke(
    model: str = typer.Option(..., help="Slug do modelo. Ex: qwen/qwen3.8-27b"),
    sgbd: str = typer.Option("sqlite", help="SGBD do prompt: sqlite|postgresql|mariadb."),
    db: str = typer.Option("california_schools", help="Banco de onde sai a questão."),
) -> None:
    """Uma questão, um modelo. Rode antes de gastar a rodada inteira.

    Mostra o SQL gerado, os tokens, o custo estimado e — o mais importante —
    qual provedor upstream do OpenRouter atendeu a chamada. É esse valor que
    entra no `OPENROUTER_PIN_<MODELO>` do .env. As duas falhas mais caras deste
    projeto (cercas markdown e crases no DDL do PostgreSQL) só apareceram em
    execução real, não em leitura de código.
    """
    from rich.console import Console

    from src.text2sql_benchmark.config import load_config
    from src.text2sql_benchmark.dataset import BirdLoader
    from src.text2sql_benchmark.llm.factory import build_llm_connectors
    from src.text2sql_benchmark.prompt import BirdPromptBuilder
    from src.text2sql_benchmark.runner.benchmark_runner import _build_db_connectors

    console = Console()
    cfg = load_config()

    # exigir_pin=False de proposito: descobrir quem atende e justamente o
    # motivo de rodar o smoke, e nao da para pinar antes de saber.
    conectores = build_llm_connectors(cfg, model=model, exigir_pin=False)
    if not conectores:
        disponiveis = "\n  ".join(l.model_name for l in cfg.llms if l.api_key)
        raise typer.BadParameter(
            f"{model!r} não tem chave configurada. Com chave agora:\n  {disponiveis or '(nenhum)'}"
        )
    llm = conectores[0]

    dbs = _build_db_connectors(cfg, sgbd)
    if not dbs:
        raise typer.BadParameter(f"Sem conexão configurada para o SGBD {sgbd!r}.")
    conexao = dbs[0]

    loader = BirdLoader()
    loader.load(cfg.bird_data_path, dialect=sgbd)
    instancias = list(loader.iter_instances(db_id=db, limit=1))
    if not instancias:
        raise typer.BadParameter(f"Nenhuma questão para o banco {db!r}.")
    instancia = instancias[0]

    schema = conexao.get_schema(instancia.db_id)
    prompt = BirdPromptBuilder().build(instancia, schema, sgbd, cfg.use_evidence)

    console.rule(f"[bold]Smoke · {model} · {sgbd} · {db}")
    console.print(f"[dim]Pergunta:[/dim] {instancia.question}\n")

    resposta = llm.generate(prompt)

    console.print("[bold]SQL gerado[/bold]")
    console.print(resposta.sql or "[red](vazio — o extrator não achou SQL na resposta)[/red]")
    console.print()

    if resposta.provider:
        # A resposta traz o nome de exibicao ("Sail Research"); `provider.only`
        # exige o slug ("sail-research"). Colar o nome no .env produziria uma
        # pinagem que nao casa com provedor nenhum.
        from src.text2sql_benchmark.llm.openrouter_catalog import slug_do_provedor

        endpoint = slug_do_provedor(model, resposta.provider)
        chave = "OPENROUTER_PIN_" + model.upper().replace("/", "_").replace("-", "_").replace(".", "_")
        if endpoint:
            console.print(
                f"[bold green]Provedor que atendeu:[/bold green] {endpoint.provider_name} "
                f"· quantização [bold]{endpoint.quantization}[/bold]"
            )
            console.print(f"[dim]Para fixar, ponha no .env:[/dim] {chave}={endpoint.slug}")
            # So alerta quando ha de fato o que escolher: num modelo
            # proprietario todos os endpoints sao do mesmo dono e vem como
            # "unknown", e avisar ali seria alarme falso.
            from src.text2sql_benchmark.llm.openrouter_catalog import listar_endpoints

            quants = {e.quantization for e in listar_endpoints(model)}
            if len(quants) > 1 and endpoint.quantization in ("fp4", "unknown"):
                console.print(
                    f"[yellow]Atenção: {endpoint.quantization} é quantização agressiva ou não "
                    f"declarada, e este modelo tem outras ({', '.join(sorted(quants))}). "
                    f"Veja com:[/yellow] python cli.py providers --model {model}"
                )
        else:
            console.print(f"[bold green]Provedor que atendeu:[/bold green] {resposta.provider}")
            console.print(f"[dim]Slug não encontrado no catálogo; confira com:[/dim] "
                          f"python cli.py providers --model {model}")
    else:
        console.print("[yellow]O provedor não veio na resposta (normal fora do OpenRouter).[/yellow]")

    console.print(
        f"\nTokens: {resposta.input_tokens} entrada / {resposta.output_tokens} saída"
        f"  ·  Latência: {resposta.latency_ms:.0f} ms"
    )
    if resposta.truncated:
        console.print("[red]Resposta truncada por limite de tokens — o SQL pode estar incompleto.[/red]")

    # Executa de verdade: um SQL que parece bom e nao roda nao serve de nada.
    try:
        conexao.execute(resposta.sql, timeout=cfg.timeout_seconds, db_id=instancia.db_id)
        console.print("[green]A query executou no banco.[/green]")
    except Exception as exc:
        console.print(f"[red]A query falhou ao executar:[/red] {exc}")



@app.command()
def providers(
    model: str = typer.Option(..., help="Slug do modelo. Ex: qwen/qwen3.8-27b"),
) -> None:
    """Lista os provedores que servem um modelo, com a quantização de cada um.

    A mesma slug pode ser servida em fp4, fp8 ou bf16 conforme o provedor, e a
    quantização muda a fidelidade do modelo. Escolher o provedor sabendo disso
    é decisão de metodologia, não de infraestrutura — e é o valor que entra no
    `OPENROUTER_PIN_<MODELO>` do .env.
    """
    from rich.console import Console
    from rich.table import Table

    from src.text2sql_benchmark.llm.openrouter_catalog import listar_endpoints

    console = Console()
    endpoints = listar_endpoints(model)
    if not endpoints:
        console.print(f"[yellow]Nenhum provedor listado para {model}.[/yellow]")
        return

    t = Table(title=f"Provedores de {model} ({len(endpoints)})")
    t.add_column("Provedor")
    t.add_column("slug para o .env", style="cyan")
    t.add_column("Quantização")
    t.add_column("Uptime 24h", justify="right")
    ordem = {"bf16": 0, "fp16": 1, "fp8": 2, "fp4": 3, "unknown": 4}
    for ep in sorted(endpoints, key=lambda e: (ordem.get(e.quantization, 5), -e.uptime_30d)):
        cor = {"fp4": "yellow", "unknown": "yellow"}.get(ep.quantization, "green")
        t.add_row(ep.provider_name, ep.slug,
                  f"[{cor}]{ep.quantization}[/{cor}]", f"{ep.uptime_30d:.1f}%")
    console.print(t)

    chave = "OPENROUTER_PIN_" + model.upper().replace("/", "_").replace("-", "_").replace(".", "_")
    console.print(f"\n[dim]No .env:[/dim] {chave}=<slug>")

@app.command()
def compare(
    stage1: list[Path] = typer.Option(..., "--stage1", help="JSONs de Etapa 1. Repita a opção para cada modelo/SGBD."),
    stage2: list[Path] = typer.Option([], "--stage2", help="JSONs de Etapa 2. Repita na mesma ordem dos --stage3."),
    stage3: list[Path] = typer.Option([], "--stage3", help="JSONs de Etapa 3, pareados por posição com os --stage2."),
    csv_dir: Optional[Path] = typer.Option(None, help="Diretório para exportar os CSVs."),
) -> None:
    """Compara modelos entre si sobre as mesmas questões.

    O relatório consolidado descreve um modelo por vez; este põe todos lado a
    lado e mostra onde discordam, que é a pergunta central do trabalho.

    Com --stage2 e --stage3 sai também o efeito dos índices por modelo e a
    verificação de em quantas células as queries incorretas ganham mais que as
    corretas.
    """
    from src.text2sql_benchmark.report.comparative_report import ComparativeReport

    if stage3 and len(stage3) != len(stage2):
        raise typer.BadParameter(
            f"--stage2 e --stage3 são pareados por posição: "
            f"{len(stage2)} e {len(stage3)} recebidos."
        )
    rep = ComparativeReport.from_files(list(stage1), list(stage2), list(stage3))
    rep.imprimir()

    if csv_dir:
        typer.echo("")
        for g in rep.exportar_csv(csv_dir):
            typer.echo(f"CSV: {g}")


if __name__ == "__main__":
    app()
