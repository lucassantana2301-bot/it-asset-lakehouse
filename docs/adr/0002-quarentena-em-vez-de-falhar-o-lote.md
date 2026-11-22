# ADR 0002: Quarentena por linha em vez de falhar o lote

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

As fontes mandam linhas inválidas todos os dias: telemetria com CPU de 340%, chave nula, data de fechamento anterior à abertura. Há duas estratégias clássicas:

- **Falhar o lote:** dado perfeito, mas uma única linha ruim atrasa todos os indicadores do dia.
- **Aceitar tudo:** pipeline estável, mas o erro contamina silenciosamente os marts.

## Decisão

Cada fonte tem um **contrato** (colunas, tipos e regras). A ingestão lê tudo como texto, converte com `TRY_CAST` e avalia as regras por linha:

- linhas válidas vão para `bronze/`;
- linhas reprovadas vão para `quarantine/`, com o **valor original** e a **lista de motivos**;
- um manifesto por partição registra as contagens e o checksum do arquivo.

A taxa de quarentena vira um sinal monitorado: checagem de asset no Dagster (alerta acima de 5% por fonte) e teste com severidade `warn` no dbt.

## Consequências

- O dado ruim nunca chega aos marts, e o painel do dia sai mesmo com problemas pontuais na origem.
- Quem investiga tem o valor original e o motivo, sem reprocessar o arquivo.
- Um defeito sistêmico (ex.: a fonte mudou o formato de data) aparece como salto na taxa de quarentena, não como pipeline quebrado. Por isso o limite é monitorado, não opcional.
