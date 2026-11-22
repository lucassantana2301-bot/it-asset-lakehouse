-- Manifestos gravados pela ingestão (um por fonte/partição): base do painel de qualidade de dados.
select
    source,
    cast(dt as date) as partition_date,
    status,
    rows_read,
    rows_valid,
    rows_quarantined,
    cast(ingested_at as timestamp) as ingested_at
from read_json(
    '{{ lake_root() }}/_manifests/*/dt=*.json',
    columns = {
        source: 'VARCHAR', dt: 'VARCHAR', status: 'VARCHAR', rows_read: 'BIGINT',
        rows_valid: 'BIGINT', rows_quarantined: 'BIGINT', ingested_at: 'VARCHAR'
    }
)
