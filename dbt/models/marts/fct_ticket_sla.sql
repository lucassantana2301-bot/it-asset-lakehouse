-- Chamados com o SLA de resolução por prioridade e a situação no fim do período de dados.
with sla as (
    select * from (values ('P1', 4), ('P2', 8), ('P3', 24), ('P4', 72)) as t(priority, sla_hours)
),

data_until as (
    select max(coalesce(closed_at, opened_at)) as ts from {{ ref('stg_tickets') }}
)

select
    cast(t.ticket_id as varchar) as ticket_id,
    cast(t.customer_id as varchar) as customer_id,
    cast(t.asset_id as varchar) as asset_id,
    cast(t.priority as varchar) as priority,
    cast(t.category as varchar) as category,
    cast(t.opened_at as timestamp) as opened_at,
    cast(t.closed_at as timestamp) as closed_at,
    cast(date_trunc('month', t.opened_at) as date) as opened_month,
    cast(sla.sla_hours as integer) as sla_hours,
    cast(round(datediff('minute', t.opened_at, coalesce(t.closed_at, d.ts)) / 60.0, 2) as double) as elapsed_hours,
    cast(t.closed_at is not null as boolean) as is_closed,
    cast(datediff('minute', t.opened_at, coalesce(t.closed_at, d.ts)) > sla.sla_hours * 60 as boolean) as is_breached
from {{ ref('stg_tickets') }} as t
join sla using (priority)
cross join data_until as d
