"""Comparacao entre modelos — a pergunta central do trabalho.

O `ConsolidatedReport` descreve um modelo por vez. Este junta varios e pareia
as questoes, para que as taxas sejam comparaveis: cada modelo e medido sobre
exatamente o mesmo conjunto.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Falhas que NAO sao resultado do modelo: a API caiu ou o benchmark quebrou.
# Um par em que qualquer um dos lados tem isso sai da comparacao — contar como
# erro atribuiria ao modelo um problema que nao e dele.
_NAO_E_RESULTADO = {"llm_error", "system_error"}


@dataclass
class Celula:
    modelo: str
    sgbd: str
    acertos: dict[int, bool]      # instance_id -> acertou
    invalidas: set[int]
    erros: int

    @property
    def ex(self) -> float:
        return 100 * sum(self.acertos.values()) / len(self.acertos) if self.acertos else 0.0


def _carregar(caminho: Path) -> Celula:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not dados:
        raise ValueError(f"Arquivo sem registros: {caminho}")
    acertos, invalidas = {}, set()
    for r in dados:
        iid = r["instance_id"]
        if r.get("error_type") in _NAO_E_RESULTADO:
            invalidas.add(iid)
            continue
        acertos[iid] = bool(r["execution_accuracy"])
    return Celula(
        modelo=dados[0]["model"],
        sgbd=dados[0].get("sgbd") or "?",
        acertos=acertos,
        invalidas=invalidas,
        erros=sum(1 for r in dados if r.get("error")),
    )


class ComparativeReport:
    def __init__(self, celulas: list[Celula]) -> None:
        self._celulas = celulas
        self._por_sgbd: dict[str, list[Celula]] = defaultdict(list)
        for c in celulas:
            self._por_sgbd[c.sgbd].append(c)

    @classmethod
    def from_files(cls, arquivos: list[Path]) -> ComparativeReport:
        return cls([_carregar(Path(a)) for a in arquivos])

    @property
    def modelos(self) -> list[str]:
        vistos: list[str] = []
        for c in self._celulas:
            if c.modelo not in vistos:
                vistos.append(c.modelo)
        return vistos

    def _pares(self, a: Celula, b: Celula) -> tuple[list[bool], list[bool], int]:
        """Alinha duas celulas pelas questoes que ambas mediram validamente."""
        comuns = sorted(set(a.acertos) & set(b.acertos))
        descartadas = len((set(a.acertos) | set(b.acertos)) - set(comuns))
        return [a.acertos[i] for i in comuns], [b.acertos[i] for i in comuns], descartadas

    # ---------------------------------------------------------------- tabelas

    def tabela_acuracia(self, console: Console) -> None:
        sgbds = sorted(self._por_sgbd)
        t = Table(title="Execution Accuracy — modelo × SGBD")
        t.add_column("Modelo")
        for s in sgbds:
            t.add_column(s, justify="right")
        t.add_column("média", justify="right", style="bold")
        for modelo in self.modelos:
            linha, valores = [modelo], []
            for s in sgbds:
                c = next((x for x in self._por_sgbd[s] if x.modelo == modelo), None)
                if c:
                    valores.append(c.ex)
                    linha.append(f"{c.ex:.1f}%")
                else:
                    linha.append("—")
            linha.append(f"{sum(valores) / len(valores):.1f}%" if valores else "—")
            t.add_row(*linha)
        console.print(t)

    def tabela_divergencias(self, console: Console) -> None:
        """Onde os modelos discordam, par a par.

        As questoes que ambos acertaram ou ambos erraram nao distinguem os
        modelos; as discordantes sao o material da comparacao e mostram o
        tamanho real da vantagem de um sobre o outro.
        """
        for sgbd in sorted(self._por_sgbd):
            celulas = self._por_sgbd[sgbd]
            if len(celulas) < 2:
                continue
            t = Table(
                title=f"Onde os modelos discordam — {sgbd}",
                caption="Só as questões em que um acertou e o outro errou "
                        "distinguem os dois.",
            )
            for col in ("Comparação", "n", "ambos ✓", "só o 1º", "só o 2º", "ambos ✗"):
                t.add_column(col, justify="right" if col != "Comparação" else "left")
            for a, b in combinations(celulas, 2):
                xa, xb, _ = self._pares(a, b)
                ambos_c = sum(1 for x, y in zip(xa, xb) if x and y)
                so_a = sum(1 for x, y in zip(xa, xb) if x and not y)
                so_b = sum(1 for x, y in zip(xa, xb) if y and not x)
                ambos_e = sum(1 for x, y in zip(xa, xb) if not x and not y)
                t.add_row(
                    f"{a.modelo.split('/')[-1]} vs {b.modelo.split('/')[-1]}",
                    str(len(xa)), str(ambos_c), str(so_a), str(so_b), str(ambos_e),
                )
            console.print(t)

    def imprimir(self) -> None:
        console = Console()
        console.rule("[bold]Comparação entre modelos")
        self.tabela_acuracia(console)
        console.print()
        self.tabela_divergencias(console)
        descartes = sum(len(c.invalidas) for c in self._celulas)
        if descartes:
            console.print(
                f"\n[yellow]{descartes} medições descartadas[/yellow] por "
                f"llm_error ou system_error — não são resultado do modelo."
            )

    # -------------------------------------------------------------------- csv

    def exportar_csv(self, destino: Path) -> list[Path]:
        destino = Path(destino)
        destino.mkdir(parents=True, exist_ok=True)
        gerados = []

        p = destino / "acuracia_por_modelo.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["modelo", "sgbd", "questoes", "acertos", "ex_pct", "erros", "descartadas"])
            for c in self._celulas:
                w.writerow([c.modelo, c.sgbd, len(c.acertos), sum(c.acertos.values()),
                            f"{c.ex:.2f}", c.erros, len(c.invalidas)])
        gerados.append(p)

        p = destino / "divergencias.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["sgbd", "modelo_a", "modelo_b", "n_pares",
                        "ambos_certos", "so_a", "so_b", "ambos_errados"])
            for sgbd in sorted(self._por_sgbd):
                for a, b in combinations(self._por_sgbd[sgbd], 2):
                    xa, xb, _ = self._pares(a, b)
                    w.writerow([
                        sgbd, a.modelo, b.modelo, len(xa),
                        sum(1 for x, y in zip(xa, xb) if x and y),
                        sum(1 for x, y in zip(xa, xb) if x and not y),
                        sum(1 for x, y in zip(xa, xb) if y and not x),
                        sum(1 for x, y in zip(xa, xb) if not x and not y),
                    ])
        gerados.append(p)
        return gerados
