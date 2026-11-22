-- Eventos do agente de telemetria, deduplicados.
-- O agente reenvia eventos (mesmo event_id) e alguns chegam no arquivo do dia seguinte:
-- a data do evento vem de event_ts, nunca da partição, e fica a primeira cópia ingerida.
select
    event_id,
    asset_id,
    event_ts,
    cast(event_ts as date) as event_date,
    cpu_util_pct,
    disk_free_pct,
    battery_health_pct,
    agent_version,
    _partition_dt <> cast(event_ts as date) as arrived_late
from {{ source('bronze', 'telemetry') }}
qualify row_number() over (partition by event_id order by _partition_dt, _ingested_at) = 1
