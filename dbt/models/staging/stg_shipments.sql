-- Estado mais recente de cada envio/coleta da logística.
select
    shipment_id,
    asset_id,
    contract_id,
    direction,
    requested_at,
    collected_at,
    received_at,
    condition
from {{ source('bronze', 'shipments') }}
qualify row_number() over (partition by shipment_id order by _partition_dt desc, _ingested_at desc) = 1
