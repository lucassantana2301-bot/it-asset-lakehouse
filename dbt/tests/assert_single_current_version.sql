-- Cada contrato tem exatamente uma versão vigente.
select contract_id, count(*) filter (where is_current) as current_versions
from {{ ref('int_contract_history') }}
group by contract_id
having count(*) filter (where is_current) <> 1
