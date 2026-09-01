# Runbook — rodar a matriz via OpenRouter

> Passo a passo operacional. Decidido em 31/08/2026: os modelos restantes são
> acessados pelo OpenRouter; o Claude Sonnet 5, já fechado nas 9 células pela
> API nativa da Anthropic, **não será reexecutado**.
>
> Metodologia e resultados: `docs/pipeline_e_resultados.md`.

---

## 1. Antes de pôr dinheiro

Suba os bancos e confirme que respondem — o benchmark não chama LLM nenhum
antes de conseguir falar com o SGBD, mas descobrir isso depois de pagar é
desperdício de tempo.

```bash
docker compose up -d
python cli.py smoke --model claude-sonnet-5 --sgbd sqlite
```

Esse smoke usa a chave da Anthropic que já está no `.env` e custa frações de
centavo. Se ele imprimir SQL e disser "A query executou no banco", a
infraestrutura está de pé.

## 2. Crédito e chave

1. Crédito em <https://openrouter.ai/credits>. **US$ 25 cobrem a matriz
   inteira com folga** — ver a tabela de custos abaixo.
2. Chave em <https://openrouter.ai/keys>.
3. Cole no `.env`:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

## 3. Descobrir e fixar o provedor de cada modelo

**Este passo não é opcional.** O roteamento padrão do OpenRouter faz
balanceamento entre provedores upstream com peso inverso ao quadrado do preço:
ele troca de provedor entre requisições. Numa rodada de 500 questões o
experimento se espalha por provedores e quantizações diferentes, e a comparação
entre modelos perde validade.

Exposição por modelo (medida em 31/08/2026):

| Modelo | Provedores | Risco |
|---|---:|---|
| `deepseek/deepseek-v4-flash-0731` | 30 | **alto** |
| `qwen/qwen3.8-27b` | 11 | **alto** |
| `anthropic/claude-sonnet-5` | 5 | médio |
| `openai/gpt-5.6-luna` | 3 | baixo (todos oficiais) |
| `google/gemini-3.1-flash-lite` | 8 | baixo (todos Google) |

Para cada modelo, rode o smoke e cole a linha que ele imprime:

```bash
python cli.py smoke --model openai/gpt-5.6-luna
python cli.py smoke --model google/gemini-3.1-flash-lite
python cli.py smoke --model qwen/qwen3.8-27b
python cli.py smoke --model deepseek/deepseek-v4-flash-0731
```

Cada um custa menos de US$ 0,01 e mostra o SQL gerado, os tokens, a latência,
**qual provedor atendeu** e se a query roda no banco. Rode antes de qualquer
rodada paga: as duas falhas mais caras deste projeto — cercas markdown e crases
no DDL do PostgreSQL — só apareceram em execução real.

O runner **recusa** rodar um modelo multiprovedor sem pinagem, com a mensagem
dizendo qual variável preencher. É proposital: um erro visível custa um
smoke, um roteamento silencioso invalida a rodada inteira.

Nos dois modelos abertos, fixe também a quantização:

```
OPENROUTER_QUANT_QWEN=fp8
OPENROUTER_QUANT_DEEPSEEK=fp8
```

## 3b. Validar o provedor com um ensaio (não pule)

Um smoke de uma questão **não basta** para aprovar um provedor. Em 31/08/2026 o
DeepSeek pinado na CoreWeave (fp8) passou no smoke e depois falhou em 4 de 10
questões, injetando tokens de lixo no meio do SQL:

```
WHERE (`Enrollment (K-12)` + `Enrollment (Ages 5-17)`) > it 500;
WHERE ...                                              >  ﻿499     <- BOM
WHERE ABS(...)                                         >   ? INSERT 30;
       f.`Enrollment (Ages  utes 5-17)`                            <- "utes"
       f.`Enrollment (Ages  ​5-17)`                                <- espaco zero-width
```

Mesmo prompt, mesmo modelo, outros provedores: **todos limpos**. O mesmo lote
de 8 questões deu 4 falhas na CoreWeave contra 2 na Novita — e as 2 da Novita
eram erro legítimo do modelo (coluna inexistente `s.sname`), não corrupção.

Isso é defeito de infraestrutura do provedor, não limitação do modelo. Rodar as
500 questões ali teria produzido um número falso e publicável.

**Sempre rode o ensaio antes da célula inteira:**

```bash
python cli.py pipeline --model <slug> --sgbd sqlite --limit 10
```

Depois inspecione os erros. Se aparecer token estranho dentro do SQL —
caractere invisível, palavra solta, número trocado por letra — troque de
provedor e repita. Erro de coluna ou tabela inexistente é do modelo e pode
seguir.

## 4. Rodar

**Ordem recomendada: do mais barato para o mais caro.** Se algo estiver errado
no pipeline, o erro aparece custando centavos em vez de dólares — e o primeiro
modelo completo já dá o consumo real de tokens de saída, que é a única
incerteza grande da estimativa de custo.

| Ordem | Modelo | Custo (× 3 SGBDs) | Por quê |
|---|---|---:|---|
| 1º | `deepseek/deepseek-v4-flash-0731` | US$ 0,17 | valida o OpenRouter ponta a ponta por quase nada |
| 2º | `openai/gpt-5.6-luna` | US$ 1,17 | |
| 3º | `qwen/qwen3.8-27b` | US$ 2,28 | |
| 4º | `google/gemini-3.1-flash-lite` | US$ 0,84 | |

Uma célula = um modelo × um SGBD × as três etapas. São 12 células (4 modelos ×
3 SGBDs).

```bash
python cli.py pipeline --model openai/gpt-5.6-luna --sgbd sqlite
python cli.py pipeline --model openai/gpt-5.6-luna --sgbd postgresql
python cli.py pipeline --model openai/gpt-5.6-luna --sgbd mariadb
```

E assim por diante. Antes de soltar a célula inteira, vale um ensaio barato:

```bash
python cli.py pipeline --model openai/gpt-5.6-luna --sgbd sqlite --limit 10
```

**Se cair no meio** (crédito, queda de rede), retome sem repagar o que já foi
feito:

```bash
python cli.py run --model openai/gpt-5.6-luna --sgbd sqlite \
  --resume results/runs/<arquivo_da_rodada>.json
```

O resume descarta os registros marcados como `llm_error` e refaz só eles.
Falha de API não é resultado do modelo, e sem essa distinção a acurácia do
MariaDB teria sido reportada como 37,6 % em vez de 58,0 %.

**Acompanhar:**

```bash
python scripts/progresso.py -w
```

## 5. Custo esperado

Base medida: 935.347 tokens de entrada e 56.680 de saída por SGBD (Etapa 1 +
Etapa 2; a Etapa 3 não chama LLM).

Lineup de 4 modelos (decidido em 31/08/2026: sem o `gpt-5.6-terra`).

| Modelo | saída como no Sonnet | saída 3× |
|---|---:|---:|
| `openai/gpt-5.6-luna` | 0,77 | 1,17 |
| `google/gemini-3.1-flash-lite` | 0,84 | 1,61 |
| `qwen/qwen3.8-27b` | 1,42 | 2,28 |
| `deepseek/deepseek-v4-flash-0731` | 0,11 | 0,17 |
| **Total (× 3 SGBDs)** | **5,03** | **7,64** |

A coluna da direita é a de orçamento: a base de saída foi medida no Sonnet
(~84 tokens por resposta) e um modelo que raciocine antes de responder gasta
mais. Mesmo no pior caso (~840 tokens) o total fica em US$ 16,76.

**Custo real medido (01/09/2026): US$ 3,69 no OpenRouter** pelos quatro modelos nas três
etapas e três SGBDs, incluindo smokes, ensaios e o subteste de rota. A
estimativa acima era conservadora porque supunha o consumo de saída do Sonnet,
que não raciocina nesta tarefa;
com o raciocínio desligado, a saída ficou em 44 a 52 tokens por questão.
**US$ 10 cobrem a matriz inteira com folga.**

A base de saída foi medida no Sonnet (~84 tokens por resposta). Modelo que
raciocine muito pode gastar bem mais na saída — é o item a vigiar no
`scripts/progresso.py`.

Opcional, para fechar a assimetria de rota: `anthropic/claude-sonnet-5` em três
bancos (`formula_1`, `toxicology`, `california_schools` = 136 questões) por
**US$ 0,58**, demonstrando que a rota nativa e a do OpenRouter dão o mesmo
resultado. Sem isso, a assimetria fica como limitação declarada no texto.

## 6. Depois de rodar

```bash
python cli.py consolidated --model <slug> \
  --stage1 <e1.json> --stage2 <e2.json> --stage3 <e3.json> \
  --csv-dir results/csv/<sgbd>
```

E confira que a pinagem valeu do início ao fim da rodada — o provedor fica
gravado em cada registro:

```bash
python -c "
import json,sys,collections
d=json.load(open(sys.argv[1]))
print(collections.Counter(r.get('provider','') for r in d))
" results/runs/<arquivo>.json
```

Tem que sair **um provedor só**. Mais de um significa que o fallback agiu e a
rodada não é homogênea.
