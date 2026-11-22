-- Telemetria de equipamentos que não existem no inventário: sinal de agente instalado fora do processo.
select t.*
from {{ ref('stg_telemetry') }} as t
left join {{ ref('stg_assets') }} as a using (asset_id)
where a.asset_id is null
