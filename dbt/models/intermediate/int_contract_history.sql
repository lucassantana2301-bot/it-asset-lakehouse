-- Histórico SCD tipo 2 dos contratos, reconstruído das fotos diárias do ERP (gaps and islands):
-- cada sequência de dias com o mesmo estado (status, mensalidade, assentos, vigência) vira uma versão.
with daily as (
    select
        *,
        md5(concat_ws('|', status, monthly_fee, seats, end_date)) as state_hash
    from {{ ref('stg_contracts_daily') }}
),

flagged as (
    select
        *,
        case
            when state_hash is distinct from lag(state_hash) over (partition by contract_id order by snapshot_date)
                then 1
            else 0
        end as starts_version
    from daily
),

numbered as (
    select
        *,
        sum(starts_version) over (
            partition by contract_id order by snapshot_date rows between unbounded preceding and current row
        ) as version
    from flagged
)

select
    contract_id || '-v' || version as contract_version_id,
    contract_id,
    any_value(customer_id) as customer_id,
    version,
    min(snapshot_date) as valid_from,
    lead(min(snapshot_date)) over (partition by contract_id order by version) as valid_to,
    any_value(status) as status,
    any_value(monthly_fee) as monthly_fee,
    any_value(seats) as seats,
    any_value(start_date) as start_date,
    any_value(end_date) as end_date,
    lead(min(snapshot_date)) over (partition by contract_id order by version) is null as is_current
from numbered
group by contract_id, version
