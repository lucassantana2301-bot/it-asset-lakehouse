{{ config(meta={'dagster': {'ref': {'name': 'fct_mrr_movements'}}}) }}
-- A variação do MRR total de cada mês precisa ser exatamente a soma das movimentações dos clientes.
with by_month as (
    select
        month_start,
        sum(mrr) as mrr,
        sum(previous_mrr) as previous_mrr,
        sum(mrr_change) as movements
    from {{ ref('fct_mrr_movements') }}
    group by all
),

totals as (
    select month_start, sum(mrr) as mrr
    from {{ ref('int_customer_mrr_monthly') }}
    group by all
)

select by_month.month_start, by_month.mrr, totals.mrr as expected_mrr, by_month.movements
from by_month
join totals using (month_start)
where by_month.mrr <> totals.mrr
   or by_month.mrr - by_month.previous_mrr <> by_month.movements
