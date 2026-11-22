-- MRR de cada cliente no fechamento de cada mês (ou no último dia com dados, no mês corrente).
with bounds as (
    select min(snapshot_date) as first_day, max(snapshot_date) as last_day
    from {{ ref('stg_contracts_daily') }}
),

months as (
    select
        cast(month_start as date) as month_start,
        least(cast(month_start + interval 1 month - interval 1 day as date), bounds.last_day) as as_of_date
    from bounds,
        range(date_trunc('month', bounds.first_day), bounds.last_day + interval 1 day, interval 1 month) as m(month_start)
),

active_versions as (
    select months.month_start, months.as_of_date, h.customer_id, h.monthly_fee
    from months
    join {{ ref('int_contract_history') }} as h
        on h.valid_from <= months.as_of_date
        and (h.valid_to is null or h.valid_to > months.as_of_date)
    where h.status = 'active'
)

select
    month_start,
    as_of_date,
    customer_id,
    sum(monthly_fee) as mrr
from active_versions
group by all
