"""Comparacao entre modelos — a pergunta central do trabalho.

O `ConsolidatedReport` descreve um modelo por vez. Este junta varios e pareia
as questoes, para que as taxas sejam comparaveis: cada modelo e medido sobre
exatamente o mesmo conjunto.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from statistics import median

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


@dataclass
class CelulaIndices:
    """Etapas 2 e 3 de um modelo num SGBD."""

    modelo: str
    sgbd: str
    aplicados: int
    falharam: int
    speedups_gabarito: list[float] = field(default_factory=list)   # Etapa 2
    speedups_gerado: list[float] = field(default_factory=list)     # Etapa 3
    sp_corretas: list[float] = field(default_factory=list)
    sp_incorretas: list[float] = field(default_factory=list)
    melhoraram: int = 0
    usaram_indice_novo: int = 0
    medidas: int = 0

    def _med(self, valores: list[float]) -> float:
        # Mediana, nao media: a distribuicao tem cauda longa (uma query saiu de
        # 408 s para 2,1 ms) e a media seria dominada por outliers.
        return median(valores) if valores else 0.0

    @property
    def med_gabarito(self) -> float:
        return self._med(self.speedups_gabarito)

    @property
    def med_gerado(self) -> float:
        return self._med(self.speedups_gerado)

    @property
    def med_corretas(self) -> float:
        return self._med(self.sp_corretas)

    @property
    def med_incorretas(self) -> float:
        return self._med(self.sp_incorretas)

    @property
    def pct_melhoraram(self) -> float:
        return 100 * self.melhoraram / self.medidas if self.medidas else 0.0

    @property
    def pct_indice_novo(self) -> float:
        return 100 * self.usaram_indice_novo / self.medidas if self.medidas else 0.0

    @property
    def pct_falha_indice(self) -> float:
        total = self.aplicados + self.falharam
        return 100 * self.falharam / total if total else 0.0


def _speedup(q: dict) -> float | None:
    """Razao entre a latencia antes e depois dos indices."""
    antes = (q.get("before") or {}).get("latency_ms")
    depois = (q.get("after") or {}).get("latency_ms")
    return antes / depois if antes and depois else None


def _carregar_indices(caminho_e2: Path, caminho_e3: Path | None) -> CelulaIndices:
    d2 = json.loads(Path(caminho_e2).read_text(encoding="utf-8"))
    if not d2:
        raise ValueError(f"Arquivo sem registros: {caminho_e2}")
    validos = [r for r in d2 if not r.get("error")]
    celula = CelulaIndices(
        modelo=d2[0]["model"],
        sgbd=d2[0].get("dialect") or "?",
        aplicados=sum(r.get("indexes_applied", 0) for r in validos),
        falharam=sum(r.get("indexes_failed", 0) for r in validos),
        speedups_gabarito=[
            v for r in validos for q in (r.get("query_results") or [])
            if (v := _speedup(q))
        ],
    )
    if caminho_e3 is None:
        return celula

    d3 = [r for r in json.loads(Path(caminho_e3).read_text(encoding="utf-8"))
          if not r.get("error")]
    qs = [q for r in d3 for q in (r.get("query_results") or [])]
    celula.speedups_gerado = [v for q in qs if (v := _speedup(q))]
    celula.sp_corretas = [v for q in qs if q.get("execution_accuracy") and (v := _speedup(q))]
    celula.sp_incorretas = [
        v for q in qs if not q.get("execution_accuracy") and (v := _speedup(q))
    ]
    celula.melhoraram = sum(1 for q in qs if q.get("improved"))
    # So os indices CRIADOS. O `uses_index` da Etapa 1 nao serve para comparar
    # SGBDs: cada parser conta indice preexistente de forma diferente, e o
    # InnoDB sempre tem a chave primaria agrupada, o que inflaria o MariaDB.
    celula.usaram_indice_novo = sum(1 for q in qs if q.get("new_index_used"))
    celula.medidas = len(qs)
    return celula


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
    def __init__(
        self, celulas: list[Celula], indices: list[CelulaIndices] | None = None
    ) -> None:
        self._celulas = celulas
        self._indices = indices or []
        self._por_sgbd: dict[str, list[Celula]] = defaultdict(list)
        for c in celulas:
            self._por_sgbd[c.sgbd].append(c)
        self._idx_por_sgbd: dict[str, list[CelulaIndices]] = defaultdict(list)
        for c in self._indices:
            self._idx_por_sgbd[c.sgbd].append(c)

    @classmethod
    def from_files(
        cls,
        arquivos: list[Path],
        stage2: list[Path] | None = None,
        stage3: list[Path] | None = None,
    ) -> ComparativeReport:
        """Monta o relatorio a partir dos JSONs das etapas.

        `stage3` e opcional e pareado com `stage2` por posicao: sem ele saem
        so os numeros da Etapa 2, medidos sobre as queries gabarito.
        """
        celulas = [_carregar(Path(a)) for a in arquivos]
        indices: list[CelulaIndices] = []
        for i, e2 in enumerate(stage2 or []):
            e3 = Path(stage3[i]) if stage3 and i < len(stage3) else None
            indices.append(_carregar_indices(Path(e2), e3))
        return cls(celulas, indices)

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

    def tabela_indices(self, console: Console) -> None:
        """Etapas 2 e 3 lado a lado, por modelo e SGBD."""
        if not self._indices:
            return
        t = Table(
            title="Etapas 2 e 3 — efeito dos índices",
            caption="E2 mede sobre as queries gabarito; E3, sobre as geradas. "
                    "Mediana: a distribuição tem cauda longa.",
        )
        t.add_column("Modelo")
        t.add_column("SGBD")
        t.add_column("Índices", justify="right")
        t.add_column("Falhas", justify="right")
        t.add_column("E2", justify="right")
        t.add_column("E3", justify="right")
        t.add_column("Melhoraram", justify="right")
        t.add_column("Usa índice novo", justify="right")
        for c in self._indices:
            falhas = f"{c.falharam}" if not c.falharam else f"[yellow]{c.falharam}[/yellow]"
            t.add_row(
                c.modelo.split("/")[-1], c.sgbd, str(c.aplicados), falhas,
                f"{c.med_gabarito:.2f}×", f"{c.med_gerado:.2f}×",
                f"{c.pct_melhoraram:.0f} %", f"{c.pct_indice_novo:.0f} %",
            )
        console.print(t)

    def tabela_corretas_incorretas(self, console: Console) -> None:
        """Verifica se as queries incorretas ganham mais que as corretas.

        Observado na rodada isolada do primeiro modelo. Esta tabela existe
        para mostrar em quantas celulas isso de fato se repete.
        """
        if not self._indices:
            return
        t = Table(
            title="Etapa 3 — ganho em queries corretas vs incorretas",
            caption="A coluna final diz qual grupo ganhou mais em cada célula.",
        )
        for col in ("Modelo", "SGBD", "Corretas", "Incorretas", "Ganhou"):
            t.add_column(col, justify="right" if col not in ("Modelo", "SGBD") else "left")
        favor_incorretas = 0
        for c in self._indices:
            incorretas_ganham = c.med_incorretas > c.med_corretas
            favor_incorretas += incorretas_ganham
            t.add_row(
                c.modelo.split("/")[-1], c.sgbd,
                f"{c.med_corretas:.2f}×", f"{c.med_incorretas:.2f}×",
                "[yellow]incorretas[/yellow]" if incorretas_ganham else "corretas",
            )
        console.print(t)
        n = len(self._indices)
        console.print(
            f"[dim]As incorretas ganham mais em {favor_incorretas} de {n} células.[/dim]"
        )

    def imprimir(self) -> None:
        console = Console()
        console.rule("[bold]Comparação entre modelos")
        self.tabela_acuracia(console)
        console.print()
        self.tabela_divergencias(console)
        if self._indices:
            console.print()
            self.tabela_indices(console)
            console.print()
            self.tabela_corretas_incorretas(console)
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

        if self._indices:
            p = destino / "indices_por_modelo.csv"
            with p.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["modelo", "sgbd", "indices_aplicados", "indices_falharam",
                            "pct_falha", "speedup_mediano_gabarito", "speedup_mediano_gerado",
                            "speedup_mediano_corretas", "speedup_mediano_incorretas",
                            "queries_medidas", "pct_melhoraram", "pct_usa_indice_novo"])
                for c in self._indices:
                    w.writerow([
                        c.modelo, c.sgbd, c.aplicados, c.falharam,
                        f"{c.pct_falha_indice:.2f}",
                        f"{c.med_gabarito:.4f}", f"{c.med_gerado:.4f}",
                        f"{c.med_corretas:.4f}", f"{c.med_incorretas:.4f}",
                        c.medidas, f"{c.pct_melhoraram:.2f}", f"{c.pct_indice_novo:.2f}",
                    ])
            gerados.append(p)
        return gerados
