-- No SCD2, duas versões do mesmo contrato nunca podem valer no mesmo dia.
select a.contract_version_id, b.contract_version_id as overlapping_version
from {{ ref('int_contract_history') }} as a
join {{ ref('int_contract_history') }} as b
    on a.contract_id = b.contract_id
    and a.version < b.version
    and a.valid_from < coalesce(b.valid_to, date '9999-12-31')
    and b.valid_from < coalesce(a.valid_to, date '9999-12-31')
