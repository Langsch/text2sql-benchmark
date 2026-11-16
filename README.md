# Avaliação de Modelos de Linguagem na Recomendação de Índices em Múltiplos SGBDs

*Evaluating Large Language Models for Index Recommendation across Multiple Database Management Systems*

Código, dados e análise do Trabalho de Conclusão de Curso de Rafael Langsch
Caheté Rêgo, Bacharelado em Sistemas de Informação, Universidade Federal
Fluminense. Orientação: Prof. Daniel Cardoso Moraes de Oliveira.

---

## O que este repositório contém

Cinco modelos de linguagem recomendam índices para três SGBDs (SQLite 3,
PostgreSQL 17 e MariaDB 11) sobre os 11 bancos de esquema real do
[BIRD Mini-Dev](https://bird-bench.github.io/). A carga de trabalho sobre a qual
os índices são avaliados é produzida pelo próprio modelo: cada um traduz para
SQL as 500 perguntas em linguagem natural do conjunto (*text-to-SQL*).

O experimento roda em três etapas, para cada par (modelo, SGBD):

| Etapa | O que acontece | O que mede |
|---|---|---|
| **1. Composição da carga** | O modelo traduz as 500 perguntas para SQL; a consulta gerada e a de referência são executadas | Acurácia de execução, *exact match*, latência, plano |
| **2. Recomendação de índices** | O modelo recebe o esquema e as **consultas de referência** de cada banco e devolve `CREATE INDEX` | Índices aplicáveis; ganho sobre as consultas de referência |
| **3. Efeito sobre a carga gerada** | Os índices da Etapa 2 são aplicados e as **consultas geradas na Etapa 1** são reexecutadas, sem nova chamada ao modelo | Ganho sobre a carga que o modelo produziu |

Cinco modelos × três SGBDs = 15 combinações e 7.500 questões medidas.

## Resultados principais

**Aplicabilidade e ganho dos índices.** Índices aplicados sobre recomendados e
mediana do ganho (latência antes / depois) sobre a carga gerada:

| Modelo | Acesso | Aplicáveis | Ganho SQLite | Ganho PostgreSQL | Ganho MariaDB |
|---|---|---:|---:|---:|---:|
| Claude Sonnet 5 | API nativa | 98,6% | 3,52× | 1,68× | 1,65× |
| Gemini 3.1 Flash Lite | OpenRouter | 96,4% | 2,58× | 1,40× | 1,22× |
| Qwen 3.8 27B | OpenRouter | 93,9% | 3,15× | 1,26× | 1,24× |
| GPT-5.6 Luna | OpenRouter | 98,8% | 4,16× | 1,55× | 1,43× |
| DeepSeek V4 Flash | OpenRouter | 90,4% | 3,16× | 1,62× | 1,37× |

O ganho varia mais entre SGBDs do que entre modelos, e a ordem dos modelos por
ganho não acompanha a ordem por acurácia.

**Acurácia de execução na Etapa 1** (500 questões por célula):

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 67,0% | 58,6% | 58,0% |
| Gemini 3.1 Flash Lite | 61,2% | 55,4% | 52,6% |
| Qwen 3.8 27B | 53,4% | 47,4% | 46,6% |
| GPT-5.6 Luna | 53,8% | 46,4% | 46,0% |
| DeepSeek V4 Flash | 52,4% | 43,8% | 44,4% |

Nos cinco modelos, a acurácia em SQLite supera a média dos outros dois sistemas
(vantagem de 6,4 a 8,7 pontos percentuais).

Detalhamento, achados e defeitos corrigidos: [`docs/resultados_matriz_completa.md`](docs/resultados_matriz_completa.md).

## Conferência dos números do artigo

Todo número citado no artigo pode ser recalculado a partir dos arquivos de
resultado, sem chamada a API e sem banco de dados:

```bash
.venv/bin/python analise/reproduzir.py
```

O script confere o SHA-256 de cada arquivo usado, recalcula cada afirmação e
gera [`analise/saida/numeros_do_artigo.md`](analise/saida/numeros_do_artigo.md),
com o valor do artigo, o valor dos dados e se coincidem. Ver
[`analise/README.md`](analise/README.md).

## Disponibilidade dos dados

| Conteúdo | Onde |
|---|---|
| Tabelas agregadas e uma linha por questão (CSV) | [`analise/saida/csv/`](analise/saida/csv/), neste repositório |
| Arquivos brutos de todas as rodadas (JSON: prompt exato, SQL gerado, resposta íntegra do modelo na Etapa 2, plano de execução, provedor que atendeu) | Pacote `resultados.tar.gz` anexado à release `v1.0-tcc` deste repositório *(DOI Zenodo: a preencher)* |
| Dataset BIRD Mini-Dev | Não redistribuído; obter na fonte original com `download_dataset.py` |

## Como reproduzir o experimento

Requer Python 3.11+, [`uv`](https://docs.astral.sh/uv/) e Docker.

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env                      # chaves de API e credenciais dos bancos
.venv/bin/python download_dataset.py      # BIRD Mini-Dev
docker compose up -d                      # PostgreSQL 17 e MariaDB 11
./scripts/setup_databases.sh <pasta do minidev>

# as três etapas de uma combinação (modelo, SGBD)
.venv/bin/python cli.py pipeline --model <modelo> --sgbd sqlite|postgresql|mariadb
```

O acesso via OpenRouter exige provedor fixado; o passo a passo, a pinagem usada
e os custos estão em [`docs/runbook_openrouter.md`](docs/runbook_openrouter.md).
Os testes rodam com `.venv/bin/python -m pytest -q`.

As respostas dos modelos não são determinísticas (ver Limitações): uma
reexecução produz números próximos, não idênticos. A conferência exata é a
feita sobre os arquivos de resultado, acima.

## Configuração dos modelos

| Modelo | Rota | Provedor fixado | Raciocínio |
|---|---|---|---|
| Claude Sonnet 5 | API nativa da Anthropic | — | padrão do modelo (adaptativo) |
| Gemini 3.1 Flash Lite | OpenRouter | google-ai-studio | desabilitado |
| Qwen 3.8 27B | OpenRouter | chutes (fp8) | desabilitado |
| GPT-5.6 Luna | OpenRouter | openai | desabilitado |
| DeepSeek V4 Flash | OpenRouter | novita (fp8) | desabilitado |

Nenhum modelo recebeu parâmetro de temperatura. O provedor que atendeu é
gravado em cada chamada; nas Etapas 1 e 2, todas as chamadas via OpenRouter
foram atendidas pelo provedor fixado.

## Limitações

- As respostas não são determinísticas: não há configuração de temperatura
  comum aos provedores.
- O Claude Sonnet 5 rodou com o raciocínio adaptativo padrão, enquanto os
  demais rodaram com raciocínio desabilitado. A API da Anthropic permitiria
  desligá-lo; isso não foi feito na rodada.
- A recomendação é emitida numa única interação, sem orçamento de
  armazenamento e sem refinamento iterativo. Não se mede o teto de capacidade
  de nenhum modelo.
- A Execution Accuracy segue o critério do BIRD: compara conjuntos de linhas,
  ignorando ordem e duplicatas.

## Estrutura

```
analise/        conferência dos números do artigo (manifesto, script, relatório, CSVs)
cli.py          comandos: run, index, revalidate, pipeline, compare, smoke
docs/           arquitetura, resultados detalhados, runbook do OpenRouter
src/text2sql_benchmark/
  dataset/      leitura do BIRD
  prompt/       prompts de text-to-SQL e de recomendação de índices
  llm/          conectores (Anthropic, OpenRouter e outros)
  db/           conectores SQLite, PostgreSQL e MariaDB; isolamento dos índices
  metrics/      execution accuracy, exact match, parsers de plano, latência
  runner/       Etapas 1, 2 e 3
  report/       relatórios por modelo e comparativo
tests/          testes unitários
```

Decisões de projeto: [`docs/arquitetura.md`](docs/arquitetura.md).

## Referência do conjunto de dados

Li, J. et al. *Can LLM Already Serve as A Database Interface? A BIg Bench for
Large-Scale Database Grounded Text-to-SQLs.* NeurIPS 2023.
