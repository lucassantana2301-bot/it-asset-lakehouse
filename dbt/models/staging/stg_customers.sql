-- Foto mais recente do cadastro de clientes (o ERP entrega a tabela completa todo dia).
with latest as (
    select *
    from {{ source('bronze', 'customers') }}
    qualify _partition_dt = max(_partition_dt) over ()
)

select
    customer_id,
    regexp_replace(cnpj, '[^0-9]', '', 'g') as cnpj,
    name as customer_name,
    segment,
    upper(state) as state,
    created_at
from latest
