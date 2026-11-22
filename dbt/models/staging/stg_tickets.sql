-- Estado mais recente de cada chamado (o service desk reenvia o chamado a cada mudança).
select
    ticket_id,
    asset_id,
    customer_id,
    priority,
    category,
    status,
    opened_at,
    closed_at
from {{ source('bronze', 'tickets') }}
qualify row_number() over (
    partition by ticket_id
    order by _partition_dt desc, closed_at desc nulls last, _ingested_at desc
) = 1
