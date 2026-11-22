-- Movimentação mensal de MRR por cliente: novo, expansão, redução, churn e reativação.
-- A soma das movimentações de um mês reconcilia exatamente com a variação do MRR total
-- (teste singular assert_mrr_movements_reconcile).
with months as (
    select distinct month_start from {{ ref('int_customer_mrr_monthly') }}
),

customers as (
    select customer_id, min(month_start) as first_month
    from {{ ref('int_customer_mrr_monthly') }}
    group by all
),

grid as (
    select c.customer_id, m.month_start
    from customers as c
    join months as m on m.month_start >= c.first_month
),

series as (
    select
        g.customer_id,
        g.month_start,
        coalesce(mrr.mrr, 0) as mrr,
        coalesce(lag(coalesce(mrr.mrr, 0)) over (partition by g.customer_id order by g.month_start), 0) as previous_mrr,
        count(mrr.mrr) over (
            partition by g.customer_id order by g.month_start rows between unbounded preceding and 1 preceding
        ) > 0 as had_mrr_before
    from grid as g
    left join {{ ref('int_customer_mrr_monthly') }} as mrr using (customer_id, month_start)
)

select
    cast(customer_id as varchar) as customer_id,
    cast(month_start as date) as month_start,
    cast(previous_mrr as decimal(18, 2)) as previous_mrr,
    cast(mrr as decimal(18, 2)) as mrr,
    cast(mrr - previous_mrr as decimal(18, 2)) as mrr_change,
    cast(case
        when previous_mrr = 0 and mrr > 0 and not had_mrr_before then 'new'
        when previous_mrr = 0 and mrr > 0 then 'reactivation'
        when previous_mrr > 0 and mrr = 0 then 'churn'
        when mrr > previous_mrr then 'expansion'
        when mrr < previous_mrr then 'contraction'
        else 'flat'
    end as varchar) as movement_type
from series
where mrr > 0 or previous_mrr > 0
