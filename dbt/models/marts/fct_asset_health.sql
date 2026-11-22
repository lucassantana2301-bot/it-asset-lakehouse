-- Saúde de cada equipamento em uso nos últimos 14 dias de dados, com a recomendação de ação.
with params as (
    select max(event_date) as data_until, max(event_date) - interval 13 day as window_start
    from {{ ref('int_asset_daily_utilization') }}
),

recent as (
    select u.*
    from {{ ref('int_asset_daily_utilization') }} as u, params
    where u.event_date >= params.window_start
),

per_asset as (
    select
        asset_id,
        avg(avg_cpu_pct) as avg_cpu_pct_14d,
        quantile_cont(max_cpu_pct, 0.95) as p95_cpu_pct_14d,
        min(min_disk_free_pct) as min_disk_free_pct_14d,
        arg_max(battery_health_pct, event_date) as battery_health_pct,
        regr_slope(battery_health_pct, epoch(event_date) / 86400) * 30 as battery_change_per_30d,
        max(event_date) as last_seen_date,
        sum(readings) as readings_14d
    from recent
    group by all
),

assets as (
    select a.asset_id, a.category, a.model, a.contract_id, c.customer_id
    from {{ ref('stg_assets') }} as a
    left join {{ ref('int_contract_history') }} as c on c.contract_id = a.contract_id and c.is_current
    where a.status = 'deployed' and a.category <> 'monitor'
),

scored as (
    select
        assets.*,
        per_asset.* exclude (asset_id),
        datediff('day', coalesce(per_asset.last_seen_date, params.window_start - interval 1 day), params.data_until)
            as days_since_last_seen,
        params.data_until
    from assets
    cross join params
    left join per_asset using (asset_id)
)

select
    cast(asset_id as varchar) as asset_id,
    cast(category as varchar) as category,
    cast(model as varchar) as model,
    cast(customer_id as varchar) as customer_id,
    cast(round(avg_cpu_pct_14d, 1) as double) as avg_cpu_pct_14d,
    cast(round(p95_cpu_pct_14d, 1) as double) as p95_cpu_pct_14d,
    cast(round(min_disk_free_pct_14d, 1) as double) as min_disk_free_pct_14d,
    cast(round(battery_health_pct, 1) as double) as battery_health_pct,
    cast(round(battery_change_per_30d, 2) as double) as battery_change_per_30d,
    cast(last_seen_date as date) as last_seen_date,
    cast(days_since_last_seen as integer) as days_since_last_seen,
    cast(case
        when days_since_last_seen >= 3 then 'investigar_sem_sinal'
        when battery_health_pct < 70 then 'trocar_bateria'
        when min_disk_free_pct_14d < 10 then 'liberar_disco'
        when avg_cpu_pct_14d < 10 then 'subutilizado'
        else 'ok'
    end as varchar) as recommended_action,
    cast(data_until as date) as data_until
from scored
