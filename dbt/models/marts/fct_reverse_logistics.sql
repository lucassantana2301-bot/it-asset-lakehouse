-- Ciclo de devolução de equipamentos: pedido → coleta → recebimento no galpão, e a condição na chegada.
select
    cast(shipment_id as varchar) as shipment_id,
    cast(asset_id as varchar) as asset_id,
    cast(contract_id as varchar) as contract_id,
    cast(cast(requested_at as date) as date) as requested_date,
    cast(date_trunc('month', requested_at) as date) as requested_month,
    cast(round(datediff('hour', requested_at, collected_at) / 24.0, 2) as double) as days_to_collect,
    cast(round(datediff('hour', collected_at, received_at) / 24.0, 2) as double) as days_in_transit,
    cast(round(datediff('hour', requested_at, received_at) / 24.0, 2) as double) as cycle_days,
    cast(condition as varchar) as condition,
    cast(received_at is not null as boolean) as is_completed,
    cast(condition in ('damaged', 'missing_parts') as boolean) as has_issue
from {{ ref('stg_shipments') }}
where direction = 'return'
