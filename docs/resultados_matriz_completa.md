# Resultados — matriz completa

> Cinco modelos × três SGBDs × três etapas = **15 células, 7.500 questões medidas**.
>
> **Rodadas:** 30/08/2026 (Claude Sonnet 5) e 31/08–01/09/2026 (demais).
> **Custo de API:** US$ 3,69 no OpenRouter (quatro modelos, 12 células, mais
> smokes, ensaios e o subteste de rota) e cerca de US$ 7,40 na API da Anthropic
> (Claude Sonnet 5, três células). São faturas separadas: o saldo do OpenRouter
> **não** inclui o Sonnet nativo. O valor da Anthropic vem do registro de
> 30/08/2026 e inclui desenvolvimento e retrabalho, não sendo o custo limpo das
> três células.
>
> Metodologia e decisões: `docs/pipeline_e_resultados.md`.
> Operação: `docs/runbook_openrouter.md`. Design: `docs/arquitetura.md`.

---

## 1. Lineup

| Modelo | Acesso | Provedor fixado | Quantização |
|---|---|---|---|
| `claude-sonnet-5` | API nativa da Anthropic | — | — |
| `google/gemini-3.1-flash-lite` | OpenRouter | `google-ai-studio` | não declarada |
| `qwen/qwen3.8-27b` | OpenRouter | `chutes` | fp8 |
| `openai/gpt-5.6-luna` | OpenRouter | `openai` | não declarada |
| `deepseek/deepseek-v4-flash-0731` | OpenRouter | `novita` | fp8 |

Todos os modelos do OpenRouter rodaram com **raciocínio desabilitado**
(`reasoning.effort = none`) — ver §6.1. O provedor que atendeu cada chamada é
gravado por questão; a pinagem valeu em 100 % das 6.000 chamadas via OpenRouter.

---

## 2. Etapa 1 — corretude

### 2.1 Execution Accuracy

| Modelo | SQLite | PostgreSQL | MariaDB | Média |
|---|---:|---:|---:|---:|
| Claude Sonnet 5 | 67,0 % | 58,6 % | 58,0 % | **61,2 %** |
| Gemini 3.1 Flash Lite | 61,2 % | 55,4 % | 52,6 % | **56,4 %** |
| Qwen 3.8 27B | 53,4 % | 47,4 % | 46,6 % | **49,1 %** |
| GPT-5.6 Luna | 53,8 % | 46,4 % | 46,0 % | **48,7 %** |
| DeepSeek V4 Flash | 52,4 % | 43,8 % | 44,4 % | **46,9 %** |

### 2.2 Exact Match (em 500)

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 32 | 20 | 35 |
| Gemini 3.1 Flash Lite | 28 | 28 | 23 |
| Qwen 3.8 27B | 28 | 25 | 19 |
| GPT-5.6 Luna | 15 | 11 | 13 |
| DeepSeek V4 Flash | 13 | 7 | 10 |

**Estes valores foram recalculados em 01/09/2026** — os anteriores estavam
errados. Ver §5.4.

### 2.3 Erros de execução (em 500)

Separados por tipo, porque medem coisas diferentes: `sql_error` é SQL inválido
— falha de corretude do modelo — e `timeout` é query válida que excedeu 30 s,
que é resultado de eficiência.

| Modelo | SGBD | `sql_error` | `timeout` | total |
|---|---|---:|---:|---:|
| Claude Sonnet 5 | SQLite | 4 | 1 | 5 |
| Claude Sonnet 5 | PostgreSQL | 13 | 0 | 13 |
| Claude Sonnet 5 | MariaDB | 14 | 0 | 14 |
| Gemini 3.1 Flash Lite | SQLite | 4 | 3 | 7 |
| Gemini 3.1 Flash Lite | PostgreSQL | 18 | 0 | 18 |
| Gemini 3.1 Flash Lite | MariaDB | 43 | 0 | 43 |
| Qwen 3.8 27B | SQLite | 37 | 2 | 39 |
| Qwen 3.8 27B | PostgreSQL | 66 | 0 | 66 |
| Qwen 3.8 27B | MariaDB | 75 | 0 | 75 |
| GPT-5.6 Luna | SQLite | 9 | 3 | 12 |
| GPT-5.6 Luna | PostgreSQL | 14 | 0 | 14 |
| GPT-5.6 Luna | MariaDB | 17 | 0 | 17 |
| DeepSeek V4 Flash | SQLite | 15 | 4 | 19 |
| DeepSeek V4 Flash | PostgreSQL | 28 | 0 | 28 |
| DeepSeek V4 Flash | MariaDB | 35 | 0 | 35 |

**Os 13 timeouts estão todos no SQLite**, nenhum nos dois servidores. É
coerente com a natureza dos motores: o SQLite não tem otimizador baseado em
custo nem paralelismo.

**Totais da Etapa 1 nas 15 células:** 405 erros de execução, sendo 392
`sql_error` e 13 `timeout`. As falhas de índice das Etapas 2 e 3 (233) são
contadas à parte, em §3.1 — somá-las a estas misturaria falha de consulta com
falha de DDL.

Nas 7.500 medições não há **nenhum** `llm_error` nem `system_error`.

### 2.4 Por dificuldade

| Modelo | SGBD | simple | moderate | challenging |
|---|---|---:|---:|---:|
| Claude Sonnet 5 | SQLite | 79,7 % | 66,8 % | 49,0 % |
| Claude Sonnet 5 | PostgreSQL | 70,9 % | 57,6 % | 43,1 % |
| Claude Sonnet 5 | MariaDB | 75,0 % | 55,2 % | 40,2 % |
| Gemini 3.1 Flash Lite | SQLite | 73,6 % | 58,4 % | 50,0 % |
| Gemini 3.1 Flash Lite | PostgreSQL | 70,3 % | 54,4 % | 36,3 % |
| Gemini 3.1 Flash Lite | MariaDB | 69,6 % | 50,4 % | 33,3 % |
| Qwen 3.8 27B | SQLite | 69,6 % | 49,6 % | 39,2 % |
| Qwen 3.8 27B | PostgreSQL | 61,5 % | 44,8 % | 33,3 % |
| Qwen 3.8 27B | MariaDB | 68,2 % | 41,2 % | 28,4 % |
| GPT-5.6 Luna | SQLite | 66,2 % | 52,8 % | 38,2 % |
| GPT-5.6 Luna | PostgreSQL | 61,5 % | 45,2 % | 27,5 % |
| GPT-5.6 Luna | MariaDB | 62,2 % | 42,8 % | 30,4 % |
| DeepSeek V4 Flash | SQLite | 67,6 % | 47,6 % | 42,2 % |
| DeepSeek V4 Flash | PostgreSQL | 59,5 % | 39,2 % | 32,4 % |
| DeepSeek V4 Flash | MariaDB | 61,5 % | 40,8 % | 28,4 % |

A degradação é monotônica nas **15 células**, sem exceção.

---

## 3. Etapas 2 e 3 — índices

### 3.1 Índices aplicados / falharam

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 306 / 0 | 305 / 1 | 296 / 12 |
| Gemini 3.1 Flash Lite | 234 / 1 | 233 / 1 | 182 / 22 |
| Qwen 3.8 27B | 365 / 1 | 325 / 27 | 240 / 32 |
| GPT-5.6 Luna | 332 / 2 | 335 / 1 | 323 / 9 |
| DeepSeek V4 Flash | 399 / 0 | 430 / 5 | **339 / 119** |

O MariaDB concentra as falhas em todos os modelos. A causa dominante é
`Specified key was too long; max key length is 3072 bytes`: índices compostos
sobre colunas TEXT sem prefixo. O DeepSeek é o caso extremo — 119 falhas, 82
delas por esse motivo — apesar de o prompt avisar sobre a exigência.

### 3.2 Speedup mediano

| Modelo | SGBD | E2 (queries gabarito) | E3 (queries geradas) |
|---|---|---:|---:|
| Claude Sonnet 5 | SQLite | 2,84× | 3,52× |
| Claude Sonnet 5 | PostgreSQL | 1,54× | 1,68× |
| Claude Sonnet 5 | MariaDB | 1,46× | 1,65× |
| Gemini 3.1 Flash Lite | SQLite | 2,30× | 2,58× |
| Gemini 3.1 Flash Lite | PostgreSQL | 1,31× | 1,40× |
| Gemini 3.1 Flash Lite | MariaDB | 1,30× | 1,22× |
| Qwen 3.8 27B | SQLite | 2,66× | 3,15× |
| Qwen 3.8 27B | PostgreSQL | 1,44× | 1,26× |
| Qwen 3.8 27B | MariaDB | 1,36× | 1,24× |
| GPT-5.6 Luna | SQLite | 3,27× | **4,16×** |
| GPT-5.6 Luna | PostgreSQL | 1,54× | 1,55× |
| GPT-5.6 Luna | MariaDB | 1,62× | 1,43× |
| DeepSeek V4 Flash | SQLite | 2,88× | 3,16× |
| DeepSeek V4 Flash | PostgreSQL | 1,71× | 1,62× |
| DeepSeek V4 Flash | MariaDB | 1,59× | 1,37× |

Reporta-se a **mediana**: a distribuição tem cauda longa (uma query saiu de
408 s para 2,1 ms) e a média seria dominada por outliers.

### 3.3 Plano usa um dos índices criados (Etapa 3)

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 56 % | 32 % | 12 % |
| Gemini 3.1 Flash Lite | 52 % | 30 % | 9 % |
| Qwen 3.8 27B | 55 % | 32 % | 12 % |
| GPT-5.6 Luna | 58 % | 34 % | 13 % |
| DeepSeek V4 Flash | 60 % | 38 % | 11 % |

Métrica deliberadamente restrita aos índices **novos**. O `uses_index` da
Etapa 1 não serve para comparar SGBDs: cada parser conta índice preexistente de
forma diferente e o InnoDB sempre tem a chave primária agrupada, o que
inflaria o MariaDB artificialmente.

---

## 4. Achados

### 4.1 O SQLite é superior nos cinco modelos — sem exceção

A vantagem do SQLite sobre a média de PostgreSQL e MariaDB:

| Modelo | Vantagem |
|---|---:|
| Claude Sonnet 5 | 8,7 pontos |
| DeepSeek V4 Flash | 8,3 pontos |
| GPT-5.6 Luna | 7,6 pontos |
| Gemini 3.1 Flash Lite | 7,2 pontos |
| Qwen 3.8 27B | 6,4 pontos |

Cinco modelos, cinco fornecedores, cinco arquiteturas — e o padrão não falha
uma vez.

**Implicação para a literatura:** Spider e BIRD avaliam em SQLite. A acurácia
que esses benchmarks reportam superestima o desempenho em bancos de produção,
que são PostgreSQL e MySQL/MariaDB. Esta é a justificativa empírica do
trabalho, e ela deixou de depender de um único modelo.

### 4.2 PostgreSQL e MariaDB empatam

A maior diferença entre os dois em qualquer modelo é de 2,8 pontos (Gemini);
nos outros quatro fica abaixo de 1,6. A divisão relevante não é entre os dois
servidores, e sim entre **SQLite e o resto**.

### 4.3 O ganho de índice acompanha o SGBD, não a qualidade do modelo

O GPT-5.6 Luna tem a terceira pior acurácia do lineup e o **maior speedup do
projeto** (4,16× no SQLite). Já o Gemini, segundo em acurácia, tem o menor
(2,58×). Corretude e eficiência são eixos independentes: índice bom não
compensa SQL ruim, e SQL bom não garante ganho de índice.

O uso de índice novo no plano é praticamente idêntico entre modelos e varia
com o SGBD (SQLite ~55 %, PostgreSQL ~33 %, MariaDB ~11 %). Isso sugere que a
diferença está no otimizador de cada SGBD, não em quem sugeriu os índices.

### 4.4 O que NÃO replicou: "queries incorretas ganham mais"

Achado observado na rodada isolada do Sonnet. Com cinco modelos:

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---|---|---|
| Claude Sonnet 5 | incorretas | incorretas | **corretas** |
| Gemini 3.1 Flash Lite | **corretas** | **corretas** | **corretas** |
| Qwen 3.8 27B | incorretas | incorretas | **corretas** |
| GPT-5.6 Luna | incorretas | **corretas** | **corretas** |
| DeepSeek V4 Flash | incorretas | **corretas** | **corretas** |

Não há padrão. No MariaDB inverte em **todos** os modelos; o Gemini inverte
nos três. **Este achado não se sustenta e não deve ser reportado como
regularidade.**

### 4.5 Contaminação de dialeto — quantificada

Construções válidas em um SGBD aparecem nas consultas geradas para outro, em
todos os cinco modelos. A contagem abaixo conta cada construção **apenas onde
ela é inválida** naquele SGBD:

| Construção | Inválida em |
|---|---|
| `strftime(...)` | PostgreSQL, MariaDB (é função do SQLite) |
| `YEAR(...)` | SQLite, PostgreSQL (é função do MySQL/MariaDB) |
| `CAST(x AS REAL)` | MariaDB (REAL não é tipo de CAST no MariaDB) |
| `SUBTRACT(...)`, `DIVIDE(...)` | todos — não existem em SQL nenhum |

Consultas com ao menos uma construção inválida para o alvo:

| Modelo | SQLite | PostgreSQL | MariaDB | Total |
|---|---:|---:|---:|---:|
| Claude Sonnet 5 | 2 | 6 | 8 | 16 |
| Gemini 3.1 Flash Lite | 0 | 7 | 11 | 18 |
| Qwen 3.8 27B | 6 | 12 | 6 | 24 |
| GPT-5.6 Luna | 0 | 2 | 4 | 6 |
| DeepSeek V4 Flash | 3 | 4 | 9 | 16 |
| **Total** | **11** | **31** | **38** | **80** |

**As 80 consultas contaminadas falharam — taxa de falha de 100 %, todas como
`sql_error`.** A construção de dialeto errado é sempre fatal: nunca degrada
silenciosamente para um resultado incorreto, o que a torna detectável.

Elas respondem por **19,8 % dos 405 erros de execução** da Etapa 1, ou
**20,4 % dos 392 `sql_error`** — um em cada cinco SQLs inválidos da matriz vem
de dialeto trocado.

A contaminação é mínima no SQLite (11 casos) e cresce nos servidores (31 e 38),
o que é esperado: o SQLite é o dialeto de origem do dataset.

`SUBTRACT` e `DIVIDE` merecem nota à parte — 16 ocorrências. Não existem em
SQL nenhum: vêm do vocabulário do próprio enunciado do BIRD, que descreve
cálculos em prosa, e o modelo os reproduz como se fossem funções. É evidência
de que a formulação do dataset influencia o SQL gerado.

### 4.5.1 Taxa de SQL inválido por modelo

Contando apenas `sql_error`, sem os timeouts:

| Modelo | SQLite | PostgreSQL | MariaDB |
|---|---:|---:|---:|
| Claude Sonnet 5 | 0,8 % | 2,6 % | 2,8 % |
| Gemini 3.1 Flash Lite | 0,8 % | 3,6 % | 8,6 % |
| GPT-5.6 Luna | 1,8 % | 2,8 % | 3,4 % |
| DeepSeek V4 Flash | 3,0 % | 5,6 % | 7,0 % |
| Qwen 3.8 27B | 7,4 % | 13,2 % | 15,0 % |

A ordem é estável nos três SGBDs e a taxa cresce do SQLite para os servidores
em todos os modelos.

> **Nota.** Uma versão anterior deste documento atribuía essa ordem ao porte
> dos modelos. A atribuição foi retirada: o número de parâmetros é público
> apenas para o Qwen (27B); os outros quatro são fechados. O padrão está
> descrito, a causa fica em aberto.

### 4.6 O tier econômico chega perto

O Gemini 3.1 Flash Lite custa US$ 0,25/US$ 1,50 por milhão de tokens — cerca de
um oitavo do Sonnet — e fica em segundo lugar nos três SGBDs, a 4,8 pontos do
primeiro e 7,3 à frente do terceiro.

---

## 5. Defeitos encontrados e corrigidos

Todos foram detectados **antes** de contaminar resultado publicado.

### 5.1 Um provedor do OpenRouter corrompia o SQL

A CoreWeave, servindo o DeepSeek em fp8, injetava tokens de lixo no meio da
consulta: `> it 500`, `> u 500`, BOM (U+FEFF), espaço zero-width (U+200B),
`? INSERT`, `Ages  utes 5-17`. Falhou em **4 de 10** questões; o mesmo prompt
em Novita, OpenInference, DeepInfra, Parasail e Morph saiu limpo.

Rodar as 500 questões ali teria produzido um número falso e publicável,
atribuindo ao modelo um defeito do provedor. Repinado para `novita`.

**Lição operacional:** o smoke de uma questão **não** detecta isso — passou
limpo por sorte. É preciso o ensaio de 10 questões e inspecionar os erros.

### 5.2 `NameError` no runner de índices

A unificação da fábrica de conectores deixou uma referência viva a
`GroqConnector` num ramo que só executa a partir do segundo banco. A Etapa 1
(20 min, já paga) sobreviveu; a Etapa 2 quebrou. Corrigido, com um teste que
percorre a árvore sintática dos runners procurando nomes indefinidos.

### 5.3 CSVs sobrescritos entre SGBDs

Os nomes de arquivo levavam etapa e modelo, mas não o SGBD: rodar o mesmo
modelo no segundo banco apagava o primeiro, sem aviso. Os JSONs estavam
intactos e os CSVs foram regenerados. Hoje há um subdiretório por SGBD.

### 5.4 O Exact Match estava errado nas 15 células

O normalizador tratava caixa, espaços e aspas, mas **não o ponto-e-vírgula
final** — e as queries gabarito do BIRD não usam terminador. Consequência:

| Modelo | Consultas terminando em `;` | EM antigo |
|---|---:|---:|
| GPT-5.6 Luna | 500/500 | 0 |
| DeepSeek V4 Flash | 498/500 | 0 |
| Qwen 3.8 27B | 147/500 | 23 |
| Claude Sonnet 5 | 119/500 | 17 |
| Gemini 3.1 Flash Lite | 22/500 | 22 |

Luna e DeepSeek tinham Exact Match **estruturalmente zero**, por diferença
puramente tipográfica. O aparente "Gemini é o único com EM alto" era artefato:
ele apenas usava menos ponto-e-vírgula.

Corrigido e recalculado offline nas 15 células — `sql_generated` e `sql_gold`
estão gravados em cada registro, então não foi preciso reexecutar nada. **As 15
células mudaram.**

### 5.5 `ARRAY_AGG` estourava a comparação de resultados

A Execution Accuracy compara conjuntos de linhas; o PostgreSQL devolve arrays
como lista Python, que não entra em `set()`. Duas questões viraram
`system_error` e a resposta do modelo foi descartada mesmo podendo estar
correta. Corrigido com conversão recursiva para tipos comparáveis.

### 5.6 `EXPLAIN` sobre resposta com dois statements

Quando o modelo devolve duas consultas, o `EXPLAIN` prefixa só a primeira e o
cursor termina com o resultado da última — inteiros no lugar de um plano. Uma
questão afetada. Corrigido extraindo o primeiro statement, com separador que
respeita `;` dentro de aspas e crases. A semântica de `execute` foi mantida de
propósito, para não invalidar a comparação com a rodada já fechada do Sonnet.

### 5.7 Total de questões perdidas

**3 de 7.500 (0,04 %)**, todas reprocessadas em 01/09/2026 após a correção das
causas. Não há mais nenhuma medição inválida na matriz.

Uma quarta questão (Sonnet × SQLite, id 168) tinha erro sem classificação por
ser anterior ao campo `error_type`. Era `sql_error` legítimo — `misuse of
aggregate: COUNT()` — e foi apenas rotulada, não reexecutada.

---

## 6. Decisões metodológicas desta rodada

### 6.1 Raciocínio desabilitado

Os modelos do OpenRouter rodaram com `reasoning.effort = none`.

**Motivo empírico**, medido no mesmo modelo, mesma questão e mesmo provedor,
variando apenas o parâmetro:

| DeepSeek V4 Flash | Saída | Latência |
|---|---:|---:|
| Com raciocínio (padrão) | 2.986 tokens | 25,9 s |
| `reasoning.effort = none` | **46 tokens** | **2,0 s** |

Fator **65×** em tokens de saída e 13× em latência, para produzir seis linhas
de SQL equivalentes. A estimativa de custo da matriz caiu de US$ 50 para os
US$ 3,69 efetivamente gastos.

**Justificativa metodológica:** a rodada nativa do Sonnet, que é a linha de
base, praticamente não raciocinou, apesar de o thinking adaptativo da Anthropic
vir ligado por padrão — a saída observada ficou na ordem de uma centena de
tokens, contra os milhares dos modelos que raciocinam. Desligar o raciocínio
nos demais aproxima a condição da linha de base em vez de afastá-la.

> **Limitação desta comparação.** A Etapa 1 não registrava `output_tokens`
> (corrigido em 01/09/2026, válido para rodadas futuras). O consumo do Sonnet
> por questão vem de chamadas de amostra, não do total da rodada, e por isso
> **não** se reporta aqui um fator Sonnet × DeepSeek: ele misturaria medições
> de origens diferentes. O fator 65× acima é controlado e se sustenta.

**Limitação a declarar:** não se está medindo o teto de capacidade de cada
modelo. Números comparados aos de leaderboards públicos aparecerão mais baixos.

O `google/gemini-3.7-flash`, previsto no lineup, foi **descartado** por não
permitir desligar o raciocínio (`Reasoning is mandatory for this endpoint`).
Mantê-lo criaria a assimetria que a decisão busca evitar. Substituído pelo
`gemini-3.1-flash-lite`, que aceita `effort: none`.

### 6.2 Parâmetros de amostragem

Nenhum modelo recebeu `temperature`. Não existe configuração comum aos
provedores — os modelos Claude atuais rejeitam o parâmetro com HTTP 400 — e o
OpenRouter **omite silenciosamente** parâmetros não suportados em vez de
retornar erro. Enviar `temperature=0.0` produziria assimetria invisível: uns
modelos em 0,0 e outros no padrão do provedor, sem nada indicando isso.

**Limitação:** as respostas não são determinísticas; uma reexecução pode
produzir SQL diferente para o mesmo prompt.

### 6.3 Pinagem de provedor

O roteamento padrão do OpenRouter troca de provedor entre requisições, com peso
inverso ao quadrado do preço. Numa rodada de 500 questões isso espalharia o
experimento por provedores e quantizações diferentes. Todas as requisições
levaram `provider: {only: [...], allow_fallbacks: false}`, e o provedor que
atendeu foi gravado por questão para verificação posterior.

Verificado: **6.000 de 6.000 chamadas** atendidas pelo provedor fixado.

### 6.4 Equivalência entre rotas de acesso — verificada

O Sonnet rodou pela API nativa; os demais, via OpenRouter. Para descartar
efeito de rota, o Sonnet foi reexecutado via OpenRouter (provedor `anthropic`)
em 136 questões de três bancos — `formula_1`, `toxicology` e
`california_schools`.

| Rota | Execution Accuracy |
|---|---:|
| API nativa da Anthropic (30/08) | 60,3 % (82/136) |
| OpenRouter (01/09) | 59,6 % (81/136) |

Concordância questão a questão: **127 de 136 (93,4 %)**. Das nove
discordâncias, quatro favorecem o OpenRouter e cinco a rota nativa — divisão
compatível com o não-determinismo do modelo, sem viés sistemático.

O subteste rodou **sem** parâmetro de raciocínio, replicando a condição da
rodada nativa: enviá-lo compararia condições em vez de rotas.

**Conclusão:** as rotas são equivalentes. A assimetria de acesso deixa de ser
limitação declarada e passa a ser diferença medida e descartada.

---

## 7. Reprodução

```bash
docker compose up -d
python cli.py pipeline --model <slug> --sgbd sqlite|postgresql|mariadb
# comparação entre modelos: Etapa 1, e com --stage2/--stage3 também os índices
python cli.py compare \
  --stage1 <e1.json> --stage1 <e1.json> ... \
  --stage2 <e2.json> --stage3 <e3.json> ... \
  --csv-dir results/csv/comparativo
python scripts/progresso.py -w
```

Passo a passo, pinagem e custos: `docs/runbook_openrouter.md`.

### Arquivos das rodadas

Os JSONs de cada célula estão em `results/runs/` (Etapa 1),
`results/runs/index_runs/` (Etapa 2) e `results/runs/revalidation_runs/`
(Etapa 3). Cada registro guarda o prompt exato, o SQL gerado, o SQL gabarito, o
plano de execução, o provedor que atendeu e a classificação do erro — o
suficiente para reproduzir ou reauditar qualquer número deste documento sem
nova chamada de API.

Os CSVs estão em `results/csv/<sgbd>/` por modelo e em
`results/csv/comparativo/` para a visão entre modelos —
`acuracia_por_modelo.csv`, `divergencias.csv` e `indices_por_modelo.csv`.

---

## 8. Em aberto

- **Teste estatístico.** Removido a pedido em 01/09/2026; é decisão de escopo
  com o orientador. Sem ele, diferenças entre modelos são descritivas: os três
  do meio (Qwen 49,1 %, Luna 48,7 %, DeepSeek 46,9 %) devem ser tratados como
  um grupo, sem afirmar ordem entre eles.
- **`README.md` e `docs/arquitetura.md`** descrevem o lineup planejado, não o
  executado.
