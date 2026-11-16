# Conferência dos números do artigo

Esta pasta liga cada número citado no artigo aos arquivos de resultado que o
produziram.

| Arquivo | Papel |
|---|---|
| `manifesto.json` | Lista, para cada uma das 15 combinações (modelo, SGBD), os arquivos das Etapas 1, 2 e 3, com o SHA-256 de cada um. Lista também os arquivos do subteste de equivalência de rota. |
| `reproduzir.py` | Confere os hashes, recalcula cada afirmação numérica do artigo e escreve o relatório. Não chama API nem banco de dados. |
| `saida/numeros_do_artigo.md` | O relatório: para cada afirmação, o valor no artigo, o valor nos dados e se coincidem. |
| `saida/csv/` | Tabelas derivadas: acurácia por célula, índices e ganho por célula, e uma linha por questão da Etapa 1. |

## Como rodar

Na raiz do repositório, com os arquivos de resultado em `results/` (ver
"Disponibilidade dos dados" no README principal):

```bash
.venv/bin/python analise/reproduzir.py
```

O script termina com código 0 quando todos os arquivos estão íntegros e todas
as afirmações coincidem, e com código 1 caso contrário, listando as
divergências no terminal e no início do relatório.

## Como o manifesto foi montado

`results/runs/` guarda todas as rodadas do projeto, inclusive ensaios de 10
questões, rodadas parciais e a rodada descartada por defeito do provedor
CoreWeave. Nenhuma análise lê o diretório inteiro: as 15 cadeias foram
extraídas dos campos `source_stage1_run` e `source_stage2_run` que cada
arquivo da Etapa 3 grava ao rodar, o que garante que as três etapas de uma
célula são as que de fato se encadearam.

## O que cada seção do relatório confere

| Seção | Conteúdo |
|---|---|
| 1 | Integridade: SHA-256 de cada arquivo |
| 2 | 7.500 questões; provedor fixado em todas as chamadas via OpenRouter |
| 3 | Acurácia por célula, vantagem do SQLite, degradação por dificuldade, erros |
| 4 | Índices aplicáveis, quantidade recomendada, causas de rejeição no MariaDB |
| 5 | Mediana de ganho, uso de índice pelo plano, carga gerada × referência, população da Etapa 3 |
| 6 | Contaminação de dialeto |
| 7 | Equivalência entre a rota nativa e o OpenRouter |
| 8 | Teste de McNemar entre modelos e entre SGBDs |
| 9 | Cobertura das colunas de predicado pelos índices, em dois critérios |

## O que não está aqui

Duas medições do artigo não saem dos arquivos de resultado e por isso não são
conferidas pelo script:

- **A diferença de "mais de uma ordem de grandeza" em tokens de saída com o
  raciocínio ligado.** Veio de um ensaio preliminar numa chamada avulsa, que
  não ficou gravado em arquivo; por isso o artigo não cita um fator exato.
- **O efeito do `ANALYZE` ausente no MariaDB** (duas réplicas em quatro
  bancos). Exige o banco em execução; o procedimento e os resultados estão em
  `docs/resultados_matriz_completa.md`, §5.8.
