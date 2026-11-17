# Arquitetura e Decisões de Projeto — text2sql-benchmark

> Documento técnico complementar ao README. Registra as decisões de design, a justificativa do dataset escolhido e a arquitetura do framework implementado. O código faz algumas coisas além do que o artigo usa (por exemplo, a opção de rodar sem *evidence* e conectores de provedores que não entraram na rodada final); quando isso acontece, o texto indica.

---

## 1. Contexto e Motivação

### 1.1 O problema central

Modelos de linguagem vêm sendo propostos para recomendar índices, tarefa que tradicionalmente depende do administrador de banco de dados ou de ferramentas apoiadas no modelo de custo do otimizador. A literatura que avalia essa abordagem concentra-se em um único SGBD, tipicamente PostgreSQL, e em cargas sintéticas (TPC-H, TPC-DS, JOB, DSB). Duas condições ficam pouco examinadas:

1. **O sistema alvo.** O efeito de um índice depende do otimizador que decide usá-lo, e as restrições de criação variam entre sistemas.
2. **A natureza da carga.** Esquemas sintéticos são regulares; esquemas reais não são.

Do lado da geração de SQL, os *benchmarks* consolidados de *text-to-SQL* (Spider, BIRD) conduzem sua avaliação de referência em SQLite, e a variação de dialeto entre SGBDs fica fora do que medem.

---

### 1.2 Recorte do TCC

O trabalho **avalia** cinco modelos de linguagem na recomendação de índices para três SGBDs (SQLite, PostgreSQL e MariaDB), sobre os 11 bancos de esquema real do BIRD Mini-Dev. Não propõe um *advisor*: a recomendação sai de uma única interação, sem orçamento de armazenamento e sem refinamento iterativo.

A carga sobre a qual os índices são avaliados é produzida pelo próprio modelo, que traduz para SQL as 500 perguntas do conjunto (*text-to-SQL*). Essa etapa fornece também o segundo resultado do trabalho: a acurácia da geração de SQL em cada SGBD.

As três etapas (composição da carga, recomendação, efeito sobre a carga gerada) estão descritas no README e na §3.

---

## 2. Escolha do Dataset: BIRD Mini-Dev

### 2.1 Por que não o Spider

O **Spider** foi o benchmark de referência dominante em Text-to-SQL até 2023. Suas características são:

| Dimensão | Spider |
|---|---|
| Instâncias | ~10.181 pares pergunta-SQL |
| SGBDs | SQLite apenas |
| Complexidade | Sintática (JOINs, subqueries, aninhamentos) |
| Conhecimento externo | Não |
| Métricas | Exact Match + Execution Accuracy |

O Spider testa se o modelo domina a **estrutura** do SQL. Para o nosso objetivo, ele apresenta dois problemas fundamentais: avalia em um único SGBD (inviabilizando a dimensão de variabilidade) e não possui métricas de eficiência.

### 2.2 Por que o BIRD

O **BIRD** (*A BIg Bench for Large-Scale Database Grounded Text-to-SQLs*, Li et al., NeurIPS 2023) representa uma evolução significativa:

| Dimensão | Spider | BIRD |
|---|---|---|
| Instâncias | 10.181 | 12.751 |
| SGBDs | SQLite | SQLite, MySQL, PostgreSQL |
| Bancos de dados | 200 pequenos e limpos | 95 grandes (33,4 GB), dados reais e "sujos" |
| Domínios | Genéricos | 37 profissionais (saúde, finanças, blockchain...) |
| Conhecimento externo | Não | Sim — `evidence` anotado por especialistas |
| Métricas | EX + EM | EX + R-VES (eficiência) + Soft F1 |

A diferença conceitual mais importante é o **evidence**: cada instância do BIRD inclui conhecimento de domínio que não está no schema do banco, mas é necessário para gerar a query correta. Por exemplo:

> **Pergunta** (banco `financial`): "Name the account numbers of female clients who are oldest and have lowest average salary?"
> **Evidence:** "Female refers to 'F' in the gender; A11 contains information about average salary"

Sem esse conhecimento, a pergunta é ambígua. O BIRD reflete melhor cenários do mundo real, onde o usuário tem contexto de negócio que o modelo precisa incorporar.

### 2.3 Por que o BIRD Mini-Dev especificamente

O BIRD Mini-Dev é um subconjunto compacto do BIRD pensado para ciclos rápidos de desenvolvimento:

- **500 consultas de leitura** selecionadas do conjunto de desenvolvimento original
- **11 bancos de dados** temáticos (Financial, European Football, Formula 1, etc.)
- Dificuldade estratificada: 148 simples, 250 moderadas, 102 desafiadoras
- Versões nativas para **SQLite, MySQL e PostgreSQL**, com as consultas de referência traduzidas para cada dialeto

O trabalho emprega apenas as 500 consultas de leitura, carregadas pelo `download_dataset.py` a partir dos splits `mini_dev_sqlite`, `mini_dev_mysql` e `mini_dev_pg` do conjunto `birdsql/bird_mini_dev`.

500 questões × 5 modelos × 3 SGBDs = **7.500 medições** na Etapa 1, volume viável para o orçamento de API de um TCC.

### 2.4 Adaptações necessárias em relação ao BIRD original

| O que o BIRD faz | Nossa adaptação |
|---|---|
| Suporta SQLite, MySQL, PostgreSQL | Substituímos MySQL por **MariaDB** |
| Scripts de referência voltados a um provedor | API nativa da Anthropic e OpenRouter (com provedor fixado) |
| Métrica R-VES (razão de tempos gerada/referência) | Ganho de latência **antes e depois dos índices recomendados**, mais o plano de execução |
| Avaliação offline em script único | Pipeline modular de três etapas com storage de resultados |

**Por que MariaDB em vez de MySQL?**
MariaDB é um fork do MySQL com divergências crescentes no otimizador, em funções nativas e em tipos de dados. Do ponto de vista acadêmico, incluir MariaDB em vez de MySQL introduz uma comparação mais rica: dois SGBDs com SQL superficialmente similar mas comportamentos distintos. Operacionalmente, MariaDB é equivalente ao MySQL para fins de carga do dataset BIRD.

**Por que não o R-VES?**
O R-VES do BIRD compara o tempo da consulta gerada com o da consulta de referência, ambos no mesmo banco. Este trabalho faz outra pergunta — se os **índices recomendados pelo modelo** aceleram a carga — e por isso compara a mesma consulta **antes e depois** da aplicação dos índices, no mesmo ambiente e na mesma sessão de medição. A razão antes/depois cancela boa parte da variação de hardware que afeta comparações absolutas de tempo. O plano de execução é coletado junto, em cada SGBD pelo comando que ele oferece (§3.2), para verificar se o otimizador passou a usar índice.

---

## 3. Arquitetura do Framework

### 3.1 Visão geral

O framework é organizado em camadas independentes conectadas por interfaces abstratas. Cada camada pode ser substituída ou estendida sem alterar as demais.

```
BIRD Dataset (JSON)
      │
      ▼
┌─────────────────┐
│  Dataset Loader  │  Lê e normaliza as instâncias do BIRD
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Prompt Builder  │  Monta: schema + question + evidence + instrução de dialeto
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM Runner    │  Chama a API do modelo e extrai o SQL da resposta
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   DB Executor   │  Executa SQL gerado + SQL gold nos 3 SGBDs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Metrics Engine  │  Calcula EX, Exact Match, EXPLAIN, latência
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Results Storage │  Persiste por (modelo, SGBD, instância) em JSON
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Report Generator│  Tabelas comparativas, gráficos, exportação CSV
└─────────────────┘
```

### 3.2 Módulos e responsabilidades

#### `dataset/` — Carregamento do BIRD

**Contrato principal:**

```python
@dataclass
class BirdInstance:
    instance_id: int
    db_id: str
    question: str       # pergunta em linguagem natural
    evidence: str       # conhecimento externo (pode ser vazio)
    sql_gold: str       # query de referência
    difficulty: str     # "simple" | "moderate" | "challenging"
```

O `BirdLoader` lê o arquivo JSON do BIRD Mini-Dev e normaliza as instâncias para esse dataclass. O `difficulty` permite filtrar o dataset em execuções parciais (ex.: rodar apenas instâncias "simple" para validação rápida).

---

#### `prompt/` — Construção do prompt

O prompt enviado a cada LLM segue a estrutura do BIRD original, adaptada para múltiplos dialetos:

```
[1] Schema do banco (DDL das tabelas)
    CREATE TABLE orders (...)
    CREATE TABLE customers (...)

[2] Pergunta + Evidence
    -- Question: How many customers opened account in the lowest salary branch?
    -- External Knowledge: Lowest salary branch refers to MIN(A11)

[3] Chain-of-thought
    Generate the PostgreSQL SQL for the above question after thinking step by step:

[4] Instrução de formato
    Write only the SQL query. No explanations, no markdown blocks.
```

O dialeto SQL é parametrizado — o mesmo prompt é emitido com `"Generate the PostgreSQL SQL..."`, `"Generate the MariaDB SQL..."`, `"Generate the SQLite SQL..."`. Isso força o modelo a produzir SQL adaptado ao SGBD alvo.

O flag `use_evidence` permite rodar o benchmark com e sem o evidence, criando uma variável de controle para medir o impacto do conhecimento externo na acurácia.

---

#### `llm/` — Conectores de modelos

Todos os conectores implementam a mesma interface:

```python
class LLMConnector(ABC):
    model_name: str
    def generate(self, prompt: str) -> LLMResponse: ...

@dataclass
class LLMResponse:
    sql: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float   # latência de inferência do LLM (não da query SQL)
```

| Conector | Uso | API |
|---|---|---|
| `AnthropicConnector` | Claude Sonnet 5 — rodada nativa de 30/08/2026 | `anthropic` SDK |
| `OpenRouterConnector` | **todos os demais modelos** | `openai` SDK contra `openrouter.ai/api/v1` |
| `OpenAIConnector` | acesso nativo, sem uso no lineup atual | `openai` SDK |
| `GoogleConnector` | acesso nativo, sem uso no lineup atual | `google.genai` SDK |
| `GroqConnector` | acesso nativo, sem uso no lineup atual | `groq` SDK |

O despacho fica em `llm/factory.py` e olha o campo `LLMConfig.provider`, nunca
o nome do modelo: a slug `openai/gpt-5.6-luna` é do OpenRouter, e casar por
substring `"gpt"` a mandaria para a API nativa da OpenAI.

Lineup **executado** (01/09/2026), todo via OpenRouter:
`openai/gpt-5.6-luna`, `google/gemini-3.1-flash-lite`, `qwen/qwen3.8-27b`,
`deepseek/deepseek-v4-flash-0731`.

Dois modelos previstos ficaram de fora: o `openai/gpt-5.6-terra` foi descartado
por custo (sozinho seria 60 % do orçamento) e o `google/gemini-3.7-flash` por
não permitir desligar o raciocínio, o que criaria assimetria com os demais.
Os modelos abertos do escopo original (Llama 3.3 70B e Qwen 2.5 72B) foram
descontinuados pela Groq durante o projeto, e o plano pago da Groq esteve
indisponível — daí a migração.

Resultados: `docs/resultados_matriz_completa.md`.

Os parâmetros de amostragem não são uniformizáveis entre provedores — ver §5.1.

---

#### `db/` — Conectores de banco de dados

```python
class DBConnector(ABC):
    dialect: str
    def execute(self, sql: str, timeout: int) -> list[tuple]: ...
    def explain(self, sql: str) -> str: ...      # saída bruta do EXPLAIN
    def get_schema(self, db_id: str) -> str: ... # DDL para o prompt
```

Cada SGBD tem particularidades importantes:

| SGBD | Driver | EXPLAIN | Observação |
|---|---|---|---|
| PostgreSQL | `psycopg2` | `EXPLAIN (ANALYZE, FORMAT TEXT)` | Expõe custo real e estimado |
| MariaDB | `PyMySQL` | `ANALYZE FORMAT=JSON` | O MariaDB não implementa `EXPLAIN ANALYZE` (sintaxe do MySQL 8); a forma equivalente executa a consulta e devolve a árvore JSON do plano |
| SQLite | `sqlite3` (stdlib) | `EXPLAIN QUERY PLAN` | Sem custo numérico, apenas tipo de acesso |

---

#### `metrics/` — Motor de métricas

**Execution Accuracy (EX)**

```python
def execution_accuracy(predicted: list[tuple], gold: list[tuple]) -> bool:
    return {_hashavel(l) for l in predicted} == {_hashavel(l) for l in gold}
```

Compara os **conjuntos** de linhas resultantes, como faz a avaliação oficial do BIRD. Duas consequências, ambas herdadas do BIRD: a ordem das linhas é ignorada, e linhas duplicadas também (um resultado com uma linha repetida duas vezes equivale ao mesmo resultado sem a repetição). `_hashavel` converte arrays e JSON devolvidos pelo PostgreSQL em tipos comparáveis.

**Exact Match (EM)**

Normaliza caixa, espaços, aspas e o ponto-e-vírgula final, e compara as strings. Não normaliza aliases, ordem de cláusulas nem parênteses redundantes: essas são escolhas de escrita, e distingui-las é o propósito da métrica.

**Plano de execução**

Cada SGBD tem um parser dedicado que extrai do texto bruto do plano:

```python
@dataclass
class ExplainResult:
    scan_type: str      # "SeqScan" | "IndexScan" | "Table scan" | etc.
    total_cost: float   # custo estimado (-1.0 para SQLite, que não expõe)
    actual_rows: int    # linhas reais processadas
    uses_index: bool
    raw: str
```

Nas Etapas 2 e 3, o campo `new_index_used` marca a **transição** de um plano que não usava índice para um que passa a usar (`depois.uses_index and not antes.uses_index`). Não identifica qual índice foi usado: uma consulta que já usava índice preexistente não é contada.

**Latência e ganho**

A latência é medida com `time.perf_counter()` ao redor da execução da consulta no banco, sem incluir o tempo de inferência do LLM. A métrica de eficiência central é o **ganho** (speedup) de cada consulta, `latência antes / latência depois` da aplicação dos índices recomendados, reportado pela **mediana** por combinação (modelo, SGBD): a distribuição tem cauda longa e a média seria dominada por poucos casos extremos.

---

#### `runner/` — Orquestração

O `BenchmarkRunner` implementa o loop principal:

```
para cada instância do BIRD:
    para cada SGBD:
        schema = db.get_schema(instância.db_id)
        prompt = prompt_builder.build(instância, schema, dialeto)
        para cada LLM:
            sql_gerado = llm.generate(prompt)
            resultado_gerado, latência = db.execute(sql_gerado)
            resultado_gold = db.execute(instância.sql_gold)
            explain_raw = db.explain(sql_gerado)
            métricas = calcular(...)
            store.add(BenchmarkResult(...))
```

O loop SGBD está **fora** do loop LLM: isso permite que todos os modelos sejam avaliados no mesmo SGBD antes de avançar para o próximo, o que facilita paralelização futura por SGBD.

---

#### `storage/` — Persistência de resultados

Cada execução gera um arquivo `results/runs/<run_id>.json` com uma lista de `BenchmarkResult`:

```python
@dataclass
class BenchmarkResult:
    instance_id: int
    db_id: str
    difficulty: str
    model: str
    sgbd: str
    sql_generated: str
    sql_gold: str
    execution_accuracy: bool
    exact_match: bool
    latency_ms: float
    explain_raw: str
    explain_parsed: dict    # scan_type, total_cost, actual_rows, uses_index
    error: str | None
```

O campo `error` captura falhas de execução (SQL inválido, timeout, erro de conexão) sem interromper o benchmark.

---

#### `report/` — Relatórios

O `ReportGenerator` agrega os resultados por `(model, sgbd)` e produz tabelas comparativas. A saída primária é uma tabela terminal via `rich`, com exportação CSV planejada para importação em ferramentas de análise estatística (R, Python/pandas) usadas na escrita do TCC.

---

## 4. Infraestrutura

### 4.1 SGBDs via Docker

PostgreSQL e MariaDB são provisionados via `docker-compose.yml`. SQLite opera diretamente sobre os arquivos `.sqlite` do BIRD Mini-Dev, sem servidor.

```
docker compose up -d   # sobe PostgreSQL:17 e MariaDB:11
```

### 4.2 Variáveis de ambiente

Todas as chaves de API e URLs de conexão são configuradas via `.env` (baseado em `.env.example`). Nenhuma credencial é commitada no repositório.

### 4.3 Gerenciamento de dependências

O projeto usa **`uv`** para criação de ambientes virtuais e instalação de dependências:

```
uv venv
uv pip install -e ".[dev]"
```

---

## 5. Decisões de Design Relevantes para o TCC

### 5.1 Parâmetros de amostragem: o padrão de cada provedor

O projeto pretendia fixar `temperature=0.0` em todos os modelos para garantir
determinismo. **Isso não é realizável.** O conector da Anthropic enviava o
parâmetro e o Claude Sonnet 5 o rejeitou com HTTP 400; o OpenRouter, por sua
vez, omite silenciosamente parâmetros que o provedor não suporta. Não existe
configuração de temperatura comum aos provedores.

A decisão é usar o padrão de cada provedor e **registrar a não-uniformidade
como limitação do trabalho**: as respostas não são determinísticas e uma
reexecução pode produzir SQL diferente para o mesmo prompt. A rodada do
Claude Sonnet 5 de 30/08/2026 foi feita sem o parâmetro.

A alternativa — fixar temperatura só onde o provedor aceita — seria pior:
introduziria uma assimetria de tratamento exatamente entre os modelos que o
trabalho se propõe a comparar.

### 5.2 Evidence como variável de controle

O flag `BIRD_USE_EVIDENCE=true/false` permite rodar o benchmark com ou sem o conhecimento de domínio no *prompt*. **Todas as rodadas do artigo usaram `true`**; a condição sem *evidence* não foi executada nem é reportada.

### 5.3 Separação entre latência LLM e latência de query

`LLMResponse.latency_ms` mede o tempo de chamada à API do modelo.
`BenchmarkResult.latency_ms` mede o tempo de execução da query no banco.

São métricas distintas com interpretações distintas. Misturá-las seria um erro metodológico.

### 5.4 Timeout por query

Queries que não retornam em `BENCHMARK_TIMEOUT_SECONDS` (padrão: 30s) são registradas como erro. Isso evita que uma query patológica trave o benchmark e garante que o tempo total de execução seja previsível.

### 5.5 Interfaces abstratas (ABC)

Cada componente principal é definido como classe abstrata. Isso permite:
- Substituir um conector de LLM sem alterar o runner
- Adicionar um novo SGBD implementando apenas `DBConnector`
- Trocar o dataset (ex.: usar Spider no futuro) implementando `DatasetLoader`

### 5.6 Pinagem de provedor no OpenRouter

A partir de 31/08/2026 os modelos são acessados pelo OpenRouter. O roteamento
padrão faz balanceamento entre provedores upstream com peso inverso ao quadrado
do preço — ou seja, **troca de provedor entre requisições**. Numa rodada de 500
questões isso espalha o experimento por provedores e quantizações diferentes,
e a comparação entre modelos deixa de ser válida.

Por isso toda requisição leva `provider: {only: [...], allow_fallbacks: false}`.
Desligar o fallback é parte essencial: pinar sem isso faria o roteador cair em
outro provedor no primeiro erro, silenciosamente. Falhar é o comportamento
desejado — um erro visível custa uma repetição, um fallback silencioso invalida
a rodada.

O provedor que atendeu cada chamada é gravado em cada registro de resultado
(campo `provider`), o que permite verificar depois da rodada que a pinagem
valeu do início ao fim.

A pinagem não é só sobre reprodutibilidade: provedores servem o mesmo modelo
com qualidade diferente. Em 31/08/2026 a CoreWeave (fp8) injetava tokens de
lixo no meio do SQL do DeepSeek — 4 falhas em 10 questões, contra 2 (erros
legítimos do modelo) na Novita com o mesmo prompt. Sem pinagem e sem ensaio, o
benchmark teria atribuído ao modelo um defeito do provedor.

`config.PROVEDORES_POR_MODELO` registra quantos provedores servem cada modelo;
`llm/factory.py` recusa construir o conector de um modelo multiprovedor sem
pinagem. Ver `docs/runbook_openrouter.md`.

---

## 6. Estado

A matriz completa — cinco modelos × três SGBDs × três etapas — foi executada
entre 30/08 e 01/09/2026. Os resultados estão em
`docs/resultados_matriz_completa.md`, e cada número citado no artigo pode ser
recalculado a partir dos arquivos de resultado com
`analise/reproduzir.py` (ver `analise/README.md`).

Itens deliberadamente fora do escopo: paralelização das chamadas ao LLM e
gráficos de visualização.
