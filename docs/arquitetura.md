# Arquitetura e Decisões de Projeto — text2sql-benchmark

> Documento técnico complementar ao README. Registra as decisões de design, a justificativa do dataset escolhido e a arquitetura do framework implementado. Destinado a subsidiar a escrita do TCC e orientar futuras contribuições ao projeto.

---

## 1. Contexto e Motivação

### 1.1 O problema central

Large Language Models têm capacidade crescente de gerar SQL a partir de linguagem natural (Text-to-SQL). Contudo, a grande maioria dos benchmarks acadêmicos consolidados — como Spider e BIRD — avalia os modelos em um único SGBD, tipicamente SQLite, e mede exclusivamente a **corretude** das queries geradas.

Esse recorte ignora dois problemas práticos relevantes:

1. **Variabilidade de dialeto:** O SQL gerado para PostgreSQL não é o mesmo do SQLite. Funções de janela, tipos de dados, operadores de texto, comportamento de NULL e sintaxe de CTEs variam entre SGBDs. Um modelo pode gerar SQL correto para um SGBD e inválido para outro — e nenhum benchmark existente mede isso sistematicamente.

2. **Eficiência da query gerada:** Um modelo pode gerar SQL sintaticamente correto e semanticamente equivalente ao gabarito, mas produzir um plano de execução ineficiente — fazendo full table scan onde um índice deveria ser usado, por exemplo. Métricas de corretude pura são cegas a esse problema.

Este projeto nasce exatamente para preencher essas duas lacunas.

---

### 1.2 Recorte do TCC

O objetivo não é construir o melhor sistema Text-to-SQL, mas sim **avaliar e comparar** o comportamento de cinco LLMs disponíveis comercialmente na tarefa de geração de SQL, cruzando duas dimensões:

- **Modelo** (quem gerou o SQL)
- **SGBD** (em qual banco o SQL foi executado)

E medindo duas propriedades das queries geradas:

- **Corretude** — a query produz o resultado correto?
- **Eficiência** — o plano de execução gerado é eficiente?

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

O **BIRD** (Big Bench for Large-scale Database Grounded Text-to-SQL Evaluation) foi lançado em 2023 e representa uma evolução significativa:

| Dimensão | Spider | BIRD |
|---|---|---|
| Instâncias | ~10.181 | 12.751+ |
| SGBDs | SQLite | SQLite, MySQL, PostgreSQL |
| Bancos de dados | 200 pequenos e limpos | 95 grandes, dados reais e "sujos" |
| Domínios | Genéricos | 37+ profissionais (saúde, finanças, blockchain...) |
| Conhecimento externo | Não | Sim — `evidence` anotado por especialistas |
| Métricas | EX + EM | EX + R-VES (eficiência) + Soft F1 |

A diferença conceitual mais importante é o **evidence**: cada instância do BIRD inclui conhecimento de domínio que não está no schema do banco, mas é necessário para gerar a query correta. Por exemplo:

> **Pergunta:** "Quantos clientes abriram conta na agência com menor salário médio?"
> **Evidence:** "Menor salário médio refere-se à agência com `MIN(A11)`"

Sem esse conhecimento, a pergunta é ambígua. O BIRD reflete melhor cenários do mundo real, onde o usuário tem contexto de negócio que o modelo precisa incorporar.

### 2.3 Por que o BIRD Mini-Dev especificamente

O BIRD Mini-Dev é um subconjunto compacto do BIRD pensado para ciclos rápidos de desenvolvimento:

- **780 instâncias** (500 do dataset original + 270 novas, incluindo operações CRUD e JSON)
- **11 bancos de dados** temáticos (Financial, European Football, Formula 1, etc.)
- Distribuição controlada: 30% simples, 50% moderada, 20% desafiadora
- Scripts de avaliação já implementados no repositório oficial
- Versões nativas para **SQLite, MySQL e PostgreSQL**

Para o contexto de um TCC — onde o custo de chamadas de API é real e o tempo de execução do benchmark impacta o cronograma — 780 instâncias × 5 modelos × 3 SGBDs é um volume gerenciável (≈11.700 execuções de query) sem sacrificar representatividade estatística.

### 2.4 Adaptações necessárias em relação ao BIRD original

| O que o BIRD faz | Nossa adaptação |
|---|---|
| Suporta SQLite, MySQL, PostgreSQL | Substituímos MySQL por **MariaDB** |
| Usa apenas APIs OpenAI/Azure | Adicionamos Anthropic, Google AI, Groq |
| Métrica R-VES (tempo de inferência LLM) | Substituímos por **EXPLAIN ANALYZE** |
| Avaliação offline em script único | Pipeline modular com storage de resultados |

**Por que MariaDB em vez de MySQL?**
MariaDB é um fork do MySQL com divergências crescentes no otimizador, em funções nativas e em tipos de dados. Do ponto de vista acadêmico, incluir MariaDB em vez de MySQL introduz uma comparação mais rica: dois SGBDs com SQL superficialmente similar mas comportamentos distintos. Operacionalmente, MariaDB é equivalente ao MySQL para fins de carga do dataset BIRD.

**Por que EXPLAIN ANALYZE em vez de R-VES?**
O R-VES do BIRD mede a razão entre o tempo de execução da query gerada e o tempo da query de referência. Esse número é sensível à variabilidade de hardware, carga do servidor e latência de rede — fatores externos ao modelo avaliado. O EXPLAIN ANALYZE, por outro lado, expõe o **plano de execução** determinístico do otimizador do SGBD: tipo de scan (sequential vs. index), custo estimado, número real de linhas processadas. Isso permite comparar a qualidade da query gerada de forma independente do ambiente de execução.

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

| Conector | Modelo | API |
|---|---|---|
| `AnthropicConnector` | Claude Sonnet 4.5 | `anthropic` SDK |
| `OpenAIConnector` | GPT-5.2 | `openai` SDK |
| `GoogleConnector` | Gemini 2.5 Pro | `google.genai` SDK |
| `GroqConnector` | Llama 3.3 70B / Qwen 2.5 72B | `groq` SDK |

Todos os modelos usam `temperature=0.0` para garantir determinismo nas respostas e reprodutibilidade do benchmark.

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
| MariaDB | `PyMySQL` | `EXPLAIN ANALYZE` | Sintaxe similar ao PostgreSQL desde MariaDB 10.9 |
| SQLite | `sqlite3` (stdlib) | `EXPLAIN QUERY PLAN` | Sem custo numérico, apenas tipo de acesso |

---

#### `metrics/` — Motor de métricas

**Execution Accuracy (EX)**

```python
def execution_accuracy(predicted: list[tuple], gold: list[tuple]) -> bool:
    return set(predicted) == set(gold)
```

Compara os conjuntos de resultados ignorando a ordem das linhas. Uma query que retorna as mesmas linhas em ordem diferente é considerada correta.

**Exact Match (EM)**

Normaliza as strings SQL (lowercase, whitespace, aspas) e compara diretamente. É uma métrica mais restritiva que EX — útil para medir se o modelo gera SQL idiomático próximo ao gabarito, não apenas equivalente em resultado.

**EXPLAIN ANALYZE**

Cada SGBD tem um parser dedicado que extrai do texto bruto do EXPLAIN:

```python
@dataclass
class ExplainResult:
    scan_type: str      # "SeqScan" | "IndexScan" | "Table scan" | etc.
    total_cost: float   # custo estimado (-1.0 para SQLite, que não expõe)
    actual_rows: int    # linhas reais processadas
    uses_index: bool
    raw: str
```

A diferença entre `scan_type` da query gerada vs. da query gold é a métrica de eficiência central do projeto.

**Latência**

Medida com `time.perf_counter()` ao redor da execução da query no banco — não inclui o tempo de inferência do LLM.

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

### 5.1 temperature=0.0 em todos os modelos

Garante que o benchmark seja reprodutível: para o mesmo prompt, o mesmo modelo produz o mesmo SQL. Isso é essencial para comparações científicas. Modelos com `temperature > 0` introduziriam variabilidade não controlada.

### 5.2 Evidence como variável de controle

O flag `BIRD_USE_EVIDENCE=true/false` permite rodar o benchmark nas duas condições e medir o impacto do conhecimento externo na acurácia. Isso adiciona uma dimensão de análise interessante para o TCC sem custo de implementação adicional.

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

---

## 6. Próximos Passos de Implementação

| Prioridade | Tarefa |
|---|---|
| Alta | Implementar `get_schema()` para PostgreSQL e MariaDB via `information_schema` |
| Alta | Script de carga dos dados BIRD nos SGBDs (`setup_databases.sh`) |
| Alta | Download e organização do dataset BIRD Mini-Dev em `data/bird/` |
| Média | Validação de saída dos LLMs (extração de SQL de respostas com markdown) |
| Média | Exportação CSV no `ReportGenerator` |
| Média | Paralelização de chamadas LLM com `asyncio` ou `ThreadPoolExecutor` |
| Baixa | Gráficos de visualização (matplotlib/plotly) |
| Baixa | Migração do conector Google para `google.genai` (SDK atual) |
