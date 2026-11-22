-- Estado atual de cada equipamento (última foto do sistema de gestão de ativos).
select
    asset_id,
    serial_number,
    category,
    model,
    purchase_date,
    purchase_cost,
    status,
    contract_id,
    updated_at as status_changed_at
from {{ source('bronze', 'assets') }}
qualify _partition_dt = max(_partition_dt) over ()
