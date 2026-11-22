-- Uso diário por equipamento do inventário (telemetria de equipamento desconhecido fica de fora).
select
    t.asset_id,
    t.event_date,
    count(*) as readings,
    avg(t.cpu_util_pct) as avg_cpu_pct,
    max(t.cpu_util_pct) as max_cpu_pct,
    min(t.disk_free_pct) as min_disk_free_pct,
    min(t.battery_health_pct) as battery_health_pct,
    count(*) filter (where t.arrived_late) as late_readings
from {{ ref('stg_telemetry') }} as t
join {{ ref('stg_assets') }} as a using (asset_id)
group by all
