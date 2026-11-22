# ADR 0003: SCD tipo 2 reconstruído das fotos diárias

- **Status:** aceito
- **Data:** 2026-11-22

## Contexto

O ERP entrega a foto completa dos contratos todo dia, sem histórico de alterações. O MRR de um mês passado depende do valor do contrato **naquela data**, e não do valor de hoje.

O `dbt snapshot` resolve isso guardando versões a cada execução. Porém:

- o histórico só começa no dia em que o snapshot passa a rodar;
- uma execução perdida perde a versão daquele dia para sempre;
- o resultado depende da ordem das execuções, então não é reprodutível.

## Decisão

O bronze guarda **todas** as fotos diárias (uma partição por dia). O modelo `int_contract_history` reconstrói o SCD2 com *gaps and islands*:

1. calcula um hash do estado relevante (status, mensalidade, assentos, vigência);
2. marca o início de uma versão quando o hash muda em relação ao dia anterior;
3. numera as versões com soma acumulada;
4. agrupa: `valid_from` é o primeiro dia da versão, e `valid_to` (exclusivo) é o início da próxima.

## Consequências

- O histórico é **reprocessável e determinístico**: apagar o warehouse e rodar de novo dá o mesmo resultado.
- Dois testes singulares garantem a integridade: versões do mesmo contrato não se sobrepõem, e existe exatamente uma versão vigente.
- O custo é guardar as fotos completas no bronze. Com Parquet + zstd, 123 dias de contratos ocupam algumas centenas de KB. Em volume maior, o ciclo de vida do S3 move partições antigas para armazenamento frio.
