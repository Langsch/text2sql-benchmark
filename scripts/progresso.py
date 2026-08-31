#!/usr/bin/env python3
"""Mostra o progresso das rodadas do benchmark e o gasto acumulado.

Uso:
    .venv/bin/python scripts/progresso.py          # uma leitura
    .venv/bin/python scripts/progresso.py -w       # atualiza a cada 15s
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUNS = RAIZ / "results" / "runs"

# Sonnet 5, USD por token.
PRECO_IN, PRECO_OUT = 2.00 / 1e6, 10.00 / 1e6
# Input medio por questao da Etapa 1, medido com a contagem de tokens da API.
IN_POR_QUESTAO, OUT_POR_QUESTAO = 853_810 / 500, 84

CREDITO_INICIAL = 5.00


def _processo_ativo() -> str | None:
    try:
        saida = subprocess.run(
            ["ps", "-eo", "args"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return None
    for linha in saida.splitlines():
        if "cli.py" in linha and "grep" not in linha:
            for etapa, marca in (
                ("pipeline completo", "cli.py pipeline"),
                ("Etapa 1 (text2sql)", "cli.py run"),
                ("Etapa 2 (índices)", "cli.py index"),
                ("Etapa 3 (revalidação)", "cli.py revalidate"),
            ):
                if marca in linha:
                    return etapa
    return None


def _mais_recente(padrao: str) -> Path | None:
    achados = sorted(glob.glob(str(RUNS / padrao)), key=os.path.getmtime)
    return Path(achados[-1]) if achados else None


def _carregar(p: Path | None) -> list[dict]:
    if not p or not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []  # gravacao em andamento


def relatorio() -> None:
    ativo = _processo_ativo()
    print(f"\n  {'▶ ' + ativo if ativo else '■ nada rodando'}")
    print("  " + "─" * 58)

    gasto = 0.0

    # --- Etapa 1 ---
    p1 = _mais_recente("*_all.json")
    d1 = _carregar(p1)
    if d1:
        n = len(d1)
        ok = sum(1 for r in d1 if r["execution_accuracy"])
        em = sum(1 for r in d1 if r["exact_match"])
        tipos = collections.Counter(
            r.get("error_type") or "sem_tipo" for r in d1 if r.get("error")
        )
        barra = "█" * int(n / 500 * 28) + "░" * (28 - int(n / 500 * 28))
        print(f"  Etapa 1  {barra} {n}/500")
        print(f"           EX {ok / n * 100:.1f}%   EM {em / n * 100:.1f}%", end="")
        print(f"   erros: {dict(tipos) if tipos else 0}")
        print(f"           {p1.name}")
        gasto += n * IN_POR_QUESTAO * PRECO_IN + n * OUT_POR_QUESTAO * PRECO_OUT

    # --- Etapa 2 ---
    p2 = _mais_recente("index_runs/*_index_all.json")
    d2 = _carregar(p2)
    if d2:
        idx = sum(r.get("indexes_applied", 0) for r in d2)
        print(f"\n  Etapa 2  {len(d2)}/11 bancos   {idx} índices aplicados")
        print(f"           {p2.name}")
        gasto += sum(
            r.get("index_prompt_tokens", 0) * PRECO_IN
            + r.get("index_output_tokens", 0) * PRECO_OUT
            for r in d2
        )

    # --- Etapa 3 ---
    p3 = _mais_recente("revalidation_runs/*_revalidation_*.json")
    d3 = _carregar(p3)
    if d3:
        medidas = sum(r.get("queries_measured", 0) for r in d3)
        melhor = sum(r.get("queries_improved", 0) for r in d3)
        print(f"\n  Etapa 3  {len(d3)} bancos   {medidas} queries medidas", end="")
        print(f"   {melhor} melhoraram")
        print(f"           {p3.name}")
    else:
        print("\n  Etapa 3  não executada")

    print("  " + "─" * 58)
    print(f"  gasto ~${gasto:.2f}   crédito ~${CREDITO_INICIAL - gasto:.2f}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-w", "--watch", action="store_true", help="atualiza a cada 15s")
    args = ap.parse_args()

    if not args.watch:
        relatorio()
        return 0

    try:
        while True:
            print("\033[2J\033[H", end="")  # limpa a tela
            relatorio()
            time.sleep(15)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
