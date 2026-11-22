-- Indicadores de topo do painel executivo (uma linha).
with mrr as (
    select
        sum(mrr) filter (where month_start = (select max(month_start) from {{ ref('fct_mrr_movements') }})) as mrr,
        sum(mrr_change) filter (where movement_type = 'churn'
            and month_start = (select max(month_start) from {{ ref('fct_mrr_movements') }})) as churned_mrr
    from {{ ref('fct_mrr_movements') }}
),

fleet as (
    select
        count(*) filter (where status = 'deployed') as deployed,
        count(*) filter (where status <> 'retired') as in_service
    from {{ ref('stg_assets') }}
),

sla as (
    select avg(case when is_breached then 0 else 1 end) as compliance
    from {{ ref('fct_ticket_sla') }}
    where opened_at >= (select max(opened_at) from {{ ref('fct_ticket_sla') }}) - interval 30 day
),

returns as (
    select median(cycle_days) as median_cycle_days, avg(case when has_issue then 1.0 else 0 end) as issue_rate
    from {{ ref('fct_reverse_logistics') }}
    where is_completed
),

health as (
    select count(*) filter (where recommended_action <> 'ok') as assets_needing_action, max(data_until) as data_until
    from {{ ref('fct_asset_health') }}
),

quality as (
    select sum(rows_quarantined)::double / nullif(sum(rows_read), 0) as quarantine_rate
    from {{ ref('stg_ingestion_manifests') }}
)

select
    cast(health.data_until as date) as data_until,
    cast((select count(*) from {{ ref('dim_customers') }} where is_active) as integer) as active_customers,
    cast(mrr.mrr as decimal(18, 2)) as mrr,
    cast(coalesce(-mrr.churned_mrr, 0) as decimal(18, 2)) as churned_mrr_last_month,
    cast(fleet.deployed as integer) as assets_deployed,
    cast(round(fleet.deployed::double / nullif(fleet.in_service, 0), 4) as double) as fleet_utilization,
    cast(round(sla.compliance, 4) as double) as sla_compliance_30d,
    cast(round(returns.median_cycle_days, 2) as double) as return_median_cycle_days,
    cast(round(returns.issue_rate, 4) as double) as return_issue_rate,
    cast(health.assets_needing_action as integer) as assets_needing_action,
    cast(round(quality.quarantine_rate, 5) as double) as quarantine_rate
from mrr, fleet, sla, returns, health, quality
