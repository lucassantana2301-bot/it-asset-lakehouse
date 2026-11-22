-- Uma linha por contrato por dia de extração: base para reconstruir o histórico (SCD tipo 2).
select
    contract_id,
    customer_id,
    _partition_dt as snapshot_date,
    start_date,
    end_date,
    seats,
    monthly_fee,
    status
from {{ source('bronze', 'contracts') }}
qualify row_number() over (partition by contract_id, _partition_dt order by _ingested_at desc) = 1
