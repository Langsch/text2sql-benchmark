# text2sql-benchmark

> Benchmark comparativo de Large Language Models na geração de consultas SQL para diferentes Sistemas de Gerenciamento de Banco de Dados

---

## Resumo

Este projeto implementa um framework de benchmark para avaliar e comparar a capacidade de cinco Large Language Models (LLMs) na tarefa de Text-to-SQL, geração automática de consultas SQL a partir de perguntas em linguagem natural. A avaliação contempla três SGBDs (PostgreSQL, MariaDB e SQLite) e mede tanto a **corretude** das queries geradas (Execution Accuracy e Exact Match) quanto sua **eficiência** de execução (análise do plano de query e latência). Os resultados são consolidados em relatórios comparativos que subsidiam a análise do Trabalho de Conclusão de Curso.

---

## Motivação e Contexto

### Por que Text-to-SQL importa

A capacidade de consultar bancos de dados relacionais em linguagem natural democratiza o acesso a dados corporativos: usuários sem conhecimento de SQL passam a obter respostas diretamente de bases estruturadas, sem depender de analistas ou desenvolvedores. Isso viabiliza ferramentas de BI conversacionais e assistentes de dados.

### O problema da variabilidade

LLMs diferentes têm exposição distinta a dialetos SQL durante o treinamento. O SQL do PostgreSQL não é o mesmo do SQLite, janelas temporais, funções de agregação, operadores de texto e comportamento de tipos variam entre SGBDs. Um modelo pode gerar SQL correto para PostgreSQL mas inválido ou subótimo para MariaDB. Essa variabilidade cruzada (modelo × SGBD) é o objeto central deste benchmark.

### Lacuna na literatura

A maioria dos benchmarks de Text-to-SQL consolidados (Spider, BIRD) avalia as queries em um único SGBD (tipicamente SQLite), usa apenas métricas de corretude e ignora a eficiência do plano de execução gerado. Este projeto preenche essa lacuna ao comparar sistematicamente múltiplos SGBDs e incluir métricas de eficiência baseadas em `EXPLAIN ANALYZE`.

---

## Objetivos

**Objetivo geral:** Implementar e executar um benchmark sistemático comparando LLMs na geração de SQL para múltiplos SGBDs, avaliando corretude e eficiência das queries produzidas.

**Objetivos específicos:**


- Definir e implementar as métricas de avaliação: Execution Accuracy, Exact Match, EXPLAIN ANALYZE e latência
- Executar o benchmark sobre um dataset de perguntas em linguagem natural com queries de referência
- Analisar estatisticamente os resultados e identificar padrões por modelo, por SGBD e por complexidade de query
- Produzir relatórios comparativos e visualizações para subsidiar o TCC

---

## Modelos Avaliados

Lineup executado (01/09/2026), cinco modelos:

| Modelo | Empresa | Tipo | Acesso |
|---|---|---|---|
| `claude-sonnet-5` | Anthropic | Proprietário | API nativa |
| `google/gemini-3.1-flash-lite` | Google | Proprietário | OpenRouter |
| `qwen/qwen3.8-27b` | Alibaba | Open-source | OpenRouter |
| `openai/gpt-5.6-luna` | OpenAI | Proprietário | OpenRouter |
| `deepseek/deepseek-v4-flash-0731` | DeepSeek | Open-source | OpenRouter |

> **Nota sobre o acesso.** O escopo original previa Groq para os modelos
> abertos, mas o plano pago ficou indisponível e os modelos usados em 06/2026
> foram descontinuados. O projeto migrou para o **OpenRouter** como plataforma
> única, o que também uniformiza o tratamento entre modelos.
>
> O roteamento do OpenRouter troca de provedor entre requisições, e provedores
> diferentes servem quantizações diferentes — por isso toda requisição fixa o
> provedor upstream, e o provedor que atendeu é gravado em cada resultado. Ver
> `docs/runbook_openrouter.md`.

### Resultados

**Execution Accuracy** — 500 questões por célula:

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 67,0 % | 58,6 % | 58,0 % |
| Gemini 3.1 Flash Lite | 61,2 % | 55,4 % | 52,6 % |
| Qwen 3.8 27B | 53,4 % | 47,4 % | 46,6 % |
| GPT-5.6 Luna | 53,8 % | 46,4 % | 46,0 % |
| DeepSeek V4 Flash | 52,4 % | 43,8 % | 44,4 % |

O SQLite fica acima dos dois servidores **nos cinco modelos**, com vantagem de
6,4 a 8,7 pontos. Como Spider e BIRD avaliam em SQLite, a acurácia que esses
benchmarks reportam superestima o desempenho em bancos de produção.

Matriz completa, achados e defeitos corrigidos:
**`docs/resultados_matriz_completa.md`**.

---

## SGBDs Avaliados

| SGBD       | Versão | Licença         | Destaque para o benchmark                                                  |
|------------|--------|-----------------|---------------------------------------------------------------------------|
| PostgreSQL | 17     | BSD             | SQL mais rico: CTEs, window functions, JSONB, `ILIKE`, `EXPLAIN ANALYZE` completo |
| MariaDB    | 11.x   | GPL             | Fork do MySQL com divergências em tipos, funções e otimizador             |
| SQLite     | 3.x    | Domínio público | Sem servidor; `EXPLAIN QUERY PLAN` com saída diferente; tipagem flexível  |

> **Nota sobre EXPLAIN:** PostgreSQL e MariaDB expõem `EXPLAIN ANALYZE` com custo estimado e real. SQLite expõe apenas `EXPLAIN QUERY PLAN` com informação de acesso (índice ou varredura). A implementação trata cada SGBD de forma diferenciada na coleta de métricas de eficiência.

---