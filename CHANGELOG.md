# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [1.0.0] - 2026-11-22

Primeira versão estável.

### Adicionado

- **Simulador determinístico** dos 5 sistemas de origem da Locabit, com defeitos reais injetados
  (duplicatas, atrasos, chaves nulas, leituras impossíveis e equipamentos fora do inventário).
- **Ingestão landing → bronze** com contrato de dados por fonte, quarentena por linha com motivo,
  Parquet zstd com troca atômica de partição, manifestos e reprocessamento idempotente por checksum.
- **Projeto dbt** com 18 modelos (staging, intermediate, marts):
  - SCD2 dos contratos reconstruído das fotos diárias;
  - movimentação de MRR;
  - saúde da frota, SLA de chamados e logística reversa;
  - KPIs e qualidade de dados;
  - contratos de schema nos marts e ~70 testes, incluindo reconciliação do MRR.
- **Dagster**: assets com linhagem ponta a ponta, checagens de quarentena, testes do dbt como asset checks
  e agenda diária.
- **Painel executivo estático** sem JavaScript, publicado no GitHub Pages com a documentação do dbt.
- **Terraform para AWS**:
  - S3 com KMS, versionamento, logs, TLS obrigatório e ciclo de vida;
  - Glue, Athena com limite de custo e papel IAM via OIDC do GitHub;
  - validado com `tflint` e `checkov`.
- **Qualidade**:
  - ruff, mypy `strict` e 17 testes com 95% de cobertura;
  - pipeline completo e Terraform no CI;
  - CodeQL, Dependabot e ADRs.

[Não lançado]: https://github.com/lucassantana2301-bot/it-asset-lakehouse/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lucassantana2301-bot/it-asset-lakehouse/releases/tag/v1.0.0
