# text2sql-benchmark

> Benchmark comparativo de Large Language Models na geração de consultas SQL para diferentes Sistemas de Gerenciamento de Banco de Dados

---

## Resumo

Este projeto implementa um framework de benchmark para avaliar e comparar a capacidade de cinco Large Language Models (LLMs) na tarefa de Text-to-SQL, geração automática de consultas SQL a partir de perguntas em linguagem natural. A avaliação contempla quatro SGBDs (PostgreSQL, MySQL, MariaDB e SQLite) e mede tanto a **corretude** das queries geradas (Execution Accuracy e Exact Match) quanto sua **eficiência** de execução (análise do plano de query e latência). Os resultados são consolidados em relatórios comparativos que subsidiam a análise do Trabalho de Conclusão de Curso.

---

## Motivação e Contexto

### Por que Text-to-SQL importa

A capacidade de consultar bancos de dados relacionais em linguagem natural democratiza o acesso a dados corporativos: usuários sem conhecimento de SQL passam a obter respostas diretamente de bases estruturadas, sem depender de analistas ou desenvolvedores. Isso viabiliza ferramentas de BI conversacionais e assistentes de dados.

### O problema da variabilidade

LLMs diferentes têm exposição distinta a dialetos SQL durante o treinamento. O SQL do PostgreSQL não é o mesmo do SQLite, janelas temporais, funções de agregação, operadores de texto e comportamento de tipos variam entre SGBDs. Um modelo pode gerar SQL correto para PostgreSQL mas inválido ou subótimo para MySQL. Essa variabilidade cruzada (modelo × SGBD) é o objeto central deste benchmark.

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

| Modelo            | Empresa   | Tipo          | Acesso                    |
|-------------------|-----------|---------------|---------------------------|
| Claude Sonnet 4.5 | Anthropic | Proprietário  | API Anthropic            
| GPT-4.1           | OpenAI    | Proprietário  | API OpenAI               
| Gemini 2.5 Pro    | Google    | Proprietário  | API Google AI            
| Llama 3.3 70B     | Meta      | Open-source   | Groq / Ollama             
| Qwen 2.5 72B      | Alibaba   | Open-source   | Groq / Ollama             

> **Nota sobre modelos open-source:** Os modelos Llama e Qwen podem ser acessados via [Groq](https://groq.com) (inferência rápida, gratuita com rate limits) ou executados localmente via [Ollama](https://ollama.com). Para fins de benchmark de corretude SQL, onde a latência de inferência do LLM não é a variável de interesse, o Groq é mais prático. Para reprodutibilidade sem dependência de serviços externos, use Ollama.

---

## SGBDs Avaliados

| SGBD       | Versão | Licença         | Destaque para o benchmark                                                  |
|------------|--------|-----------------|---------------------------------------------------------------------------|
| PostgreSQL | 17     | BSD             | SQL mais rico: CTEs, window functions, JSONB, `ILIKE`, `EXPLAIN ANALYZE` completo |
| MySQL      | 8.0    | GPL             | SGBD relacional mais popular; diferenças em funções de data/string vs PostgreSQL |
| MariaDB    | 11.x   | GPL             | Fork do MySQL com divergências em tipos, funções e otimizador             |
| SQLite     | 3.x    | Domínio público | Sem servidor; `EXPLAIN QUERY PLAN` com saída diferente; tipagem flexível  |

> **Nota sobre EXPLAIN:** PostgreSQL e MySQL/MariaDB expõem `EXPLAIN ANALYZE` com custo estimado e real. SQLite expõe apenas `EXPLAIN QUERY PLAN` com informação de acesso (índice ou varredura). A implementação trata cada SGBD de forma diferenciada na coleta de métricas de eficiência.

---