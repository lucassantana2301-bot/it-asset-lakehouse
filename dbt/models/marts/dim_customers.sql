select
    cast(c.customer_id as varchar) as customer_id,
    cast(c.customer_name as varchar) as customer_name,
    cast(c.cnpj as varchar) as cnpj,
    cast(c.segment as varchar) as segment,
    cast(c.state as varchar) as state,
    cast(c.created_at as date) as customer_since,
    cast(coalesce(sum(h.monthly_fee) filter (where h.status = 'active'), 0) as decimal(18, 2)) as current_mrr,
    cast(coalesce(sum(h.seats) filter (where h.status = 'active'), 0) as integer) as current_seats,
    cast(count(h.contract_id) filter (where h.status = 'active') > 0 as boolean) as is_active
from {{ ref('stg_customers') }} as c
left join {{ ref('int_contract_history') }} as h on h.customer_id = c.customer_id and h.is_current
group by all
