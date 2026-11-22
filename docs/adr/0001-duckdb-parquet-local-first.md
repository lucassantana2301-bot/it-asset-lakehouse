# ADR 0001: DuckDB e Parquet, local-first

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

O projeto precisa demonstrar uma plataforma de dados completa (ingestão, modelagem, testes, orquestração) que qualquer pessoa consiga rodar em minutos e que o CI execute a cada commit, sem custo de nuvem. Ao mesmo tempo, o desenho precisa ser o de produção, não um atalho de demonstração.

## Decisão

- Lake em **Parquet particionado por dia** (`<camada>/<fonte>/dt=AAAA-MM-DD/`), igual no disco local e no S3.
- **DuckDB** como motor da ingestão e do dbt (`dbt-duckdb`), lendo o Parquet direto, sem carga em banco.
- O caminho do lake vem de `LAKE_ROOT`: um diretório local ou `s3://bucket/prefixo`.

## Consequências

- O pipeline completo (123 dias, ~280 mil linhas) roda em ~40 s num notebook e no CI.
- A troca para Athena ou Spark muda o adaptador do dbt, não os modelos nem o layout do lake. O Terraform já provisiona o Glue Catalog e o workgroup do Athena.
- O DuckDB é processo único: não serve para escrita concorrente nem para volumes de centenas de GB por execução. Esse é o gatilho documentado para migrar o motor.
