"""Relatorio consolidado das tres etapas para um modelo.

Cruza os JSONs da Etapa 1 (text2sql), Etapa 2 (indices sobre queries gabarito)
e Etapa 3 (revalidacao sobre queries geradas) numa visao unica, e exporta CSV
para analise estatistica externa.

Sobre as estatisticas de speedup: a media de razoes e enganosa quando a
distribuicao tem outliers — no BIRD algumas queries saem de minutos para
milissegundos e sozinhas dominam a media. Por isso o relatorio reporta a
mediana como numero central, a razao das medias como medida de carga total, e
os quartis para mostrar a dispersao.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def _ler(path: Path | None) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _quartis(valores: list[float]) -> tuple[float, float, float]:
    """Devolve (p25, mediana, p75). Robusto para listas curtas."""
    if not valores:
        return (0.0, 0.0, 0.0)
    ordenado = sorted(valores)
    mediana = statistics.median(ordenado)
    if len(ordenado) < 4:
        return (ordenado[0], mediana, ordenado[-1])
    metade = len(ordenado) // 2
    p25 = statistics.median(ordenado[:metade])
    p75 = statistics.median(ordenado[-metade:])
    return (p25, mediana, p75)


class ConsolidatedReport:
    def __init__(
        self,
        model: str,
        stage1: list[dict],
        stage2: list[dict],
        stage3: list[dict],
    ) -> None:
        self.model = model
        self.s1 = [r for r in stage1 if r.get("model") == model]
        self.s2 = [r for r in stage2 if r.get("model") == model and not r.get("error")]
        self.s3 = [r for r in stage3 if r.get("model") == model and not r.get("error")]

    @classmethod
    def from_files(
        cls,
        model: str,
        stage1: Path,
        stage2: Path,
        stage3: Path | None = None,
    ) -> "ConsolidatedReport":
        return cls(model, _ler(stage1), _ler(stage2), _ler(stage3))

    # ---------- Etapa 1 ----------

    def etapa1_geral(self) -> dict:
        n = len(self.s1)
        if not n:
            return {}
        executaram = [r for r in self.s1 if not r.get("error")]
        return {
            "questoes": n,
            "executaram": len(executaram),
            "erros": n - len(executaram),
            "execution_accuracy": sum(1 for r in self.s1 if r["execution_accuracy"]),
            "exact_match": sum(1 for r in self.s1 if r["exact_match"]),
            "usam_indice": sum(
                1 for r in executaram if (r.get("explain_parsed") or {}).get("uses_index")
            ),
        }

    def tabela_etapa1(self) -> None:
        g = self.etapa1_geral()
        if not g:
            console.print("[yellow]Etapa 1 sem dados para este modelo.[/yellow]")
            return

        t = Table(title=f"Etapa 1 — Text2SQL · {self.model}")
        t.add_column("Métrica")
        t.add_column("Valor", justify="right")
        t.add_column("%", justify="right")
        n = g["questoes"]
        for rotulo, chave in [
            ("Questões avaliadas", "questoes"),
            ("Executaram sem erro", "executaram"),
            ("Erros de execução", "erros"),
            ("Execution Accuracy", "execution_accuracy"),
            ("Exact Match", "exact_match"),
            ("Plano usa índice", "usam_indice"),
        ]:
            v = g[chave]
            t.add_row(rotulo, str(v), "—" if chave == "questoes" else f"{v / n * 100:.1f}")
        console.print(t)

        # por dificuldade
        por_dif: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for r in self.s1:
            d = por_dif[r["difficulty"]]
            d[0] += 1
            if r["execution_accuracy"]:
                d[1] += 1
            if r.get("error"):
                d[2] += 1
        t2 = Table(title="Etapa 1 — por dificuldade")
        t2.add_column("Dificuldade")
        t2.add_column("Questões", justify="right")
        t2.add_column("Acertos", justify="right")
        t2.add_column("EX %", justify="right")
        t2.add_column("Erros", justify="right")
        for dif in ("simple", "moderate", "challenging"):
            if dif not in por_dif:
                continue
            n_d, ok, er = por_dif[dif]
            t2.add_row(dif, str(n_d), str(ok), f"{ok / n_d * 100:.1f}", str(er))
        console.print(t2)

    # ---------- Etapas 2 e 3 lado a lado ----------

    def tabela_indices(self) -> None:
        if not self.s2:
            console.print("[yellow]Etapa 2 sem dados para este modelo.[/yellow]")
            return

        s3_por_banco = {r["db_id"]: r for r in self.s3}

        t = Table(
            title=f"Etapas 2 e 3 — efeito dos índices · {self.model}",
            caption="Etapa 2 mede sobre as queries gabarito; Etapa 3, sobre as queries geradas.",
        )
        t.add_column("Banco")
        t.add_column("Índices", justify="right")
        t.add_column("E2 queries", justify="right")
        t.add_column("E2 melhor.", justify="right")
        t.add_column("E2 speedup", justify="right")
        t.add_column("E3 queries", justify="right")
        t.add_column("E3 melhor.", justify="right")
        t.add_column("E3 speedup", justify="right")

        for r in sorted(self.s2, key=lambda x: x["db_id"]):
            b = r["db_id"]
            s3 = s3_por_banco.get(b)
            # Etapa 2 nao guarda mediana; calcula a partir das queries.
            razoes2 = [
                q["before"]["latency_ms"] / q["after"]["latency_ms"]
                for q in r.get("query_results", [])
                if q["after"]["latency_ms"] > 0
            ]
            med2 = statistics.median(razoes2) if razoes2 else 0.0
            linha = [
                b,
                str(r["indexes_applied"]),
                str(r["total_queries"]),
                str(r["queries_improved"]),
                f"{med2:.2f}x",
            ]
            if s3:
                linha += [
                    str(s3["queries_measured"]),
                    str(s3["queries_improved"]),
                    f"{s3['median_speedup']:.2f}x",
                ]
            else:
                linha += ["—", "—", "—"]
            t.add_row(*linha)
        console.print(t)

    def tabela_estatisticas(self) -> None:
        """Distribuicao dos speedups: o que deve ser reportado no TCC."""
        t = Table(title="Distribuição do speedup — o que reportar")
        t.add_column("Etapa")
        t.add_column("Carga medida")
        t.add_column("n", justify="right")
        t.add_column("p25", justify="right")
        t.add_column("Mediana", justify="right")
        t.add_column("p75", justify="right")
        t.add_column("Razão das médias", justify="right")

        for rotulo, dados, carga in [
            ("Etapa 2", self.s2, "queries gabarito"),
            ("Etapa 3", self.s3, "queries geradas"),
        ]:
            razoes: list[float] = []
            antes = depois = 0.0
            for r in dados:
                for q in r.get("query_results", []):
                    b, a = q["before"]["latency_ms"], q["after"]["latency_ms"]
                    antes += b
                    depois += a
                    if a > 0:
                        razoes.append(b / a)
            if not razoes:
                t.add_row(rotulo, carga, "—", "—", "—", "—", "—")
                continue
            p25, med, p75 = _quartis(razoes)
            rm = antes / depois if depois > 0 else 0.0
            t.add_row(
                rotulo, carga, str(len(razoes)),
                f"{p25:.2f}x", f"{med:.2f}x", f"{p75:.2f}x", f"{rm:.2f}x",
            )
        console.print(t)
        console.print(
            "[dim]Reporte a mediana como ganho típico. A razão das médias "
            "descreve o tempo total da carga e é dominada por outliers.[/dim]"
        )

    def tabela_certas_vs_erradas(self) -> None:
        """O ganho difere entre queries corretas e incorretas?"""
        if not self.s3:
            return
        grupos: dict[bool, list[float]] = {True: [], False: []}
        for r in self.s3:
            for q in r.get("query_results", []):
                a = q["after"]["latency_ms"]
                if a > 0:
                    grupos[bool(q["execution_accuracy"])].append(
                        q["before"]["latency_ms"] / a
                    )
        t = Table(title="Etapa 3 — ganho em queries corretas vs incorretas")
        t.add_column("Grupo")
        t.add_column("n", justify="right")
        t.add_column("Mediana", justify="right")
        for correta, rotulo in [(True, "Corretas (EX=True)"), (False, "Incorretas (EX=False)")]:
            v = grupos[correta]
            t.add_row(rotulo, str(len(v)), f"{statistics.median(v):.2f}x" if v else "—")
        console.print(t)

    # ---------- CSV ----------

    def exportar_csv(self, destino: Path) -> list[Path]:
        destino = Path(destino)
        destino.mkdir(parents=True, exist_ok=True)
        gerados: list[Path] = []

        if self.s1:
            p = destino / f"etapa1_{self.model.replace('/', '_')}.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "instance_id", "db_id", "difficulty", "sgbd",
                    "execution_accuracy", "exact_match", "latency_ms",
                    "uses_index", "scan_type", "error",
                ])
                for r in self.s1:
                    ep = r.get("explain_parsed") or {}
                    w.writerow([
                        r["instance_id"], r["db_id"], r["difficulty"], r["sgbd"],
                        r["execution_accuracy"], r["exact_match"],
                        f"{r['latency_ms']:.4f}",
                        ep.get("uses_index", ""), ep.get("scan_type", ""),
                        r.get("error") or "",
                    ])
            gerados.append(p)

        for rotulo, dados in [("etapa2", self.s2), ("etapa3", self.s3)]:
            if not dados:
                continue
            p = destino / f"{rotulo}_{self.model.replace('/', '_')}.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "db_id", "instance_id", "difficulty",
                    "latency_before_ms", "latency_after_ms", "speedup",
                    "uses_index_before", "uses_index_after",
                    "improved", "new_index_used", "execution_accuracy",
                ])
                for r in dados:
                    for q in r.get("query_results", []):
                        b, a = q["before"]["latency_ms"], q["after"]["latency_ms"]
                        w.writerow([
                            r["db_id"], q["instance_id"], q["difficulty"],
                            f"{b:.4f}", f"{a:.4f}",
                            f"{b / a:.4f}" if a > 0 else "",
                            q["before"]["uses_index"], q["after"]["uses_index"],
                            q["improved"], q["new_index_used"],
                            q.get("execution_accuracy", ""),
                        ])
            gerados.append(p)

        return gerados

    def imprimir(self) -> None:
        console.print()
        self.tabela_etapa1()
        console.print()
        self.tabela_indices()
        console.print()
        self.tabela_estatisticas()
        console.print()
        self.tabela_certas_vs_erradas()
