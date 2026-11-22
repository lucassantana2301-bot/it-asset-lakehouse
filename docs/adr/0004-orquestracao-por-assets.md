# ADR 0004: Orquestração por assets no Dagster

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

Orquestradores baseados em tarefas (DAG de passos) dizem *o que rodou*, mas não *qual dado está atualizado*, nem de onde ele veio. Este pipeline mistura código Python (geração e ingestão), dbt e um relatório, e cada parte tem checagens de qualidade próprias.

## Decisão

Usar o Dagster com **software-defined assets**:

- `landing_extracts` e os 6 assets `bronze/<fonte>` em Python, com checagem de quarentena por fonte;
- os modelos do dbt carregados pelo `dagster-dbt`. Os testes do dbt viram asset checks, e os sources `bronze.<fonte>` ligam a linhagem aos assets de ingestão automaticamente;
- `fleet_report` dependendo dos marts;
- um job diário com agenda no fuso de São Paulo.

## Consequências

- A linhagem é uma só, da landing ao painel. Um teste automatizado garante que nenhuma dependência aponta para um asset inexistente.
- Falhas aparecem no dado afetado (ex.: `bronze/telemetry` com quarentena alta), não num passo genérico.
- A mesma lógica roda sem orquestrador pela CLI (`lakehouse run`), o que mantém o CI simples e o projeto fácil de experimentar.
