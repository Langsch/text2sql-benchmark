"""Recalcula, a partir dos JSONs brutos, todos os números citados no artigo.

Uso, na raiz do repositório:

    .venv/bin/python analise/reproduzir.py

Lê `analise/manifesto.json`, confere o SHA-256 de cada arquivo listado e
gera `analise/saida/numeros_do_artigo.md` (o relatório de conferência) e os
CSVs em `analise/saida/csv/`.

Cada afirmação numérica do artigo aparece no relatório com três colunas: o
que o artigo diz, o que os dados dão e se coincidem. O script termina com
código 1 se algum número divergir ou algum arquivo tiver sido alterado.

Nenhuma chamada a API e nenhum banco de dados são necessários: tudo sai dos
arquivos de resultado.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from statistics import median

import sqlglot
from sqlglot import exp

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.text2sql_benchmark.report.comparative_report import (  # noqa: E402
    _carregar_indices,
)

MANIFESTO = RAIZ / "analise" / "manifesto.json"
SAIDA = RAIZ / "analise" / "saida"

NOME = {
    "claude-sonnet-5": "Claude Sonnet 5",
    "google/gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "qwen/qwen3.8-27b": "Qwen 3.8 27B",
    "openai/gpt-5.6-luna": "GPT-5.6 Luna",
    "deepseek/deepseek-v4-flash-0731": "DeepSeek V4 Flash",
}
SGBDS = ["sqlite", "postgresql", "mariadb"]
ROTULO = {"sqlite": "SQLite", "postgresql": "PostgreSQL", "mariadb": "MariaDB"}
DIFS = ["simple", "moderate", "challenging"]


# --------------------------------------------------------------- utilidades

def pct(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",") + "%"


def num(x: float, casas: int = 2) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@dataclass
class Afirmacao:
    secao: str
    descricao: str
    artigo: str
    dados: str

    @property
    def ok(self) -> bool:
        return self.artigo == self.dados


class Relatorio:
    def __init__(self) -> None:
        self.linhas: list[str] = []
        self.afirmacoes: list[Afirmacao] = []

    def h(self, nivel: int, titulo: str) -> None:
        self.linhas += ["", "#" * nivel + " " + titulo, ""]

    def p(self, texto: str = "") -> None:
        self.linhas.append(texto)

    def tabela(self, cab: list[str], linhas: list[list[str]]) -> None:
        self.linhas.append("| " + " | ".join(cab) + " |")
        self.linhas.append("|" + "|".join("---" for _ in cab) + "|")
        for lin in linhas:
            self.linhas.append("| " + " | ".join(lin) + " |")
        self.linhas.append("")

    def confere(self, secao: str, descricao: str, artigo: str, dados: str) -> None:
        self.afirmacoes.append(Afirmacao(secao, descricao, artigo, dados))

    def bloco_afirmacoes(self, secao: str) -> None:
        sel = [a for a in self.afirmacoes if a.secao == secao]
        if not sel:
            return
        self.tabela(
            ["Afirmação do artigo", "Artigo", "Dados", ""],
            [[a.descricao, a.artigo, a.dados, "✓" if a.ok else "**✗**"] for a in sel],
        )


# ---------------------------------------------------------------- carregamento

def carregar_manifesto(rel: Relatorio) -> tuple[list[dict], list[dict], bool]:
    man = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    integro = True
    linhas = []
    arquivos = [(c["modelo"], c["sgbd"], et, c[et]) for c in man["celulas"]
                for et in ("etapa1", "etapa2", "etapa3")]
    arquivos += [("anthropic/claude-sonnet-5 (rota)", "sqlite", "etapa1", a)
                 for a in man["subteste_rota"]["arquivos"]]
    for modelo, sgbd, etapa, ref in arquivos:
        caminho = RAIZ / ref["arquivo"]
        if not caminho.exists():
            linhas.append([modelo, sgbd, etapa, ref["arquivo"], "**ausente**"])
            integro = False
            continue
        bate = sha256(caminho) == ref["sha256"]
        integro &= bate
        linhas.append([NOME.get(modelo, modelo), ROTULO[sgbd], etapa,
                       f"`{ref['arquivo']}`", "✓" if bate else "**hash diverge**"])
    rel.h(2, "1. Integridade dos arquivos")
    rel.p("Cada arquivo do manifesto tem o SHA-256 conferido. Um ✓ garante que o "
          "arquivo é byte a byte o mesmo que gerou os números abaixo.")
    rel.p()
    rel.tabela(["Modelo", "SGBD", "Etapa", "Arquivo", "SHA-256"], linhas)

    celulas = []
    for c in man["celulas"]:
        celulas.append({
            "modelo": c["modelo"], "sgbd": c["sgbd"],
            "e1": json.loads((RAIZ / c["etapa1"]["arquivo"]).read_text(encoding="utf-8")),
            "e2": json.loads((RAIZ / c["etapa2"]["arquivo"]).read_text(encoding="utf-8")),
            "e3": json.loads((RAIZ / c["etapa3"]["arquivo"]).read_text(encoding="utf-8")),
            "idx": _carregar_indices(RAIZ / c["etapa2"]["arquivo"], RAIZ / c["etapa3"]["arquivo"]),
        })
    rota = []
    for a in man["subteste_rota"]["arquivos"]:
        rota += json.loads((RAIZ / a["arquivo"]).read_text(encoding="utf-8"))
    return celulas, rota, integro


def cel(celulas, modelo, sgbd):
    return next(c for c in celulas if c["modelo"] == modelo and c["sgbd"] == sgbd)


# ------------------------------------------------------------------- seções

def secao_condicoes(rel, celulas):
    rel.h(2, "2. Condições de execução")
    total_e1 = sum(len(c["e1"]) for c in celulas)
    rel.confere("2", "Questões medidas nas quinze combinações", "7.500",
                f"{total_e1:,}".replace(",", "."))
    for c in celulas:
        assert len(c["e1"]) == 500, (c["modelo"], c["sgbd"], len(c["e1"]))

    # Pinagem: provedor gravado por chamada, nos quatro modelos via OpenRouter.
    via_or = [c for c in celulas if c["modelo"] != "claude-sonnet-5"]
    pin_e1 = Counter()
    for c in via_or:
        for r in c["e1"]:
            pin_e1[(c["modelo"], r.get("provider"))] += 1
    pin_e2 = Counter((c["modelo"], r.get("provider")) for c in via_or for r in c["e2"])
    n_e1 = sum(pin_e1.values())
    n_e2 = sum(pin_e2.values())
    provedores = defaultdict(set)
    for (m, p) in list(pin_e1) + list(pin_e2):
        provedores[m].add(p)
    unico = all(len(v) == 1 for v in provedores.values())
    n_tot = n_e1 + n_e2
    rel.confere("2", "Chamadas atendidas pelo provedor fixado (Etapas 1 e 2)",
                "6.132 de 6.132", f"{n_tot:,} de {n_tot:,}".replace(",", ".") if unico else "não")
    rel.p(f"Provedor por modelo, em todas as chamadas das Etapas 1 e 2 "
          f"({n_e1} + {n_e2} = {n_e1 + n_e2} chamadas):")
    rel.p()
    rel.tabela(["Modelo", "Provedor gravado", "Chamadas E1", "Chamadas E2"],
               [[NOME[m], ", ".join(sorted(provedores[m])),
                 str(sum(v for (mm, _), v in pin_e1.items() if mm == m)),
                 str(sum(v for (mm, _), v in pin_e2.items() if mm == m))]
                for m in provedores])
    rel.bloco_afirmacoes("2")


def secao_acuracia(rel, celulas):
    rel.h(2, "3. Etapa 1 — acurácia de execução")
    ex = {(c["modelo"], c["sgbd"]): 100 * sum(bool(r["execution_accuracy"]) for r in c["e1"]) / 500
          for c in celulas}
    linhas = []
    esperado = {
        "claude-sonnet-5": ("67,0%", "58,6%", "58,0%", "61,2%"),
        "google/gemini-3.1-flash-lite": ("61,2%", "55,4%", "52,6%", "56,4%"),
        "qwen/qwen3.8-27b": ("53,4%", "47,4%", "46,6%", "49,1%"),
        "openai/gpt-5.6-luna": ("53,8%", "46,4%", "46,0%", "48,7%"),
        "deepseek/deepseek-v4-flash-0731": ("52,4%", "43,8%", "44,4%", "46,9%"),
    }
    for m in NOME:
        vals = [ex[(m, s)] for s in SGBDS]
        media = sum(vals) / 3
        linhas.append([NOME[m]] + [pct(v) for v in vals] + [pct(media)])
        for s, v, e in zip(SGBDS + ["média"], vals + [media], esperado[m]):
            rel.confere("3", f"EX {NOME[m]} — {ROTULO.get(s, s)}", e, pct(v))
    rel.tabela(["Modelo", "SQLite", "PostgreSQL", "MariaDB", "Média"], linhas)

    vant = {m: ex[(m, "sqlite")] - (ex[(m, "postgresql")] + ex[(m, "mariadb")]) / 2 for m in NOME}
    rel.confere("3", "SQLite supera a média dos servidores em todos os modelos",
                "5 de 5", f"{sum(v > 0 for v in vant.values())} de 5")
    rel.confere("3", "Menor vantagem do SQLite (Qwen)", "6,4",
                num(vant["qwen/qwen3.8-27b"], 1))
    rel.confere("3", "Maior vantagem do SQLite (Sonnet)", "8,7",
                num(vant["claude-sonnet-5"], 1))
    rel.confere("3", "Faixa da vantagem do SQLite", "6,4 a 8,7",
                f"{num(min(vant.values()), 1)} a {num(max(vant.values()), 1)}")
    dif = {m: abs(ex[(m, "postgresql")] - ex[(m, "mariadb")]) for m in NOME}
    rel.confere("3", "Maior diferença PostgreSQL × MariaDB (Gemini)", "2,8",
                num(max(dif.values()), 1))
    outros = [v for m, v in dif.items() if m != "google/gemini-3.1-flash-lite"]
    rel.confere("3", "Demais modelos: diferença PostgreSQL × MariaDB abaixo de 1,6",
                "sim", "sim" if max(outros) < 1.6 else f"não ({num(max(outros), 1)})")

    # Dificuldade
    mono = 0
    linhas = []
    for c in celulas:
        taxas = []
        for d in DIFS:
            rs = [r for r in c["e1"] if r["difficulty"] == d]
            taxas.append(100 * sum(bool(r["execution_accuracy"]) for r in rs) / len(rs))
        mono += taxas[0] > taxas[1] > taxas[2]
        linhas.append([NOME[c["modelo"]], ROTULO[c["sgbd"]]] + [pct(t) for t in taxas])
    rel.p("Por dificuldade:")
    rel.p()
    rel.tabela(["Modelo", "SGBD", "simple", "moderate", "challenging"], linhas)
    rel.confere("3", "Degradação monotônica por dificuldade", "15 de 15", f"{mono} de 15")

    # Erros
    tipos = Counter(r.get("error_type") for c in celulas for r in c["e1"] if r.get("error"))
    rel.confere("3", "Consultas rejeitadas por SQL inválido", "392", str(tipos["sql_error"]))
    rel.confere("3", "Consultas interrompidas pelo limite de 30 s", "13", str(tipos["timeout"]))
    rel.confere("3", "Falhas de API ou do benchmark (llm_error, system_error)", "0",
                str(tipos["llm_error"] + tipos["system_error"]))
    rel.bloco_afirmacoes("3")
    return ex


def secao_aplicabilidade(rel, celulas):
    rel.h(2, "4. Etapa 2 — aplicabilidade dos índices")
    linhas = []
    esperado_total = {
        "claude-sonnet-5": "98,6%", "google/gemini-3.1-flash-lite": "96,4%",
        "qwen/qwen3.8-27b": "93,9%", "openai/gpt-5.6-luna": "98,8%",
        "deepseek/deepseek-v4-flash-0731": "90,4%",
    }
    esperado_cel = {
        "claude-sonnet-5": ("306/306", "305/306", "296/308"),
        "google/gemini-3.1-flash-lite": ("234/235", "233/234", "182/204"),
        "qwen/qwen3.8-27b": ("365/366", "325/352", "240/272"),
        "openai/gpt-5.6-luna": ("332/334", "335/336", "323/332"),
        "deepseek/deepseek-v4-flash-0731": ("399/399", "430/435", "339/458"),
    }
    recomendados = {}
    taxas = []
    for m in NOME:
        ap = tot = 0
        lin = [NOME[m]]
        for s, e in zip(SGBDS, esperado_cel[m]):
            i = cel(celulas, m, s)["idx"]
            a, t = i.aplicados, i.aplicados + i.falharam
            ap += a
            tot += t
            lin.append(f"{a}/{t}")
            rel.confere("4", f"Aplicados/recomendados {NOME[m]} — {ROTULO[s]}", e, f"{a}/{t}")
        recomendados[m] = tot
        taxas.append(100 * ap / tot)
        lin.append(pct(100 * ap / tot))
        rel.confere("4", f"Taxa agregada {NOME[m]}", esperado_total[m], pct(100 * ap / tot))
        linhas.append(lin)
    rel.tabela(["Modelo", "SQLite", "PostgreSQL", "MariaDB", "Total"], linhas)
    rel.confere("4", "Faixa da taxa de aplicabilidade", "90,4% a 98,8%",
                f"{pct(min(taxas))} a {pct(max(taxas))}")
    rel.confere("4", "Menor número de índices recomendados (Gemini)", "673",
                str(recomendados["google/gemini-3.1-flash-lite"]))
    rel.confere("4", "Maior número de índices recomendados (DeepSeek)", "1.292",
                f"{recomendados['deepseek/deepseek-v4-flash-0731']:,}".replace(",", "."))

    ds = cel(celulas, "deepseek/deepseek-v4-flash-0731", "mariadb")
    falhas = [s for r in ds["e2"] if not r.get("error")
              for s in (r.get("indexes_suggested") or []) if not s.get("success")]
    chave = sum(1 for s in falhas if "key was too long" in (s.get("error") or ""))
    rel.confere("4", "DeepSeek × MariaDB: recomendações rejeitadas", "119", str(len(falhas)))
    rel.confere("4", "… das quais por limite de tamanho de chave", "82", str(chave))

    # Causa dominante no MariaDB em todos os modelos
    rel.p("Causas de rejeição no MariaDB, por modelo:")
    rel.p()
    lin = []
    for m in NOME:
        c = cel(celulas, m, "mariadb")
        erros = Counter()
        for r in c["e2"]:
            for s in (r.get("indexes_suggested") or []):
                if not s.get("success"):
                    msg = s.get("error") or ""
                    erros["chave longa demais (1071)" if "1071" in msg else
                          "TEXT/BLOB sem prefixo (1170)" if "1170" in msg else "outra"] += 1
        lin.append([NOME[m], str(sum(erros.values()))] +
                   [str(erros[k]) for k in ("chave longa demais (1071)",
                                            "TEXT/BLOB sem prefixo (1170)", "outra")])
    rel.tabela(["Modelo", "Rejeitados", "1071 chave longa", "1170 sem prefixo", "outra"], lin)
    rel.bloco_afirmacoes("4")


def secao_ganho(rel, celulas, ex):
    rel.h(2, "5. Etapas 2 e 3 — ganho de desempenho")
    esperado = {
        "claude-sonnet-5": ("3,52", "1,68", "1,65"),
        "google/gemini-3.1-flash-lite": ("2,58", "1,40", "1,22"),
        "qwen/qwen3.8-27b": ("3,15", "1,26", "1,24"),
        "openai/gpt-5.6-luna": ("4,16", "1,55", "1,43"),
        "deepseek/deepseek-v4-flash-0731": ("3,16", "1,62", "1,37"),
    }
    linhas = []
    for m in NOME:
        lin = [NOME[m]]
        for s, e in zip(SGBDS, esperado[m]):
            i = cel(celulas, m, s)["idx"]
            lin.append(f"{num(i.med_gabarito)}× / {num(i.med_gerado)}×")
            rel.confere("5", f"Mediana E3 {NOME[m]} — {ROTULO[s]}", e, num(i.med_gerado))
        linhas.append(lin)
    rel.p("Mediana do speedup, consultas de referência (E2) / consultas geradas (E3):")
    rel.p()
    rel.tabela(["Modelo", "SQLite", "PostgreSQL", "MariaDB"], linhas)

    sq = [cel(celulas, m, "sqlite")["idx"].med_gerado for m in NOME]
    sv = [cel(celulas, m, s)["idx"].med_gerado for m in NOME for s in ("postgresql", "mariadb")]
    rel.confere("5", "Faixa da mediana E3 em SQLite", "2,58 a 4,16",
                f"{num(min(sq))} a {num(max(sq))}")
    rel.confere("5", "Faixa da mediana E3 em PostgreSQL e MariaDB", "1,22 a 1,68",
                f"{num(min(sv))} a {num(max(sv))}")
    todas = [cel(celulas, m, s)["idx"].med_gerado for m in NOME for s in SGBDS]
    rel.confere("5", "Todas as medianas acima de 1 (todos reduzem o tempo)", "15 de 15",
                f"{sum(v > 1 for v in todas)} de 15")

    # Ordem por ganho × ordem por acurácia, no SQLite
    rank_ex = sorted(NOME, key=lambda m: -ex[(m, "sqlite")])
    maior_ganho = max(NOME, key=lambda m: cel(celulas, m, "sqlite")["idx"].med_gerado)
    rel.confere("5", "Posição em acurácia (SQLite) do modelo de maior ganho", "3ª",
                f"{rank_ex.index(maior_ganho) + 1}ª")
    seg = rank_ex[1]
    menor_sq = min(NOME, key=lambda m: cel(celulas, m, "sqlite")["idx"].med_gerado)
    rel.confere("5", "O 2º em acurácia tem o menor ganho em SQLite", "sim",
                "sim" if seg == menor_sq else "não")

    # Uso de índice novo (transição sem índice → com índice)
    faixas = {}
    for s in SGBDS:
        v = [cel(celulas, m, s)["idx"].pct_indice_novo for m in NOME]
        faixas[s] = f"{min(v):.0f}% a {max(v):.0f}%"
    rel.confere("5", "Planos que passam a usar índice — SQLite", "52% a 60%", faixas["sqlite"])
    rel.confere("5", "Planos que passam a usar índice — PostgreSQL", "29% a 38%", faixas["postgresql"])
    rel.confere("5", "Planos que passam a usar índice — MariaDB", "9% a 13%", faixas["mariadb"])

    # Carga gerada × carga de referência
    for s, e in zip(SGBDS, ("5 de 5", "3 de 5", "1 de 5")):
        n = sum(cel(celulas, m, s)["idx"].med_gerado > cel(celulas, m, s)["idx"].med_gabarito
                for m in NOME)
        rel.confere("5", f"Carga gerada ganha mais que a de referência — {ROTULO[s]}", e, f"{n} de 5")

    # População medida na Etapa 3
    medidas = [cel(celulas, m, s)["idx"].medidas for m in NOME for s in SGBDS]
    rel.confere("5", "Consultas medidas na Etapa 3, por combinação", "425 a 495",
                f"{min(medidas)} a {max(medidas)}")
    # Quem ficou fora da Etapa 3 além das consultas com erro na Etapa 1.
    # Três questões deram system_error na Etapa 1 original e foram
    # reprocessadas em 01/09/2026, depois de a Etapa 3 daquelas células já ter
    # rodado; a Etapa 3 não foi refeita para elas.
    excecoes = []
    for c in celulas:
        medidas = {q["instance_id"] for r in c["e3"] for q in (r.get("query_results") or [])}
        for r in c["e1"]:
            if not r.get("error") and r["instance_id"] not in medidas:
                excecoes.append([NOME[c["modelo"]], ROTULO[c["sgbd"]], str(r["instance_id"]),
                                 f"`{r['db_id']}`"])
    rel.confere("5", "Consultas executáveis na E1 que ficaram fora da E3",
                "3", str(len(excecoes)))
    if excecoes:
        rel.p("Consultas executáveis na Etapa 1 que não constam da Etapa 3 (reprocessadas "
              "na Etapa 1 em 01/09/2026, depois de a Etapa 3 ter rodado):")
        rel.p()
        rel.tabela(["Modelo", "SGBD", "instance_id", "Banco"], excecoes)

    # Caso extremo citado na seção de tratamento dos dados (Etapas 2 e 3)
    extremo = None
    for c in celulas:
        for etapa in ("e2", "e3"):
            for r in c[etapa]:
                for q in r.get("query_results") or []:
                    a = (q.get("before") or {}).get("latency_ms")
                    d = (q.get("after") or {}).get("latency_ms")
                    if a and d and (extremo is None or a > extremo[0]):
                        extremo = (a, d, c["modelo"], c["sgbd"], r["db_id"], etapa)
    rel.confere("5", "Caso extremo: antes", "408 s", f"{extremo[0] / 1000:.0f} s")
    rel.confere("5", "Caso extremo: depois", "2,1 ms", f"{num(extremo[1], 1)} ms")
    rel.p(f"Caso extremo: Etapa {extremo[5][1]}, {NOME[extremo[2]]} × {ROTULO[extremo[3]]}, "
          f"banco `{extremo[4]}` (consulta de referência).")
    rel.p()
    rel.bloco_afirmacoes("5")


# ------------------------------------------------------------ contaminação

PADROES = {
    "strftime": (re.compile(r"\bstrftime\s*\(", re.I), {"postgresql", "mariadb"}),
    "YEAR()": (re.compile(r"\bYEAR\s*\(", re.I), {"sqlite", "postgresql"}),
    "CAST(… AS REAL)": (re.compile(r"\bCAST\s*\([^)]*\bAS\s+REAL\b", re.I), {"mariadb"}),
    "SUBTRACT()": (re.compile(r"\bSUBTRACT\s*\(", re.I), set(SGBDS)),
    "DIVIDE()": (re.compile(r"\bDIVIDE\s*\(", re.I), set(SGBDS)),
}


def secao_contaminacao(rel, celulas):
    rel.h(2, "6. Contaminação de dialeto")
    rel.p("Cada construção só é contada no SGBD em que é inválida: `strftime` em "
          "PostgreSQL e MariaDB; `YEAR()` em SQLite e PostgreSQL; `CAST(… AS REAL)` "
          "em MariaDB; `SUBTRACT()` e `DIVIDE()` em todos.")
    rel.p()
    marcadas = []
    por_sgbd = Counter()
    prosa = 0
    linhas = []
    for m in NOME:
        lin = [NOME[m]]
        for s in SGBDS:
            n = 0
            for r in cel(celulas, m, s)["e1"]:
                sql = r.get("sql_generated") or ""
                if any(rx.search(sql) for rx, inv in PADROES.values() if s in inv):
                    marcadas.append(r)
                    n += 1
                if any(PADROES[k][0].search(sql) for k in ("SUBTRACT()", "DIVIDE()")):
                    prosa += 1
            por_sgbd[s] += n
            lin.append(str(n))
        linhas.append(lin)
    rel.tabela(["Modelo", "SQLite", "PostgreSQL", "MariaDB"], linhas)
    rel.confere("6", "Consultas contaminadas", "80", str(len(marcadas)))
    rel.confere("6", "… em SQLite / PostgreSQL / MariaDB", "11 / 31 / 38",
                f"{por_sgbd['sqlite']} / {por_sgbd['postgresql']} / {por_sgbd['mariadb']}")
    tipos = Counter(r.get("error_type") for r in marcadas)
    rel.confere("6", "Contaminadas que falharam como SQL inválido", "80",
                str(tipos["sql_error"]))
    sql_err = sum(1 for c in celulas for r in c["e1"] if r.get("error_type") == "sql_error")
    rel.confere("6", "Fração dos SQL inválidos vinda de dialeto trocado", "uma em cada cinco",
                "uma em cada cinco" if round(sql_err / len(marcadas)) == 5
                else f"{100 * len(marcadas) / sql_err:.1f}%")
    rel.confere("6", "Consultas com SUBTRACT/DIVIDE", "19", str(prosa))
    rel.bloco_afirmacoes("6")


# -------------------------------------------------------------- rota

def secao_rota(rel, celulas, rota):
    rel.h(2, "7. Equivalência entre rotas de acesso")
    nativo = {r["instance_id"]: bool(r["execution_accuracy"])
              for r in cel(celulas, "claude-sonnet-5", "sqlite")["e1"]}
    alt = {r["instance_id"]: bool(r["execution_accuracy"]) for r in rota}
    ids = sorted(alt)
    a = sum(nativo[i] for i in ids)
    b = sum(alt[i] for i in ids)
    conc = sum(nativo[i] == alt[i] for i in ids)
    so_n = sum(nativo[i] and not alt[i] for i in ids)
    so_a = sum(alt[i] and not nativo[i] for i in ids)
    rel.confere("7", "Questões no subteste", "136", str(len(ids)))
    rel.confere("7", "EX pela rota nativa", "60,3%", pct(100 * a / len(ids)))
    rel.confere("7", "EX pela rota alternativa", "59,6%", pct(100 * b / len(ids)))
    rel.confere("7", "Concordância questão a questão", "93,4%", pct(100 * conc / len(ids)))
    rel.confere("7", "Divergências (favorecem nativa / alternativa)", "5 / 4", f"{so_n} / {so_a}")
    rel.bloco_afirmacoes("7")


# -------------------------------------------------------------- McNemar

def _chi2_cc(b: int, c: int) -> tuple[float, float]:
    """McNemar com correção de continuidade; p para 1 grau de liberdade."""
    if b + c == 0:
        return 0.0, 1.0
    x = (abs(b - c) - 1) ** 2 / (b + c)
    return x, math.erfc(math.sqrt(x / 2))


def _exato(b: int, c: int) -> float:
    """McNemar exato: teste binomial bilateral sobre as discordâncias."""
    n, k = b + c, min(b, c)
    if n == 0:
        return 1.0
    cauda = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * cauda)


def _fmt_p(p: float) -> str:
    return f"{p:.2e}" if p < 0.001 else num(p, 3)


_SOBRESCRITO = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _potencia(p: float) -> str:
    """1.8e-05 -> '2 × 10⁻⁵', como o artigo escreve."""
    mant, expo = f"{p:.0e}".split("e")
    return f"{mant} × 10{str(int(expo)).translate(_SOBRESCRITO)}"


def secao_mcnemar(rel, celulas):
    rel.h(2, "8. Teste de McNemar (bloco [[PROFESSOR]] do artigo)")
    rel.p("Pareamento por (SGBD, questão): cada dupla de modelos é comparada nas "
          "1.500 respostas que ambos deram às mesmas questões nos mesmos SGBDs. "
          "Só as discordâncias entram no teste. Correção de Bonferroni para dez "
          "comparações: α = 0,005.")
    rel.p()
    acerto = {(c["modelo"], c["sgbd"], r["instance_id"]): bool(r["execution_accuracy"])
              for c in celulas for r in c["e1"]}
    linhas = []
    resultados = []
    for A, B in combinations(NOME, 2):
        b = c = 0
        for s in SGBDS:
            for i in range(500):
                x, y = acerto.get((A, s, i)), acerto.get((B, s, i))
                if x is None or y is None:
                    continue
                b += x and not y
                c += y and not x
        x2, p = _chi2_cc(b, c)
        resultados.append((A, B, b, c, p, _exato(b, c)))
    for A, B, b, c, p, pe in sorted(resultados, key=lambda r: r[4]):
        linhas.append([f"{NOME[A]} × {NOME[B]}", str(b), str(c), _fmt_p(p), _fmt_p(pe),
                       "sim" if p < 0.005 else "não"])
    rel.tabela(["Dupla", "só A acerta", "só B acerta", "p (χ², corr.)", "p (exato)",
                "significativo (Bonferroni)"], linhas)
    sig = sum(1 for r in resultados if r[4] < 0.005)
    rel.confere("8", "Duplas significativas", "7 de 10", f"{sig} de 10")
    meio = {"qwen/qwen3.8-27b", "openai/gpt-5.6-luna", "deepseek/deepseek-v4-flash-0731"}
    nao_sig = {frozenset((r[0], r[1])) for r in resultados if r[4] >= 0.05}
    rel.confere("8", "As não significativas são exatamente as do trio Qwen, Luna, DeepSeek",
                "sim", "sim" if nao_sig == {frozenset(p) for p in combinations(meio, 2)} else "não")
    mais_prox = max(resultados, key=lambda r: r[4])
    rel.confere("8", "Par mais próximo: discordâncias", "180 e 174",
                f"{max(mais_prox[2], mais_prox[3])} e {min(mais_prox[2], mais_prox[3])}")
    rel.confere("8", "Par mais próximo: p", "0,79", num(mais_prox[4], 2))
    zona = [r for r in resultados if 0.005 <= r[4] < 0.05]
    rel.confere("8", "Comparações na zona intermediária (0,005 ≤ p < 0,05)", "0", str(len(zona)))

    # Método usado no cálculo que gerou o número do bloco [[PROFESSOR]]: soma as
    # discordâncias SQLite×PostgreSQL e SQLite×MariaDB num só teste.
    maior_somado = 0.0
    for m in NOME:
        b = c = 0
        for s in ("postgresql", "mariadb"):
            for i in range(500):
                x, y = acerto[(m, "sqlite", i)], acerto[(m, s, i)]
                b += x and not y
                c += y and not x
        maior_somado = max(maior_somado, _chi2_cc(b, c)[1])
    rel.p(f"Pelo método somado (o do cálculo original, não mais citado no artigo), o "
          f"maior p entre os modelos seria {_potencia(maior_somado)}.")
    rel.p()

    rel.p("Achado principal, SQLite contra cada servidor separadamente. Cada modelo "
          "faz dois testes (correção de Bonferroni para dez: 5 modelos × 2 "
          "servidores). Esta forma substitui o cálculo original, que somava as "
          "duas comparações num só teste e usava cada resposta do SQLite duas vezes.")
    rel.p()
    linhas = []
    maior_p = 0.0
    for m in NOME:
        for s in ("postgresql", "mariadb"):
            b = c = 0
            for i in range(500):
                x, y = acerto[(m, "sqlite", i)], acerto[(m, s, i)]
                b += x and not y
                c += y and not x
            _, p = _chi2_cc(b, c)
            maior_p = max(maior_p, p)
            linhas.append([NOME[m], ROTULO[s], str(b), str(c), _fmt_p(p), _fmt_p(_exato(b, c))])
    rel.tabela(["Modelo", "Servidor", "só SQLite acerta", "só servidor acerta",
                "p (χ², corr.)", "p (exato)"], linhas)
    abaixo_005 = [l for l in linhas if float(l[4].replace(',', '.')) < 0.05]
    bonf = [l for l in linhas if float(l[4].replace(',', '.')) < 0.005]
    fora = [l for l in linhas if l not in bonf]
    rel.confere("8", "SQLite × servidor: testes abaixo de 0,05", "10 de 10",
                f"{len(abaixo_005)} de 10")
    rel.confere("8", "SQLite × servidor: significativos após Bonferroni", "9 de 10",
                f"{len(bonf)} de 10")
    rel.confere("8", "Único que não permanece após Bonferroni", "Qwen 3.8 27B × PostgreSQL",
                " ; ".join(f"{l[0]} × {l[1]}" for l in fora))
    rel.confere("8", "… com p", "0,006", " ; ".join(num(float(l[4].replace(',', '.')), 3)
                                                   for l in fora))
    rel.p(f"Pelo teste separado, o maior p é {_fmt_p(maior_p)}: todas as dez comparações "
          f"ficam abaixo de 0,05, e {sum(1 for l in linhas if float(l[4].replace(',', '.')) < 0.005)} "
          f"de 10 abaixo do limite de Bonferroni (0,005).")
    rel.p()
    rel.bloco_afirmacoes("8")


# -------------------------------------------------------- cobertura de colunas

_ALVO = (exp.Where, exp.Join, exp.Group, exp.Order, exp.Having)
_DIALETO = {"sqlite": "sqlite", "postgresql": "postgres", "mariadb": "mysql"}


def colunas_de_predicado(sql: str, sgbd: str) -> set[str] | None:
    """Colunas referenciadas em WHERE, JOIN, GROUP BY, ORDER BY e HAVING."""
    try:
        arvore = sqlglot.parse_one(sql, read=_DIALETO[sgbd])
    except Exception:
        return None
    if arvore is None:
        return None
    out = set()
    for no in arvore.find_all(*_ALVO):
        for col in no.find_all(exp.Column):
            if col.name:
                out.add(col.name.lower())
    return out


_ON = re.compile(r"\bON\s+[`\"]?\w+[`\"]?\s*\((.*)\)\s*;?\s*$", re.I | re.S)


def colunas_indexadas(stmts: list[str]) -> set[str]:
    out = set()
    for st in stmts:
        m = _ON.search(st)
        if not m:
            continue
        for parte in m.group(1).split(","):
            nome = re.sub(r"\(\s*\d+\s*\)", "", parte)
            nome = re.sub(r"\b(ASC|DESC)\b", "", nome, flags=re.I)
            out.add(nome.strip().strip('`"').lower())
    return out


# Método original: o mesmo critério por expressão regular usado no cálculo
# que gerou os números do artigo. Captura a coluna à esquerda de um operador
# de comparação em segmentos WHERE/AND/OR/ON/GROUP BY/ORDER BY.
_SEG = re.compile(r"\b(?:WHERE|AND|OR|ON|GROUP BY|ORDER BY)\b(.*?)"
                  r"(?=\bWHERE\b|\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", re.I | re.S)
_IDENT = re.compile(r"\b(?:\w+\.)?`?(\w+)`?\s*(?:=|>|<|>=|<=|LIKE|IN|BETWEEN)", re.I)


def colunas_regex(sql: str) -> set[str]:
    return {m.group(1).lower() for seg in _SEG.findall(sql) for m in _IDENT.finditer(seg)}


def colunas_sqlglot(sql: str) -> set[str]:
    return colunas_de_predicado(sql, "sqlite") or set()


def _cobertura(celulas, extrator):
    linhas, ref_v, ger_v, inv = [], [], [], 0
    for m in NOME:
        c = cel(celulas, m, "sqlite")
        a = b = cc = d = 0
        for r2 in c["e2"]:
            if r2.get("error"):
                continue
            idx = colunas_indexadas([s["statement"] for s in (r2.get("indexes_suggested") or [])
                                     if s.get("success")])
            regs = [r for r in c["e1"] if r["db_id"] == r2["db_id"]]
            ref = set().union(*(extrator(r["sql_gold"]) for r in regs))
            ger = set().union(*(extrator(r["sql_generated"]) for r in regs
                                if r.get("sql_generated") and not r.get("error")))
            a, b = a + len(ref & idx), b + len(ref)
            cc, d = cc + len(ger & idx), d + len(ger)
        pr, pg = 100 * a / b, 100 * cc / d
        ref_v.append(pr)
        ger_v.append(pg)
        inv += pg < pr
        linhas.append([NOME[m], f"{a}/{b}", pct(pr), f"{cc}/{d}", pct(pg), num(pg - pr, 1)])
    return linhas, ref_v, ger_v, inv


def secao_cobertura(rel, celulas):
    rel.h(2, "9. Cobertura das colunas de predicado (hipótese da carga gerada)")
    rel.p("Para cada modelo, nas células SQLite: das colunas usadas como predicado "
          "pelas consultas de cada banco, que fração é coluna de algum índice "
          "aplicado na Etapa 2 daquele modelo. Conjunto de colunas distintas por "
          "banco, somado nos 11 bancos. As consultas geradas que falharam na "
          "Etapa 1 ficam de fora, como na Etapa 3.")
    rel.p()
    cab = ["Modelo", "Referência", "%", "Geradas", "%", "Diferença (p.p.)"]

    rel.p("**Método original** (expressão regular: coluna à esquerda de um operador de "
          "comparação). É o critério do número citado no artigo, aqui aplicado só "
          "aos arquivos do manifesto. O cálculo anterior lia todas as rodadas do "
          "diretório, inclusive ensaios e parciais, e contava alguns bancos duas vezes.")
    rel.p()
    linhas, ref_v, ger_v, inv = _cobertura(celulas, colunas_regex)
    rel.tabela(cab, linhas)
    d1 = [g - r for g, r in zip(ger_v, ref_v)]
    rel.confere("9", "Critério regex: modelos em que as geradas ficam mais cobertas",
                "5 de 5", f"{5 - inv} de 5")
    rel.confere("9", "Critério regex: vantagem das geradas (p.p.)", "0,4 a 2,8",
                f"{num(min(d1), 1)} a {num(max(d1), 1)}")

    rel.p("O cálculo anterior também não removia `ASC`/`DESC` da definição do índice, "
          "de modo que `ON t(col DESC)` não contava como cobrindo `col`; a função "
          "`colunas_indexadas` corrige isso.")
    rel.p()
    rel.p("**Verificação de robustez** (`sqlglot`: toda coluna referenciada em WHERE, "
          "JOIN, GROUP BY, ORDER BY ou HAVING, inclusive dentro de funções e dos dois "
          "lados de uma junção):")
    rel.p()
    linhas2, ref2, ger2, inv2 = _cobertura(celulas, colunas_sqlglot)
    rel.tabela(cab, linhas2)

    rel.p("A cobertura acompanha a vantagem da carga gerada? Diferença geradas − "
          "referência em cada critério, ao lado da diferença de mediana de ganho "
          "(Etapa 3 − Etapa 2) no SQLite:")
    rel.p()
    comp = []
    for k, m in enumerate(NOME):
        i = cel(celulas, m, "sqlite")["idx"]
        comp.append([NOME[m], num(ger_v[k] - ref_v[k], 1), num(ger2[k] - ref2[k], 1),
                     f"+{num(i.med_gerado - i.med_gabarito)}×"])
    rel.tabela(["Modelo", "Δ cobertura (regex, p.p.)", "Δ cobertura (sqlglot, p.p.)",
                "Δ mediana de ganho"], comp)
    d2 = [r - g for g, r in zip(ger2, ref2)]
    rel.confere("9", "Critério sqlglot: modelos em que as geradas ficam menos cobertas",
                "5 de 5", f"{inv2} de 5")
    rel.confere("9", "Critério sqlglot: desvantagem das geradas (p.p.)", "1,1 a 6,1",
                f"{num(min(d2), 1)} a {num(max(d2), 1)}")
    ganho = [cel(celulas, m, "sqlite")["idx"] for m in NOME]
    ganho = [i.med_gerado - i.med_gabarito for i in ganho]
    ordem = lambda v: sorted(range(5), key=lambda k: v[k])
    acompanha = [ordem(d1) == ordem(ganho), ordem([-x for x in d2]) == ordem(ganho)]
    rel.confere("9", "Critérios em que a ordem dos modelos acompanha a vantagem de ganho",
                "nenhum", "nenhum" if not any(acompanha) else str(sum(acompanha)))
    rel.p(f"Pelo critério regex as geradas ficam mais cobertas em {5 - inv} de 5 modelos; "
          f"pelo sqlglot ficam menos cobertas em {inv2} de 5. O sinal depende do "
          f"critério de extração, e em nenhum dos dois a ordem dos modelos acompanha a "
          f"ordem da vantagem de ganho. A cobertura de colunas não explica o padrão.")
    rel.p()
    rel.bloco_afirmacoes("9")


# -------------------------------------------------------------- CSVs

def exportar_csv(celulas, ex):
    destino = SAIDA / "csv"
    destino.mkdir(parents=True, exist_ok=True)
    with (destino / "etapa1_acuracia.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["modelo", "sgbd", "questoes", "acertos", "ex_pct", "exact_match",
                    "sql_error", "timeout"] + [f"ex_{d}" for d in DIFS])
        for c in celulas:
            e1 = c["e1"]
            t = Counter(r.get("error_type") for r in e1 if r.get("error"))
            dif = []
            for d in DIFS:
                rs = [r for r in e1 if r["difficulty"] == d]
                dif.append(f"{100 * sum(bool(r['execution_accuracy']) for r in rs) / len(rs):.2f}")
            w.writerow([c["modelo"], c["sgbd"], len(e1),
                        sum(bool(r["execution_accuracy"]) for r in e1),
                        f"{ex[(c['modelo'], c['sgbd'])]:.2f}",
                        sum(bool(r.get("exact_match")) for r in e1),
                        t["sql_error"], t["timeout"]] + dif)
    with (destino / "etapas2e3_indices.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["modelo", "sgbd", "indices_aplicados", "indices_rejeitados",
                    "mediana_speedup_referencia", "mediana_speedup_geradas",
                    "consultas_medidas_e3", "pct_melhoraram", "pct_passam_a_usar_indice"])
        for c in celulas:
            i = c["idx"]
            w.writerow([c["modelo"], c["sgbd"], i.aplicados, i.falharam,
                        f"{i.med_gabarito:.4f}", f"{i.med_gerado:.4f}", i.medidas,
                        f"{i.pct_melhoraram:.2f}", f"{i.pct_indice_novo:.2f}"])
    with (destino / "etapa1_por_questao.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["modelo", "sgbd", "instance_id", "db_id", "difficulty",
                    "execution_accuracy", "exact_match", "error_type", "provider"])
        for c in celulas:
            for r in c["e1"]:
                w.writerow([c["modelo"], c["sgbd"], r["instance_id"], r["db_id"],
                            r["difficulty"], bool(r["execution_accuracy"]),
                            bool(r.get("exact_match")), r.get("error_type") or "",
                            r.get("provider") or "anthropic (nativo)"])


# -------------------------------------------------------------- principal

def main() -> int:
    rel = Relatorio()
    rel.p("# Conferência dos números do artigo")
    rel.p()
    rel.p("> Gerado por `analise/reproduzir.py` a partir dos arquivos listados em "
          "`analise/manifesto.json`. Não edite à mão: rode o script de novo.")
    celulas, rota, integro = carregar_manifesto(rel)
    secao_condicoes(rel, celulas)
    ex = secao_acuracia(rel, celulas)
    secao_aplicabilidade(rel, celulas)
    secao_ganho(rel, celulas, ex)
    secao_contaminacao(rel, celulas)
    secao_rota(rel, celulas, rota)
    secao_mcnemar(rel, celulas)
    secao_cobertura(rel, celulas)

    ok = sum(a.ok for a in rel.afirmacoes)
    resumo = [
        "",
        "## Resumo",
        "",
        f"- Arquivos íntegros: **{'sim' if integro else 'NÃO'}**",
        f"- Afirmações conferidas: **{ok} de {len(rel.afirmacoes)}** coincidem com os dados",
    ]
    divergentes = [a for a in rel.afirmacoes if not a.ok]
    if divergentes:
        resumo += ["", "Divergências:", ""]
        resumo += [f"- §{a.secao} {a.descricao}: artigo diz **{a.artigo}**, dados dão **{a.dados}**"
                   for a in divergentes]
    rel.linhas[3:3] = resumo

    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "numeros_do_artigo.md").write_text("\n".join(rel.linhas) + "\n", encoding="utf-8")
    exportar_csv(celulas, ex)

    print(f"Arquivos íntegros: {'sim' if integro else 'NÃO'}")
    print(f"Afirmações: {ok}/{len(rel.afirmacoes)} coincidem")
    for a in divergentes:
        print(f"  ✗ §{a.secao} {a.descricao}: artigo {a.artigo!r} · dados {a.dados!r}")
    print(f"Relatório: {SAIDA / 'numeros_do_artigo.md'}")
    return 0 if integro and not divergentes else 1


if __name__ == "__main__":
    sys.exit(main())
